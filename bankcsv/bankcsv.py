#!/usr/bin/env python3
"""bankcsv - normalise bank statement CSVs from different banks into one
layout, tag transactions with your own category rules, and summarise by month.

Everything runs locally. Standard library only.

Exit codes: 0 = ok, 2 = bad input or wrong column mapping.
"""
import argparse
import csv
import io
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

__version__ = "0.1.0"

ALIASES = {
    "date": {"date", "transaction date", "trans date", "posting date", "posted date",
             "value date", "posted", "booking date"},
    "description": {"description", "details", "narrative", "memo", "payee", "reference",
                    "transaction details", "particulars", "transaction description", "name"},
    "amount": {"amount", "value", "transaction amount"},
    "debit": {"debit", "debits", "money out", "withdrawal", "withdrawals", "paid out", "dr"},
    "credit": {"credit", "credits", "money in", "deposit", "deposits", "paid in", "cr"},
    "balance": {"balance", "running balance", "available balance", "closing balance"},
}
FIELDS = list(ALIASES)
OUT_COLUMNS = ["date", "description", "amount", "balance", "category", "source"]
CURRENCY = re.compile(r"(?i)\b(zar|usd|eur|gbp)\b|[R$€£]")
NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$")


class BankCsvError(Exception):
    pass


# ---------- reading ----------

def read_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise BankCsvError(f"cannot read {path}: {e.strerror}")
    if not raw.strip():
        raise BankCsvError(f"{path} is empty")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def detect_delimiter(text):
    lines = text.splitlines()[:40]
    best, best_key = ",", (0.0, 0)
    for d in [",", ";", "\t", "|"]:
        counts = [len(r) for r in csv.reader(lines, delimiter=d) if r]
        if not counts:
            continue
        modal = max(set(counts), key=counts.count)
        if modal < 2:
            continue
        key = (counts.count(modal) / len(counts), modal)
        if key > best_key:
            best, best_key = d, key
    return best


def norm_header(cell):
    return re.sub(r"\s+", " ", cell.strip().lower())


def find_header(rows):
    """Return (row_index, {field: column_index}) for the first plausible header."""
    for i, row in enumerate(rows[:30]):
        mapping = {}
        for ci, cell in enumerate(row):
            h = norm_header(cell)
            for field, names in ALIASES.items():
                if h in names and field not in mapping:
                    mapping[field] = ci
        has_money = "amount" in mapping or "debit" in mapping or "credit" in mapping
        if "date" in mapping and has_money:
            return i, mapping
    return None, {}


def parse_manual_map(spec):
    mapping = {}
    for part in spec.split(","):
        try:
            field, idx = part.split("=")
            field = field.strip()
            if field not in FIELDS:
                raise ValueError
            mapping[field] = int(idx)
        except ValueError:
            raise BankCsvError(
                f"bad --map entry '{part}'. Use field=column_number, "
                f"fields: {', '.join(FIELDS)}")
    return mapping


# ---------- values ----------

def parse_money(text):
    """Parse '1 234,56', '(12.50)', 'R1,234.50', '99.00-', '45.00 DR'. Returns Decimal or None."""
    s = (text or "").strip()
    if not s:
        return None
    neg = False
    s = s.replace(" ", " ")
    # Check the CR/DR suffix before stripping currency, or the "R" in "DR" goes too.
    m = re.search(r"(?i)\s*(cr|dr)$", s)
    if m:
        neg = m.group(1).lower() == "dr"
        s = s[: m.start()].strip()
    s = CURRENCY.sub("", s).strip()
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1].strip()
    if s.endswith("-"):
        neg, s = True, s[:-1].strip()
    if s.startswith("-"):
        neg, s = True, s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    s = s.replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        raise ValueError(f"not an amount: {text!r}")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")  # 1,234 or 1,234,567
        elif s.count(",") == 1:
            s = s.replace(",", ".")  # 12,5 or 1234,56
        else:
            raise ValueError(f"not an amount: {text!r}")
    elif s.count(".") > 1:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
        else:
            raise ValueError(f"not an amount: {text!r}")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}")
    return -d if neg else d


