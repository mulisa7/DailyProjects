import io, os, tempfile, unittest
from decimal import Decimal as D
import loanplan as lp


def run(*argv):
    o, e = io.StringIO(), io.StringIO()
    code = lp.main(list(argv), o, e)
    return code, o.getvalue(), e.getvalue()


class Payment(unittest.TestCase):
    def test_known_value(self):
        self.assertEqual(lp.monthly_payment(200000, D("6.5"), 360), D("1264.14"))

    def test_zero_rate(self):
        self.assertEqual(lp.monthly_payment(12000, 0, 12), D("1000.00"))

    def test_bad_term(self):
        with self.assertRaises(lp.LoanError):
            lp.monthly_payment(1000, 5, 0)
        with self.assertRaises(lp.LoanError):
            lp.monthly_payment(1000, 5, 5000)

    def test_bad_principal(self):
        with self.assertRaises(lp.LoanError):
            lp.monthly_payment(0, 5, 12)


class Amortize(unittest.TestCase):
    def test_ends_at_zero_with_term(self):
        rows = lp.amortize(200000, D("6.5"), 360)
        self.assertEqual(len(rows), 360)
        self.assertEqual(rows[-1][4], 0)

    def test_principal_sums_to_loan(self):
        rows = lp.amortize(50000, D("4.2"), 60)
        self.assertEqual(sum(r[3] for r in rows), D("50000.00"))

    def test_extra_shortens_and_saves(self):
        base = lp.summarize(lp.amortize(200000, D("6.5"), 360))
        more = lp.summarize(lp.amortize(200000, D("6.5"), 360, extra=D(200)))
        self.assertLess(more["months"], base["months"])
        self.assertLess(more["total_interest"], base["total_interest"])

    def test_lump_sum(self):
        base = lp.summarize(lp.amortize(10000, D(5), 60))
        lump = lp.summarize(lp.amortize(10000, D(5), 60, lumps={3: D(5000)}))
        self.assertLess(lump["months"], base["months"])

    def test_huge_extra_single_payment(self):
        rows = lp.amortize(1000, D(5), 12, extra=D(5000))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4], 0)

    def test_zero_rate_no_interest(self):
        s = lp.summarize(lp.amortize(1200, 0, 12))
        self.assertEqual(s["total_interest"], 0)

    def test_negative_extra(self):
        with self.assertRaises(lp.LoanError):
            lp.amortize(1000, 5, 12, extra=D(-1))

    def test_one_month_loan(self):
        rows = lp.amortize(1000, D(12), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], D("1010.00"))


class Refi(unittest.TestCase):
    def test_breakeven_found(self):
        r = lp.refinance(200000, D("7.5"), 300, D("5.5"), 300, 4000)
        self.assertIsNotNone(r["breakeven_month"])
        self.assertGreater(r["breakeven_month"], 1)
        self.assertLess(r["new_payment"], r["old_payment"])

    def test_never_when_rate_same_and_costs(self):
        r = lp.refinance(100000, D(5), 240, D(5), 240, 3000)
        self.assertIsNone(r["breakeven_month"])

    def test_no_costs_lower_rate_is_immediate(self):
        r = lp.refinance(100000, D(7), 240, D(5), 240, 0)
        self.assertEqual(r["breakeven_month"], 1)

    def test_higher_rate_never(self):
        r = lp.refinance(100000, D(4), 240, D(6), 240, 0)
        self.assertIsNone(r["breakeven_month"])


class Parsing(unittest.TestCase):
    def test_lump(self):
        self.assertEqual(lp.parse_lump("5000@12"), (12, D(5000)))
        for bad in ("5000", "x@3", "100@0", "100@a", "0@3"):
            with self.assertRaises(lp.LoanError):
                lp.parse_lump(bad)

    def test_decimal_junk(self):
        for bad in ("abc", "", "-5", "nan", "inf"):
            with self.assertRaises(lp.LoanError):
                lp.parse_decimal(bad, "x")

    def test_commas_and_dollar(self):
        self.assertEqual(lp.parse_decimal("$200,000", "x"), D(200000))

    def test_fmt_months(self):
        self.assertEqual(lp.fmt_months(0), "0 months")
        self.assertEqual(lp.fmt_months(13), "1 year 1 month")
        self.assertEqual(lp.fmt_months(24), "2 years")


class Cli(unittest.TestCase):
    def test_plan_output(self):
        code, out, _ = run("plan", "--principal", "200000", "--rate", "6.5", "--years", "30")
        self.assertEqual(code, 0)
        self.assertIn("1,264.14", out)

    def test_plan_extra(self):
        code, out, _ = run("plan", "--principal", "200000", "--rate", "6.5", "--years", "30", "--extra", "200", "--lump", "5000@12")
        self.assertEqual(code, 0)
        self.assertIn("Interest saved", out)

    def test_missing_term(self):
        code, _, err = run("plan", "--principal", "1000", "--rate", "5")
        self.assertEqual(code, 2)
        self.assertIn("term is required", err)

    def test_both_terms(self):
        code, _, err = run("plan", "--principal", "1000", "--rate", "5", "--years", "1", "--months", "12")
        self.assertEqual(code, 2)

    def test_fractional_years(self):
        code, _, _ = run("plan", "--principal", "1000", "--rate", "5", "--years", "2.5")
        self.assertEqual(code, 0)
        code, _, err = run("plan", "--principal", "1000", "--rate", "5", "--years", "2.55")
        self.assertEqual(code, 2)

    def test_bad_number(self):
        code, _, err = run("plan", "--principal", "lots", "--rate", "5", "--years", "1")
        self.assertEqual(code, 2)
        self.assertIn("principal", err)

    def test_rate_over_100(self):
        code, _, _ = run("plan", "--principal", "1000", "--rate", "150", "--years", "1")
        self.assertEqual(code, 2)

    def test_no_command(self):
        code, _, err = run()
        self.assertEqual(code, 2)

    def test_unknown_flag(self):
        code, _, _ = run("plan", "--bogus")
        self.assertEqual(code, 2)

    def test_csv_written(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.csv")
            code, out, _ = run("plan", "--principal", "1000", "--rate", "5", "--months", "12", "--csv", path)
            self.assertEqual(code, 0)
            with open(path) as f:
                lines = f.read().strip().splitlines()
            self.assertEqual(len(lines), 13)

    def test_csv_unwritable(self):
        code, _, err = run("plan", "--principal", "1000", "--rate", "5", "--months", "12", "--csv", "/nonexistent-dir/x.csv")
        self.assertEqual(code, 2)
        self.assertIn("cannot write", err)

    def test_refi_cli(self):
        code, out, _ = run("refi", "--balance", "200000", "--old-rate", "7.5", "--old-months-left", "300",
                           "--new-rate", "5.5", "--new-months", "300", "--costs", "4000")
        self.assertEqual(code, 0)
        self.assertIn("Break-even: month", out)

    def test_refi_never_exit_1(self):
        code, out, _ = run("refi", "--balance", "100000", "--old-rate", "5", "--old-months-left", "240",
                           "--new-rate", "5", "--new-months", "240", "--costs", "3000")
        self.assertEqual(code, 1)
        self.assertIn("never", out)

    def test_refi_bad_term(self):
        code, _, _ = run("refi", "--balance", "1000", "--old-rate", "5", "--old-months-left", "0",
                         "--new-rate", "4", "--new-months", "12")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
