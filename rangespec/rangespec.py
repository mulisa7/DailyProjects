#!/usr/bin/env python3
"""rangespec: turn a plain-English date range into concrete start and end dates."""

import argparse
import calendar
import datetime as dt
import json
import os
import re
import sys

MAX_DAY_LIST = 100000
WEEK_STARTS = {"mon": 0, "sun": 6}

MONTHS = {}
for _i, _name in enumerate(calendar.month_name):
    if _name:
        MONTHS[_name.lower()] = _i
for _i, _name in enumerate(calendar.month_abbr):
    if _name:
        MONTHS[_name.lower()] = _i
MONTHS["sept"] = 9

TO_DATE = ("year to date", "month to date", "quarter to date")
UNIT = r"(day|week|month|year)s?"


class ParseError(ValueError):
    pass


class DateRange:
    def __init__(self, start, end):
        self.start = start
        self.end = end

    @property
    def end_exclusive(self):
        return self.end + dt.timedelta(days=1)

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def __eq__(self, other):
        return (self.start, self.end) == (other.start, other.end)

    def __repr__(self):
        return "DateRange(%s, %s)" % (self.start, self.end)


def add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    month += 1
    if year < 1 or year > 9999:
        raise ParseError("date is outside the supported range (year 1 to 9999)")
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def shift(d, n, unit):
    if unit == "day":
        return d + dt.timedelta(days=n)
    if unit == "week":
        return d + dt.timedelta(weeks=n)
    if unit == "month":
        return add_months(d, n)
    return add_months(d, 12 * n)


def month_span(year, month):
    last = calendar.monthrange(year, month)[1]
    return DateRange(dt.date(year, month, 1), dt.date(year, month, last))


def quarter_span(year, q):
    if q < 1 or q > 4:
        raise ParseError("quarter must be 1 to 4, got %d" % q)
    first = month_span(year, 3 * q - 2)
    last = month_span(year, 3 * q)
    return DateRange(first.start, last.end)


def year_span(year):
    return DateRange(dt.date(year, 1, 1), dt.date(year, 12, 31))


def week_span(d, week_start):
    start = d - dt.timedelta(days=(d.weekday() - week_start) % 7)
    return DateRange(start, start + dt.timedelta(days=6))


