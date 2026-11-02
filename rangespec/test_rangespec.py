import datetime as dt
import io
import os
import unittest

import rangespec as rs

TODAY = dt.date(2026, 11, 2)  # a Monday


def d(text):
    return dt.date.fromisoformat(text)


def rng(expr, today=TODAY, week_start=0):
    r = rs.parse_range(expr, today, week_start)
    return r.start.isoformat(), r.end.isoformat()


class CalendarPeriods(unittest.TestCase):
    def test_today_yesterday_tomorrow(self):
        self.assertEqual(rng("today"), ("2026-11-02", "2026-11-02"))
        self.assertEqual(rng("yesterday"), ("2026-11-01", "2026-11-01"))
        self.assertEqual(rng("tomorrow"), ("2026-11-03", "2026-11-03"))

    def test_weeks_monday_start(self):
        self.assertEqual(rng("this week"), ("2026-11-02", "2026-11-08"))
        self.assertEqual(rng("last week"), ("2026-10-26", "2026-11-01"))
        self.assertEqual(rng("next week"), ("2026-11-09", "2026-11-15"))

    def test_weeks_sunday_start(self):
        self.assertEqual(rng("this week", week_start=6), ("2026-11-01", "2026-11-07"))

    def test_week_from_midweek(self):
        self.assertEqual(rng("this week", today=d("2026-11-05")), ("2026-11-02", "2026-11-08"))

    def test_months(self):
        self.assertEqual(rng("last month"), ("2026-10-01", "2026-10-31"))
        self.assertEqual(rng("this month"), ("2026-11-01", "2026-11-30"))
        self.assertEqual(rng("next month"), ("2026-12-01", "2026-12-31"))

    def test_month_crossing_year(self):
        self.assertEqual(rng("last month", today=d("2026-01-15")), ("2025-12-01", "2025-12-31"))
        self.assertEqual(rng("next month", today=d("2026-12-15")), ("2027-01-01", "2027-01-31"))

    def test_quarters(self):
        self.assertEqual(rng("this quarter"), ("2026-10-01", "2026-12-31"))
        self.assertEqual(rng("last quarter"), ("2026-07-01", "2026-09-30"))
        self.assertEqual(rng("last quarter", today=d("2026-02-10")), ("2025-10-01", "2025-12-31"))

    def test_years(self):
        self.assertEqual(rng("last year"), ("2025-01-01", "2025-12-31"))
        self.assertEqual(rng("this year"), ("2026-01-01", "2026-12-31"))

    def test_to_date_shortcuts(self):
        self.assertEqual(rng("ytd"), ("2026-01-01", "2026-11-02"))
        self.assertEqual(rng("year to date"), ("2026-01-01", "2026-11-02"))
        self.assertEqual(rng("mtd"), ("2026-11-01", "2026-11-02"))
        self.assertEqual(rng("qtd"), ("2026-10-01", "2026-11-02"))
        self.assertEqual(rng("month to date"), ("2026-11-01", "2026-11-02"))
        self.assertEqual(rng("quarter to date"), ("2026-10-01", "2026-11-02"))


class Rolling(unittest.TestCase):
    def test_last_days_includes_today(self):
        self.assertEqual(rng("last 7 days"), ("2026-10-27", "2026-11-02"))
        self.assertEqual(rng("last 1 day"), ("2026-11-02", "2026-11-02"))

    def test_last_weeks_months_years(self):
        self.assertEqual(rng("last 4 weeks"), ("2026-10-06", "2026-11-02"))
        self.assertEqual(rng("last 3 months"), ("2026-08-03", "2026-11-02"))
        self.assertEqual(rng("past 2 years"), ("2024-11-03", "2026-11-02"))

    def test_next(self):
        self.assertEqual(rng("next 3 days"), ("2026-11-02", "2026-11-04"))
        self.assertEqual(rng("next 2 months"), ("2026-11-02", "2027-01-01"))

    def test_month_end_clamping(self):
        self.assertEqual(rng("last 1 month", today=d("2026-03-31")), ("2026-03-01", "2026-03-31"))
        self.assertEqual(rng("1 month ago", today=d("2026-03-31")), ("2026-02-28", "2026-02-28"))

    def test_leap_day_year_shift(self):
        self.assertEqual(rng("1 year ago", today=d("2028-02-29")), ("2027-02-28", "2027-02-28"))

    def test_ago_and_from_now(self):
        self.assertEqual(rng("4 weeks ago"), ("2026-10-05", "2026-10-05"))
        self.assertEqual(rng("2 weeks from now"), ("2026-11-16", "2026-11-16"))
        self.assertEqual(rng("in 3 days"), ("2026-11-05", "2026-11-05"))
        self.assertEqual(rng("a week ago"), ("2026-10-26", "2026-10-26"))

    def test_case_and_spacing(self):
        self.assertEqual(rng("  LAST   Month "), ("2026-10-01", "2026-10-31"))