def infer_dayfirst(values):
    """True = day first, False = month first, None = cannot tell."""
    day_first = month_first = False
    for v in values:
        m = NUMERIC_DATE.match(v.strip())
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:
            day_first = True
        if b > 12:
            month_first = True
    if day_first and not month_first:
        return True
    if month_first and not day_first:
        return False
    return None


TEXT_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d %b %Y", "%d %B %Y", "%d-%b-%Y",
                "%d-%b-%y", "%b %d, %Y", "%B %d, %Y", "%d %b %y"]


def parse_date(text, dayfirst):
    s = text.strip()
    m = NUMERIC_DATE.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        day, month = (a, b) if dayfirst else (b, a)
        try:
            return date(y, month, day)
        except ValueError:
            raise ValueError(f"not a date: {text!r}")
    for fmt in TEXT_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"not a date: {text!r}")


# ---------- rules ----------

def load_rules(path):
    """Parse 'Category: keyword, keyword' lines. Returns [(category, [keywords])]."""
    text = read_text(path)
    rules = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise BankCsvError(f"{path} line {n}: expected 'Category: keyword, keyword'")
        cat, kws = line.split(":", 1)
        words = [k.strip().lower() for k in kws.split(",") if k.strip()]
        if not cat.strip() or not words:
            raise BankCsvError(f"{path} line {n}: category or keywords missing")
        rules.append((cat.strip(), words))
    return rules


def categorise(description, rules):
    d = description.lower()
    for cat, words in rules:
        if any(w in d for w in words):
            return cat
    return "Uncategorised"


# ---------- normalising ----------

def normalise_file(path, rules, manual_map=None, dayfirst=None, invert=False):
    """Return (transactions, warnings). Each transaction is a dict."""
    text = read_text(path)
    delim = detect_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text, newline=""), delimiter=delim)]
    if manual_map:
        mapping, start = manual_map, 1
    else:
        hi, mapping = find_header(rows)
        if hi is None:
            raise BankCsvError(
                f"{path}: could not find a header with a date and an amount "
                f"(or debit/credit) column. Use --map, e.g. --map date=0,description=1,amount=2")
        start = hi + 1
    for f in ("date",):
        if f not in mapping:
            raise BankCsvError(f"{path}: no date column mapped")
    if not ("amount" in mapping or "debit" in mapping or "credit" in mapping):
        raise BankCsvError(f"{path}: no amount, debit or credit column mapped")

    def cell(row, field):
        i = mapping.get(field)
        return row[i].strip() if i is not None and i < len(row) else ""

    body = [r for r in rows[start:] if any(c.strip() for c in r)]
    if dayfirst is None:
        dayfirst = infer_dayfirst([cell(r, "date") for r in body])
    warnings = []
    if dayfirst is None:
        dayfirst = True
        if any(NUMERIC_DATE.match(cell(r, "date")) for r in body):
            warnings.append(f"{os.path.basename(path)}: dates like 03/04/2025 are ambiguous, "
                            f"assuming day first (use --monthfirst to change)")

    out, skipped = [], []
    for offset, row in enumerate(body):
        lineno = start + offset + 1
        try:
            d = parse_date(cell(row, "date"), dayfirst)
            if "amount" in mapping and cell(row, "amount") != "":
                amt = parse_money(cell(row, "amount"))
            else:
                debit = parse_money(cell(row, "debit")) or Decimal(0)
                credit = parse_money(cell(row, "credit")) or Decimal(0)
                if debit == 0 and credit == 0 and not (cell(row, "debit") or cell(row, "credit")):
                    raise ValueError("no amount")
                amt = abs(credit) - abs(debit)
            bal = parse_money(cell(row, "balance")) if cell(row, "balance") else None
        except ValueError as e:
            skipped.append((lineno, str(e)))
            continue
        if invert:
            amt = -amt
        desc = re.sub(r"\s+", " ", cell(row, "description"))
        out.append({
            "date": d.isoformat(), "description": desc,
            "amount": f"{amt:.2f}", "balance": "" if bal is None else f"{bal:.2f}",
            "category": categorise(desc, rules), "source": os.path.basename(path),
        })
    if body and len(skipped) > len(body) / 2:
        raise BankCsvError(
            f"{path}: {len(skipped)} of {len(body)} rows could not be read "
            f"(first: line {skipped[0][0]}, {skipped[0][1]}). Check the columns with --map.")
    if skipped:
        shown = "; ".join(f"line {n}: {why}" for n, why in skipped[:3])
        more = f" (+{len(skipped) - 3} more)" if len(skipped) > 3 else ""
        warnings.append(f"{os.path.basename(path)}: skipped {len(skipped)} row(s): {shown}{more}")
    return out, warnings


