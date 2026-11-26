"""loanplan: amortization with extra payments, and refinance break-even.

Standard library only. All money is Decimal rounded to cents.
"""
import argparse
import csv
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext

getcontext().prec = 28
CENT = Decimal("0.01")
MAX_MONTHS = 1200  # 100 years; guards against runaway loops


class LoanError(ValueError):
    pass


def money(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_decimal(text, name, minimum=None, allow_zero=True):
    try:
        v = Decimal(str(text).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        raise LoanError("%s must be a number, got %r" % (name, text))
    if not v.is_finite():
        raise LoanError("%s must be a finite number, got %r" % (name, text))
    if v < 0 or (v == 0 and not allow_zero):
        raise LoanError("%s must be %s" % (name, "positive" if not allow_zero else "zero or more"))
    if minimum is not None and v < minimum:
        raise LoanError("%s must be at least %s" % (name, minimum))
    return v


def monthly_payment(principal, annual_rate_pct, months):
    """Level payment for a fully amortizing loan."""
    principal = Decimal(principal)
    if principal <= 0:
        raise LoanError("principal must be positive")
    if months < 1 or months > MAX_MONTHS:
        raise LoanError("term must be between 1 and %d months" % MAX_MONTHS)
    r = Decimal(annual_rate_pct) / 100 / 12
    if r == 0:
        return money(principal / months)
    f = (1 + r) ** months
    return money(principal * r * f / (f - 1))


def amortize(principal, annual_rate_pct, months, extra=Decimal(0), lumps=None):
    """Return list of rows (month, payment, interest, principal_paid, balance).

    extra is added to every regular payment; lumps maps month number to a one-off
    extra amount. The loan ends early once the balance reaches zero.
    """
    lumps = lumps or {}
    extra = Decimal(extra)
    if extra < 0:
        raise LoanError("extra payment cannot be negative")
    pay = monthly_payment(principal, annual_rate_pct, months)
    r = Decimal(annual_rate_pct) / 100 / 12
    bal = money(principal)
    rows = []
    m = 0
    while bal > 0:
        m += 1
        if m > MAX_MONTHS:
            raise LoanError("loan does not pay off within %d months" % MAX_MONTHS)
        interest = money(bal * r)
        want = pay + extra + Decimal(lumps.get(m, 0))
        if m == months:  # final scheduled month: clear any rounding remainder
            want = max(want, bal + interest)
        paid = min(want, bal + interest)
        princ = paid - interest
        if princ <= 0:
            raise LoanError("payment does not cover the monthly interest")
        bal = bal - princ
        rows.append((m, paid, interest, princ, bal))
    return rows


def summarize(rows):
    return {
        "months": len(rows),
        "total_paid": sum((r[1] for r in rows), Decimal(0)),
        "total_interest": sum((r[2] for r in rows), Decimal(0)),
        "first_payment": rows[0][1] if rows else Decimal(0),
    }


def refinance(balance, old_rate, old_months_left, new_rate, new_months, closing_costs):
    """Compare keeping a loan with refinancing it.

    Net position at month m = cash paid so far (+ closing costs for the new loan)
    + balance still owed. Break-even is the first month the new loan's net
    position is no worse than the old one's. Returns a dict.
    """
    old = amortize(balance, old_rate, old_months_left)
    new = amortize(balance, new_rate, new_months)
    closing = money(closing_costs)
    horizon = max(len(old), len(new))

    def net(rows, m, upfront):
        paid = sum((r[1] for r in rows[:m]), Decimal(0))
        owed = rows[m - 1][4] if 0 < m <= len(rows) else (Decimal(balance) if m == 0 else Decimal(0))
        return money(paid + owed + upfront)

    breakeven = None
    for m in range(1, horizon + 1):
        if net(new, m, closing) <= net(old, m, Decimal(0)):
            breakeven = m
            break
    return {
        "old_payment": old[0][1],
        "new_payment": new[0][1],
        "old": summarize(old),
        "new": summarize(new),
        "closing": closing,
        "breakeven_month": breakeven,
        "total_cost_old": summarize(old)["total_paid"],
        "total_cost_new": summarize(new)["total_paid"] + closing,
    }


def parse_lump(text):
    """'5000@12' -> (12, Decimal('5000'))"""
    if "@" not in text:
        raise LoanError("lump sum must look like AMOUNT@MONTH, got %r" % text)
    amt, _, mon = text.partition("@")
    amount = parse_decimal(amt, "lump amount", allow_zero=False)
    try:
        month = int(mon)
    except ValueError:
        raise LoanError("lump month must be a whole number, got %r" % mon)
    if month < 1:
        raise LoanError("lump month must be 1 or more")
    return month, amount


def term_months(args):
    if args.months is not None and args.years is not None:
        raise LoanError("give either --years or --months, not both")
    if args.months is not None:
        n = args.months
    elif args.years is not None:
        n = parse_decimal(args.years, "years", allow_zero=False) * 12
        if n != n.to_integral_value():
            raise LoanError("years must give a whole number of months")
        n = int(n)
    else:
        raise LoanError("a term is required: --years or --months")
    if n < 1 or n > MAX_MONTHS:
        raise LoanError("term must be between 1 and %d months" % MAX_MONTHS)
    return n


def fmt_months(n):
    y, m = divmod(n, 12)
    parts = []
    if y:
        parts.append("%d year%s" % (y, "" if y == 1 else "s"))
    if m or not y:
        parts.append("%d month%s" % (m, "" if m == 1 else "s"))
    return " ".join(parts)


def m2(x):
    return "{:,.2f}".format(x)


def cmd_plan(args, out):
    principal = parse_decimal(args.principal, "principal", allow_zero=False)
    rate = parse_decimal(args.rate, "rate", allow_zero=True)
    if rate > 100:
        raise LoanError("rate is a yearly percentage and cannot exceed 100")
    months = term_months(args)
    extra = parse_decimal(args.extra, "extra", allow_zero=True)
    lumps = {}
    for t in args.lump or []:
        k, v = parse_lump(t)
        lumps[k] = lumps.get(k, Decimal(0)) + v
    base = amortize(principal, rate, months)
    sb = summarize(base)
    out.write("Loan: %s at %s%% for %s\n" % (m2(principal), rate.normalize(), fmt_months(months)))
    out.write("Monthly payment: %s\n" % m2(sb["first_payment"]))
    out.write("Without extra payments: %s months, interest %s\n" % (sb["months"], m2(sb["total_interest"])))
    rows = base
    if extra > 0 or lumps:
        rows = amortize(principal, rate, months, extra, lumps)
        s = summarize(rows)
        out.write("With extra payments:    %s months, interest %s\n" % (s["months"], m2(s["total_interest"])))
        out.write("Interest saved: %s\n" % m2(sb["total_interest"] - s["total_interest"]))
        out.write("Paid off %s sooner\n" % fmt_months(sb["months"] - s["months"]))
    if args.csv:
        try:
            with open(args.csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["month", "payment", "interest", "principal", "balance"])
                for r in rows:
                    w.writerow([r[0]] + [str(x) for x in r[1:]])
        except OSError as e:
            raise LoanError("cannot write %s: %s" % (args.csv, e.strerror))
        out.write("Schedule written to %s (%d rows)\n" % (args.csv, len(rows)))
    return 0


def cmd_refi(args, out):
    bal = parse_decimal(args.balance, "balance", allow_zero=False)
    old_rate = parse_decimal(args.old_rate, "old rate")
    new_rate = parse_decimal(args.new_rate, "new rate")
    if old_rate > 100 or new_rate > 100:
        raise LoanError("rates are yearly percentages and cannot exceed 100")
    costs = parse_decimal(args.costs, "closing costs")
    if not (1 <= args.old_months_left <= MAX_MONTHS and 1 <= args.new_months <= MAX_MONTHS):
        raise LoanError("terms must be between 1 and %d months" % MAX_MONTHS)
    r = refinance(bal, old_rate, args.old_months_left, new_rate, args.new_months, costs)
    out.write("Current loan: payment %s, %s left, total still to pay %s\n" % (
        m2(r["old_payment"]), fmt_months(r["old"]["months"]), m2(r["total_cost_old"])))
    out.write("New loan:     payment %s, %s, total to pay %s (including %s closing costs)\n" % (
        m2(r["new_payment"]), fmt_months(r["new"]["months"]), m2(r["total_cost_new"]), m2(r["closing"])))
    diff = r["total_cost_old"] - r["total_cost_new"]
    out.write("Over the full terms the new loan costs %s %s\n" % (
        m2(abs(diff)), "less" if diff > 0 else "more"))
    be = r["breakeven_month"]
    if be is None:
        out.write("Break-even: never. Refinancing does not pay back its costs.\n")
        return 1
    out.write("Break-even: month %d (%s). Selling or refinancing again before then loses money.\n" % (be, fmt_months(be)))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="loanplan", description="Loan amortization, overpayments and refinance break-even.")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("plan", help="payment, total interest, effect of extra payments")
    a.add_argument("--principal", required=True)
    a.add_argument("--rate", required=True, help="yearly percentage, e.g. 6.5")
    a.add_argument("--years")
    a.add_argument("--months", type=int)
    a.add_argument("--extra", default="0", help="extra amount paid every month")
    a.add_argument("--lump", action="append", metavar="AMOUNT@MONTH", help="one-off extra payment, repeatable")
    a.add_argument("--csv", metavar="FILE", help="write the full schedule to a CSV file")
    a.set_defaults(func=cmd_plan)
    b = sub.add_parser("refi", help="refinance break-even")
    b.add_argument("--balance", required=True, help="current outstanding balance")
    b.add_argument("--old-rate", required=True)
    b.add_argument("--old-months-left", type=int, required=True)
    b.add_argument("--new-rate", required=True)
    b.add_argument("--new-months", type=int, required=True)
    b.add_argument("--costs", default="0", help="closing costs paid up front")
    b.set_defaults(func=cmd_refi)
    return p


def main(argv=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    p = build_parser()
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if not args.cmd:
        p.print_usage(err)
        err.write("loanplan: error: choose a command: plan or refi\n")
        return 2
    try:
        return args.func(args, out)
    except LoanError as e:
        err.write("loanplan: error: %s\n" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