class Absolute(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(rng("2026-04-01"), ("2026-04-01", "2026-04-01"))

    def test_iso_month_and_year(self):
        self.assertEqual(rng("2024-02"), ("2024-02-01", "2024-02-29"))
        self.assertEqual(rng("2025-02"), ("2025-02-01", "2025-02-28"))
        self.assertEqual(rng("2025"), ("2025-01-01", "2025-12-31"))

    def test_quarter_forms(self):
        self.assertEqual(rng("q3 2026"), ("2026-07-01", "2026-09-30"))
        self.assertEqual(rng("2026-q1"), ("2026-01-01", "2026-03-31"))
        self.assertEqual(rng("Q2"), ("2026-04-01", "2026-06-30"))

    def test_month_names(self):
        self.assertEqual(rng("March 2025"), ("2025-03-01", "2025-03-31"))
        self.assertEqual(rng("sept 2025"), ("2025-09-01", "2025-09-30"))
        self.assertEqual(rng("feb"), ("2026-02-01", "2026-02-28"))
        self.assertEqual(rng("march 5"), ("2026-03-05", "2026-03-05"))
        self.assertEqual(rng("March 5th, 2025"), ("2025-03-05", "2025-03-05"))


class Ranges(unittest.TestCase):
    def test_iso_to_iso_is_inclusive(self):
        self.assertEqual(rng("2026-04-01 to 2026-05-01"), ("2026-04-01", "2026-05-01"))

    def test_periods_expand(self):
        self.assertEqual(rng("march 2026 to may 2026"), ("2026-03-01", "2026-05-31"))
        self.assertEqual(rng("q1 2025 through q2 2025"), ("2025-01-01", "2025-06-30"))

    def test_relative_endpoints(self):
        self.assertEqual(rng("4 weeks ago to 2 weeks from now"), ("2026-10-05", "2026-11-16"))

    def test_mixed_endpoints(self):
        self.assertEqual(rng("last month to today"), ("2026-10-01", "2026-11-02"))

    def test_between_and_from(self):
        self.assertEqual(rng("between 2026-01-10 and 2026-01-20"), ("2026-01-10", "2026-01-20"))
        self.assertEqual(rng("from 2026-01-10 to 2026-01-20"), ("2026-01-10", "2026-01-20"))

    def test_dotdot(self):
        self.assertEqual(rng("2026-01-10..2026-01-20"), ("2026-01-10", "2026-01-20"))
        self.assertEqual(rng("2026-01-10 .. 2026-01-20"), ("2026-01-10", "2026-01-20"))

    def test_since(self):
        self.assertEqual(rng("since march 2026"), ("2026-03-01", "2026-11-02"))

    def test_same_day_range(self):
        self.assertEqual(rng("2026-04-01 to 2026-04-01"), ("2026-04-01", "2026-04-01"))

    def test_range_properties(self):
        r = rs.parse_range("2026-02-27 to 2026-03-02", TODAY)
        self.assertEqual(r.days, 4)
        self.assertEqual(r.end_exclusive, dt.date(2026, 3, 3))


class Errors(unittest.TestCase):
    def check(self, expr, fragment):
        with self.assertRaises(rs.ParseError) as cm:
            rs.parse_range(expr, TODAY)
        self.assertIn(fragment, str(cm.exception))

    def test_empty(self):
        self.check("", "empty")
        self.check("   ", "empty")
        self.check(None, "empty")

    def test_gibberish(self):
        self.check("whenever", "cannot understand")
        self.check("last month please", "cannot understand")

    def test_impossible_dates(self):
        self.check("2026-02-30", "not a real calendar date")
        self.check("2025-02-29", "not a real calendar date")
        self.check("march 32", "not a real calendar date")
        self.check("2026-13", "no month 13")
        self.check("2026-00", "no month 0")

    def test_bad_quarter(self):
        self.check("q5 2026", "quarter must be 1 to 4")
        self.check("q0", "quarter must be 1 to 4")

    def test_zero_count(self):
        self.check("last 0 days", "at least 1")
        self.check("0 days ago", "at least 1")

    def test_negative_count_not_understood(self):
        self.check("last -3 days", "cannot understand")

    def test_reversed_range(self):
        self.check("2026-05-01 to 2026-04-01", "before it starts")

    def test_missing_side(self):
        self.check("to 2026-05-01", "cannot understand")
        self.check("2026-05-01 to ", "cannot understand")

    def test_too_many_separators(self):
        self.check("2026-01-01 to 2026-02-01 to 2026-03-01", "more than one")

    def test_since_in_future(self):
        self.check("since 2027-01-01", "after today")

    def test_overflow_is_a_parse_error(self):
        with self.assertRaises(rs.ParseError):
            rs.parse_range("9999 years ago", dt.date(9990, 1, 1))
        with self.assertRaises(rs.ParseError):
            rs.parse_range("in 100000 years", TODAY)


class Cli(unittest.TestCase):
    def go(self, argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        code = rs.run(argv, io.StringIO(stdin), out, err)
        return code, out.getvalue(), err.getvalue()

    def test_text_output(self):
        code, out, _ = self.go(["--today", "2026-11-02", "last", "month"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-10-01 to 2026-10-31 (31 days)\n")

    def test_single_day_text(self):
        _, out, _ = self.go(["--today", "2026-11-02", "yesterday"])
        self.assertEqual(out, "2026-11-01 (1 day)\n")

    def test_iso_json_sql(self):
        base = ["--today", "2026-11-02", "last month"]
        self.assertEqual(self.go(["--format", "iso"] + base)[1], "2026-10-01/2026-10-31\n")
        j = self.go(["--format", "json"] + base)[1]
        self.assertIn('"end_exclusive": "2026-11-01"', j)
        self.assertIn('"days": 31', j)
        sql = self.go(["--format", "sql", "--column", "o.created_at"] + base)[1]
        self.assertEqual(sql, "o.created_at >= '2026-10-01' AND o.created_at < '2026-11-01'\n")

    def test_days_format(self):
        _, out, _ = self.go(["--today", "2026-11-02", "--format", "days", "2026-02-27 to 2026-03-01"])
        self.assertEqual(out.split(), ["2026-02-27", "2026-02-28", "2026-03-01"])

    def test_days_format_too_large(self):
        code, out, err = self.go(["--today", "2026-11-02", "--format", "days", "1000 to 2100"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("too many", err)

    def test_week_start_option(self):
        _, out, _ = self.go(["--today", "2026-11-02", "--week-start", "sun", "this week"])
        self.assertTrue(out.startswith("2026-11-01 to 2026-11-07"))

    def test_no_expression_is_usage_error(self):
        code, _, err = self.go([])
        self.assertEqual(code, 2)
        self.assertIn("give a date range", err)

    def test_bad_today(self):
        code, _, err = self.go(["--today", "yesterday", "last month"])
        self.assertEqual(code, 2)
        self.assertIn("invalid --today", err)

    def test_bad_column_rejected(self):
        code, out, err = self.go(["--format", "sql", "--column", "a; DROP TABLE x", "today"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("invalid column", err)

    def test_parse_error_exit_code(self):
        code, out, err = self.go(["--today", "2026-11-02", "nonsense"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("cannot understand", err)

    def test_stdin_batch_continues_after_error(self):
        code, out, err = self.go(
            ["--today", "2026-11-02", "--format", "iso", "-"],
            stdin="last month\n\nnonsense\n2025\n",
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "2026-10-01/2026-10-31\n2025-01-01/2025-12-31\n")
        self.assertIn("nonsense", err)

    def test_stdin_empty(self):
        code, _, err = self.go(["-"], stdin="\n  \n")
        self.assertEqual(code, 2)
        self.assertIn("no expressions", err)

    def test_env_today(self):
        os.environ["RANGESPEC_TODAY"] = "2026-11-02"
        try:
            _, out, _ = self.go(["last month"])
        finally:
            del os.environ["RANGESPEC_TODAY"]
        self.assertTrue(out.startswith("2026-10-01"))

    def test_unusual_unicode_input(self):
        code, _, err = self.go(["--today", "2026-11-02", "last month—now"])
        self.assertEqual(code, 1)
        self.assertIn("cannot understand", err)


if __name__ == "__main__":
    unittest.main()