# ---------- summary ----------

def summarise(txns):
    months = defaultdict(lambda: {"in": Decimal(0), "out": Decimal(0), "cats": defaultdict(Decimal)})
    unknown = defaultdict(Decimal)
    for t in txns:
        amt = Decimal(t["amount"])
        m = months[t["date"][:7]]
        if amt >= 0:
            m["in"] += amt
        else:
            m["out"] += -amt
            m["cats"][t["category"]] += -amt
            if t["category"] == "Uncategorised":
                unknown[t["description"]] += -amt
    return months, unknown


def format_summary(txns):
    if not txns:
        return "No transactions."
    months, unknown = summarise(txns)
    lines = []
    for key in sorted(months):
        m = months[key]
        lines.append(f"{key}   in {m['in']:>12,.2f}   out {m['out']:>12,.2f}   net {m['in'] - m['out']:>12,.2f}")
        for cat, total in sorted(m["cats"].items(), key=lambda kv: -kv[1]):
            lines.append(f"    {cat:<20} {total:>12,.2f}")
    if unknown:
        lines.append("")
        lines.append("Biggest uncategorised spending (add rules for these):")
        for desc, total in sorted(unknown.items(), key=lambda kv: -kv[1])[:5]:
            lines.append(f"    {total:>12,.2f}  {desc[:50]}")
    return "\n".join(lines)


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(prog="bankcsv",
                                description="Normalise bank CSV exports and summarise spending.")
    p.add_argument("--version", action="version", version=f"bankcsv {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("files", nargs="+", help="bank CSV export(s)")
        sp.add_argument("--rules", help="category rules file ('Category: keyword, keyword')")
        sp.add_argument("--map", help="manual columns, e.g. date=0,description=1,amount=2")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--dayfirst", action="store_true", help="read 03/04/2025 as 3 April")
        g.add_argument("--monthfirst", action="store_true", help="read 03/04/2025 as 4 March")
        sp.add_argument("--invert", action="store_true",
                        help="flip signs (for exports that show spending as positive)")

    n = sub.add_parser("normalize", help="write one tidy CSV")
    common(n)
    n.add_argument("-o", "--output", help="output file (default: stdout)")
    s = sub.add_parser("summary", help="monthly in/out and spending by category")
    common(s)
    return p


def run(args):
    rules = load_rules(args.rules) if args.rules else []
    manual = parse_manual_map(args.map) if args.map else None
    dayfirst = True if args.dayfirst else False if args.monthfirst else None
    txns, warnings = [], []
    for path in args.files:
        t, w = normalise_file(path, rules, manual, dayfirst, args.invert)
        txns += t
        warnings += w
    txns.sort(key=lambda t: (t["date"], t["source"]))
    return txns, warnings


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        txns, warnings = run(args)
        if args.cmd == "summary":
            print(format_summary(txns))
        else:
            sink = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
            try:
                w = csv.DictWriter(sink, fieldnames=OUT_COLUMNS, lineterminator="\n")
                w.writeheader()
                w.writerows(txns)
            finally:
                if args.output:
                    sink.close()
            if args.output:
                print(f"wrote {len(txns)} transactions to {args.output}", file=sys.stderr)
    except BankCsvError as e:
        print(f"bankcsv: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"bankcsv: {e.strerror}", file=sys.stderr)
        return 2
    for w in warnings:
        print(f"bankcsv: warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
