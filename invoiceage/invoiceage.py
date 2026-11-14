#!/usr/bin/env python3
"""invoiceage: aging report and reminder drafts from a CSV of invoices."""
import argparse
import csv
import datetime as dt
import io
import sys
from decimal import Decimal, InvalidOperation

ALIASES = {
    "invoice": ["invoice", "invoice_no", "invoice_number", "number", "id", "ref"],
    "client": ["client", "customer", "name", "company"],
    "amount": ["amount", "total", "balance", "amount_due"],
    "due": ["due", "due_date", "duedate", "date_due"],
    "paid": ["paid", "paid_date", "date_paid", "paid_on"],
}
BUCKETS = [("not due", None), ("1-30", 30), ("31-60", 60), ("61-90", 90), ("90+", None)]


class InputError(Exception):
    pass


def norm(h):
    return h.strip().lower().replace(" ", "_").replace("-", "_")


def map_columns(header):
    names = [norm(h) for h in header]
    out = {}
    for key, options in ALIASES.items():
        for o in options:
            if o in names:
                out[key] = names.index(o)
                break
    missing = [k for k in ("invoice", "client", "amount", "due") if k not in out]
    if missing:
        raise InputError("missing column(s): %s (found: %s)" % (", ".join(missing), ", ".join(header)))
    return out


def parse_date(text):
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("bad date %r (use YYYY-MM-DD)" % text)


def parse_amount(text):
    t = text.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValueError("bad amount %r" % text)
    if not v.is_finite():
        raise ValueError("bad amount %r" % text)
    return -v if neg else v


def load(text):
    """Return (invoices, problems). Paid invoices are skipped."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise InputError("input is empty")
    cols = map_columns(rows[0])
    invoices, problems = [], []
    for n, r in enumerate(rows[1:], start=2):
        def cell(k):
            i = cols.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""
        try:
            if not cell("invoice"):
                raise ValueError("no invoice number")
            if not cell("client"):
                raise ValueError("no client")
            amount = parse_amount(cell("amount"))
            due = parse_date(cell("due"))
        except ValueError as e:
            problems.append("line %d: %s" % (n, e))
            continue
        if cell("paid"):
            continue
        invoices.append({"invoice": cell("invoice"), "client": cell("client"), "amount": amount, "due": due})
    return invoices, problems


def bucket_of(days_late):
    if days_late <= 0:
        return 0
    if days_late <= 30:
        return 1
    if days_late <= 60:
        return 2
    if days_late <= 90:
        return 3
    return 4


def report(invoices, today):
    """Return per-bucket totals and per-client details."""
    totals = [Decimal(0)] * 5
    counts = [0] * 5
    clients = {}
    for inv in invoices:
        late = (today - inv["due"]).days
        b = bucket_of(late)
        totals[b] += inv["amount"]
        counts[b] += 1
        c = clients.setdefault(inv["client"], {"total": Decimal(0), "overdue": Decimal(0), "items": []})
        c["total"] += inv["amount"]
        if late > 0:
            c["overdue"] += inv["amount"]
        c["items"].append(dict(inv, late=late, bucket=b))
    return totals, counts, clients


def money(v):
    return "{:,.2f}".format(v)


def render(invoices, today):
    if not invoices:
        return "No unpaid invoices.\n"
    totals, counts, clients = report(invoices, today)
    lines = ["Aging as of %s" % today.isoformat(), ""]
    for (label, _), t, c in zip(BUCKETS, totals, counts):
        lines.append("  %-8s %3d invoice(s)  %12s" % (label, c, money(t)))
    lines.append("  %-8s %3d invoice(s)  %12s" % ("total", sum(counts), money(sum(totals))))
    lines += ["", "Overdue by client (largest first):"]
    over = [(n, c) for n, c in clients.items() if c["overdue"] > 0]
    if not over:
        lines.append("  nothing overdue")
    for n, c in sorted(over, key=lambda x: (-x[1]["overdue"], x[0])):
        lines.append("  %-20s %12s" % (n, money(c["overdue"])))
        for it in sorted(c["items"], key=lambda i: -i["late"]):
            if it["late"] > 0:
                lines.append("    %-12s %10s  %d days late" % (it["invoice"], money(it["amount"]), it["late"]))
    return "\n".join(lines) + "\n"


def tone(days):
    if days <= 14:
        return "friendly"
    if days <= 45:
        return "firm"
    return "final"


def reminders(invoices, today, sender):
    clients = report(invoices, today)[2]
    out = []
    for name in sorted(clients):
        late = [i for i in clients[name]["items"] if i["late"] > 0]
        if not late:
            continue
        late.sort(key=lambda i: -i["late"])
        worst = late[0]["late"]
        t = tone(worst)
        body = ["To: %s" % name, "Subject: Overdue invoice%s: %s" % ("s" if len(late) > 1 else "", ", ".join(i["invoice"] for i in late)), ""]
        body.append("Hello %s," % name)
        body.append("")
        if t == "friendly":
            body.append("A quick note: the following %s past its due date. It may have crossed with your payment; if so, please ignore this." % ("invoice is" if len(late) == 1 else "invoices are"))
        elif t == "firm":
            body.append("Our records show the following %s still unpaid and past due. Please arrange payment this week or tell me if there is a problem." % ("invoice is" if len(late) == 1 else "invoices are"))
        else:
            body.append("This is a final reminder. The following %s seriously overdue. Please pay within 7 days or contact me to agree a plan." % ("invoice is" if len(late) == 1 else "invoices are"))
        body.append("")
        for i in late:
            body.append("  %s  %s  due %s (%d days ago)" % (i["invoice"], money(i["amount"]), i["due"].isoformat(), i["late"]))
        body.append("  Total: %s" % money(sum(i["amount"] for i in late)))
        body += ["", "Thank you,", sender or "[your name]"]
        out.append("\n".join(body))
    if not out:
        return "No reminders needed.\n"
    return "\n\n----\n\n".join(out) + "\n"


def main(argv=None, stdin=None):
    p = argparse.ArgumentParser(prog="invoiceage", description="Aging report and reminder drafts from an invoice CSV.")
    p.add_argument("file", help="CSV file, or - for stdin")
    p.add_argument("--today", help="date to age against, YYYY-MM-DD (default: today)")
    p.add_argument("--reminders", action="store_true", help="print reminder drafts instead of the report")
    p.add_argument("--sender", help="name to sign reminders with")
    a = p.parse_args(argv)
    try:
        today = parse_date(a.today) if a.today else dt.date.today()
    except ValueError as e:
        print("invoiceage: %s" % e, file=sys.stderr)
        return 2
    try:
        if a.file == "-":
            text = (stdin or sys.stdin).read()
        else:
            with open(a.file, "rb") as f:
                text = f.read().decode("utf-8-sig")
        invoices, problems = load(text)
    except (OSError, UnicodeDecodeError) as e:
        print("invoiceage: cannot read %s: %s" % (a.file, e), file=sys.stderr)
        return 2
    except InputError as e:
        print("invoiceage: %s" % e, file=sys.stderr)
        return 2
    for pr in problems:
        print("warning: skipped %s" % pr, file=sys.stderr)
    sys.stdout.write(reminders(invoices, today, a.sender) if a.reminders else render(invoices, today))
    overdue = any((today - i["due"]).days > 0 for i in invoices)
    return 1 if overdue else (3 if problems else 0)


if __name__ == "__main__":
    sys.exit(main())