def current_period(unit, d, week_start):
    if unit == "day":
        return DateRange(d, d)
    if unit == "week":
        return week_span(d, week_start)
    if unit == "month":
        return month_span(d.year, d.month)
    if unit == "quarter":
        return quarter_span(d.year, (d.month - 1) // 3 + 1)
    return year_span(d.year)


def move_period(unit, d, step, week_start):
    if unit == "day":
        return d + dt.timedelta(days=step)
    if unit == "week":
        return d + dt.timedelta(weeks=step)
    if unit == "month":
        return add_months(d, step)
    if unit == "quarter":
        return add_months(d, 3 * step)
    return add_months(d, 12 * step)


def make_date(year, month, day, text):
    try:
        return dt.date(year, month, day)
    except ValueError:
        raise ParseError("'%s' is not a real calendar date" % text)


def count_arg(raw, text):
    n = 1 if raw in ("a", "an") else int(raw)
    if n < 1:
        raise ParseError("count must be at least 1 in '%s'" % text)
    return n


def resolve(text, today, week_start):
    """Resolve one side of a range to a DateRange (a single day is a one-day range)."""
    t = text.strip()
    if not t:
        raise ParseError("empty date expression")

    if t in ("today", "now"):
        return DateRange(today, today)
    if t == "yesterday":
        d = today - dt.timedelta(days=1)
        return DateRange(d, d)
    if t == "tomorrow":
        d = today + dt.timedelta(days=1)
        return DateRange(d, d)

    if t in ("ytd", "year to date"):
        return DateRange(dt.date(today.year, 1, 1), today)
    if t in ("mtd", "month to date"):
        return DateRange(dt.date(today.year, today.month, 1), today)
    if t in ("qtd", "quarter to date"):
        return DateRange(current_period("quarter", today, week_start).start, today)

    m = re.fullmatch(r"(this|current|last|previous|prev|next) (day|week|month|quarter|year)", t)
    if m:
        which, unit = m.groups()
        step = {"this": 0, "current": 0, "next": 1}.get(which, -1)
        anchor = move_period(unit, today, step, week_start) if step else today
        return current_period(unit, anchor, week_start)

    m = re.fullmatch(r"(last|past|previous|prev|next) (\d+) " + UNIT, t)
    if m:
        which, raw, unit = m.groups()
        n = count_arg(raw, t)
        if which == "next":
            return DateRange(today, shift(today, n, unit) - dt.timedelta(days=1))
        return DateRange(shift(today, -n, unit) + dt.timedelta(days=1), today)

    m = re.fullmatch(r"(\d+|an?) " + UNIT + r" ago", t)
    if m:
        d = shift(today, -count_arg(m.group(1), t), m.group(2))
        return DateRange(d, d)

    m = re.fullmatch(r"(?:in (\d+|an?) " + UNIT + r"|(\d+|an?) " + UNIT + r" (?:from now|from today|hence))", t)
    if m:
        g = m.groups()
        raw, unit = (g[0], g[1]) if g[0] else (g[2], g[3])
        d = shift(today, count_arg(raw, t), unit)
        return DateRange(d, d)

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        d = make_date(*map(int, m.groups()), t)
        return DateRange(d, d)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m:
        year, month = map(int, m.groups())
        if not 1 <= month <= 12:
            raise ParseError("'%s' has no month %d" % (t, month))
        return month_span(year, month)
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        year = int(t)
        if year < 1:
            raise ParseError("year must be 1 or later")
        return year_span(year)

    m = re.fullmatch(r"q(\d+)(?: (\d{4}))?", t)
    if m:
        q = int(m.group(1))
        year = int(m.group(2)) if m.group(2) else today.year
        return quarter_span(year, q)
    m = re.fullmatch(r"(\d{4})[- ]?q(\d+)", t)
    if m:
        return quarter_span(int(m.group(1)), int(m.group(2)))

    m = re.fullmatch(r"([a-z]+)\.? (\d{4})", t)
    if m and m.group(1) in MONTHS:
        return month_span(int(m.group(2)), MONTHS[m.group(1)])
    m = re.fullmatch(r"([a-z]+)\.?", t)
    if m and m.group(1) in MONTHS:
        return month_span(today.year, MONTHS[m.group(1)])
    m = re.fullmatch(r"([a-z]+)\.? (\d{1,2})(?:st|nd|rd|th)?(?:,? (\d{4}))?", t)
    if m and m.group(1) in MONTHS:
        year = int(m.group(3)) if m.group(3) else today.year
        d = make_date(year, MONTHS[m.group(1)], int(m.group(2)), t)
        return DateRange(d, d)

    raise ParseError("cannot understand '%s'" % t)


def parse_range(expr, today, week_start=0):
    """Parse an expression such as 'last 4 weeks' or 'march 2026 to may 2026'."""
    if expr is None or not expr.strip():
        raise ParseError("empty expression")
    text = re.sub(r"\s+", " ", expr.strip().lower())

    m = re.fullmatch(r"between (.+?) and (.+)", text)
    if text in TO_DATE:
        return resolve(text, today, week_start)
    if m:
        parts = [m.group(1), m.group(2)]
    else:
        m = re.fullmatch(r"since (.+)", text)
        if m:
            first = resolve(m.group(1), today, week_start)
            if first.start > today:
                raise ParseError("'%s' starts after today" % m.group(1))
            return DateRange(first.start, today)
        if text.startswith("from "):
            text = text[5:]
        parts = re.split(r"\s+(?:to|through|thru)\s+|\s*\.\.\s*", text)

    if len(parts) == 1:
        return resolve(parts[0], today, week_start)
    if len(parts) > 2:
        raise ParseError("more than one range separator in '%s'" % expr.strip())
    if not parts[0].strip() or not parts[1].strip():
        raise ParseError("a range needs a start and an end")
    first = resolve(parts[0], today, week_start)
    second = resolve(parts[1], today, week_start)
    if first.start > second.end:
        raise ParseError("range ends (%s) before it starts (%s)" % (second.end, first.start))
    return DateRange(first.start, second.end)


def format_range(expr, rng, fmt, column):
    if fmt == "iso":
        return "%s/%s" % (rng.start, rng.end)
    if fmt == "json":
        return json.dumps({
            "input": expr,
            "start": rng.start.isoformat(),
            "end": rng.end.isoformat(),
            "end_exclusive": rng.end_exclusive.isoformat(),
            "days": rng.days,
        })
    if fmt == "sql":
        return "%s >= '%s' AND %s < '%s'" % (column, rng.start, column, rng.end_exclusive)
    if fmt == "days":
        if rng.days > MAX_DAY_LIST:
            raise ParseError("range has %d days, too many to list (limit %d)" % (rng.days, MAX_DAY_LIST))
        return "\n".join(
            (rng.start + dt.timedelta(days=i)).isoformat() for i in range(rng.days)
        )
    if rng.days == 1:
        return "%s (1 day)" % rng.start
    return "%s to %s (%d days)" % (rng.start, rng.end, rng.days)


def build_parser():
    p = argparse.ArgumentParser(
        prog="rangespec",
        description="Turn a plain-English date range into start and end dates.",
        epilog="Use '-' as the expression to read one expression per line from stdin.",
    )
    p.add_argument("expression", nargs="*", help="e.g. last 4 weeks, 'march 2026 to may 2026'")
    p.add_argument("--today", help="treat this YYYY-MM-DD date as today (or set RANGESPEC_TODAY)")
    p.add_argument("--week-start", choices=sorted(WEEK_STARTS), default="mon",
                   help="first day of the week (default mon)")
    p.add_argument("--format", choices=["text", "iso", "json", "sql", "days"], default="text",
                   help="output format (default text)")
    p.add_argument("--column", default="date", help="column name for --format sql (default date)")
    return p


def run(argv, stdin, stdout, stderr):
    args = build_parser().parse_args(argv)

    raw_today = args.today or os.environ.get("RANGESPEC_TODAY")
    if raw_today:
        try:
            today = dt.date.fromisoformat(raw_today)
        except ValueError:
            stderr.write("rangespec: invalid --today value '%s', expected YYYY-MM-DD\n" % raw_today)
            return 2
    else:
        today = dt.date.today()

    if args.format == "sql" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", args.column):
        stderr.write("rangespec: invalid column name '%s'\n" % args.column)
        return 2

    if args.expression == ["-"]:
        lines = [ln.strip() for ln in stdin.read().splitlines()]
        exprs = [ln for ln in lines if ln]
        if not exprs:
            stderr.write("rangespec: no expressions on stdin\n")
            return 2
    elif args.expression:
        exprs = [" ".join(args.expression)]
    else:
        stderr.write("rangespec: give a date range expression, e.g. rangespec last month\n")
        return 2

    failed = False
    for expr in exprs:
        try:
            rng = parse_range(expr, today, WEEK_STARTS[args.week_start])
            stdout.write(format_range(expr, rng, args.format, args.column) + "\n")
        except ParseError as exc:
            stderr.write("rangespec: %s\n" % exc)
            failed = True
    return 1 if failed else 0


def main():
    sys.exit(run(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr))


if __name__ == "__main__":
    main()
