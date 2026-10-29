import contextlib
import io
import os
import tempfile
import unittest
from decimal import Decimal

import bankcsv


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bankcsv.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class MoneyTests(unittest.TestCase):
    def check(self, text, expected):
        self.assertEqual(bankcsv.parse_money(text), Decimal(expected), text)

    def test_formats(self):
        self.check("1234.50", "1234.50")
        self.check("1,234.50", "1234.50")
        self.check("1.234,50", "1234.50")
        self.check("1 234,50", "1234.50")
        self.check("1 234,50", "1234.50")
        self.check("R 1,234.50", "1234.50")
        self.check("-45.00", "-45.00")
        self.check("(45.00)", "-45.00")
        self.check("45.00-", "-45.00")
        self.check("45.00 DR", "-45.00")
        self.check("45.00 CR", "45.00")
        self.check("+12", "12")
        self.check("12,5", "12.5")
        self.check("1,234", "1234")
        self.check("1,234,567", "1234567")
        self.check("$-3.10", "-3.10")

    def test_empty_is_none(self):
        self.assertIsNone(bankcsv.parse_money(""))
        self.assertIsNone(bankcsv.parse_money("   "))

    def test_garbage_raises(self):
        for bad in ("abc", "--", "1,2,3x", "12.34.56", "R"):
            with self.assertRaises(ValueError, msg=bad):
                bankcsv.parse_money(bad)


class DateTests(unittest.TestCase):
    def test_inference(self):
        self.assertTrue(bankcsv.infer_dayfirst(["13/01/2025", "02/02/2025"]))
        self.assertFalse(bankcsv.infer_dayfirst(["01/13/2025", "02/02/2025"]))
        self.assertIsNone(bankcsv.infer_dayfirst(["01/02/2025"]))
        self.assertIsNone(bankcsv.infer_dayfirst(["2025-01-13"]))

    def test_parse(self):
        p = bankcsv.parse_date
        self.assertEqual(p("2025-03-04", True).isoformat(), "2025-03-04")
        self.assertEqual(p("03/04/2025", True).isoformat(), "2025-04-03")
        self.assertEqual(p("03/04/2025", False).isoformat(), "2025-03-04")
        self.assertEqual(p("3 Apr 2025", True).isoformat(), "2025-04-03")
        self.assertEqual(p("20250403", True).isoformat(), "2025-04-03")
        self.assertEqual(p("03.04.25", True).isoformat(), "2025-04-03")

    def test_bad_dates(self):
        for bad in ("", "31/02/2025", "yesterday", "13/13/2025"):
            with self.assertRaises(ValueError, msg=bad):
                bankcsv.parse_date(bad, True)


class RuleTests(unittest.TestCase):
    def test_categorise_first_match_wins(self):
        rules = [("Food", ["checkers", "spar"]), ("Fuel", ["engen"])]
        self.assertEqual(bankcsv.categorise("CHECKERS HYPER", rules), "Food")
        self.assertEqual(bankcsv.categorise("Engen 1Stop", rules), "Fuel")
        self.assertEqual(bankcsv.categorise("???", rules), "Uncategorised")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def make(self, name, text, enc="utf-8"):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(text.encode(enc))
        return p

    def test_single_amount_column_with_preamble(self):
        p = self.make("a.csv",
                      "Account statement\nGenerated 2025-04-30\n\n"
                      "Date,Description,Amount,Balance\n"
                      "2025-04-01,Salary ACME,20000.00,20500.00\n"
                      "2025-04-02,CHECKERS  HYPER,-350.25,20149.75\n"
                      "Total,,19649.75,\n")
        rules = [("Food", ["checkers"])]
        txns, warns = bankcsv.normalise_file(p, rules)
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[1]["description"], "CHECKERS HYPER")
        self.assertEqual(txns[1]["category"], "Food")
        self.assertEqual(txns[1]["amount"], "-350.25")
        self.assertTrue(any("skipped 1" in w for w in warns))

    def test_debit_credit_columns_semicolon_cp1252(self):
        p = self.make("b.csv",
                      "Transaction Date;Narrative;Debit;Credit\n"
                      "13/04/2025;Café Océan;120,50;\n"
                      "14/04/2025;Refund;;20,00\n", enc="cp1252")
        txns, _ = bankcsv.normalise_file(p, [])
        self.assertEqual([t["amount"] for t in txns], ["-120.50", "20.00"])
        self.assertEqual(txns[0]["date"], "2025-04-13")
        self.assertEqual(txns[0]["description"], "Café Océan")

    def test_ambiguous_dates_warn_and_flags_change_result(self):
        text = "Date,Details,Amount\n03/04/2025,x,-1\n"
        p = self.make("c.csv", text)
        t, w = bankcsv.normalise_file(p, [])
        self.assertEqual(t[0]["date"], "2025-04-03")
        self.assertTrue(any("ambiguous" in x for x in w))
        t, _ = bankcsv.normalise_file(p, [], dayfirst=False)
        self.assertEqual(t[0]["date"], "2025-03-04")

    def test_invert(self):
        p = self.make("d.csv", "Date,Details,Amount\n2025-04-03,Shop,50.00\n")
        t, _ = bankcsv.normalise_file(p, [], invert=True)
        self.assertEqual(t[0]["amount"], "-50.00")

    def test_no_header_found(self):
        p = self.make("e.csv", "foo,bar\n1,2\n")
        with self.assertRaises(bankcsv.BankCsvError) as cm:
            bankcsv.normalise_file(p, [])
        self.assertIn("--map", str(cm.exception))

    def test_manual_map_headerless(self):
        p = self.make("f.csv", "x,y\n2025-04-03,Shop,-5.00\n")
        m = bankcsv.parse_manual_map("date=0,description=1,amount=2")
        t, _ = bankcsv.normalise_file(p, [], manual_map=m)
        self.assertEqual(t[0]["amount"], "-5.00")

    def test_wrong_mapping_fails_loudly(self):
        p = self.make("g.csv", "Date,Details,Amount\nnope,a,b\nnope,c,d\nnope,e,f\n")
        with self.assertRaises(bankcsv.BankCsvError):
            bankcsv.normalise_file(p, [])

    def test_bad_map_entry(self):
        for bad in ("date", "colour=1", "date=x"):
            with self.assertRaises(bankcsv.BankCsvError, msg=bad):
                bankcsv.parse_manual_map(bad)

    def test_bad_rules_file(self):
        p = self.make("r.txt", "Food checkers\n")
        with self.assertRaises(bankcsv.BankCsvError) as cm:
            bankcsv.load_rules(p)
        self.assertIn("line 1", str(cm.exception))

    def test_rules_comments_blank(self):
        p = self.make("r.txt", "# comment\n\nFood: Checkers, Spar\n")
        self.assertEqual(bankcsv.load_rules(p), [("Food", ["checkers", "spar"])])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = os.path.join(self.tmp.name, "bank_a.csv")
        self.b = os.path.join(self.tmp.name, "bank_b.csv")
        self.rules = os.path.join(self.tmp.name, "rules.txt")
        with open(self.a, "w") as f:
            f.write("Date,Description,Amount\n2025-04-01,Salary,1000\n2025-04-05,Checkers,-200\n")
        with open(self.b, "w") as f:
            f.write("Posting Date;Details;Money Out;Money In\n2025-05-02;Engen;150,00;\n"
                    "2025-05-03;Mystery Shop;75,00;\n")
        with open(self.rules, "w") as f:
            f.write("Food: checkers\nFuel: engen\n")

    def test_normalize_two_banks_to_file(self):
        out = os.path.join(self.tmp.name, "all.csv")
        code, _, err = run("normalize", self.a, self.b, "--rules", self.rules, "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("wrote 4", err)
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "date,description,amount,balance,category,source")
        self.assertIn("2025-05-02,Engen,-150.00,,Fuel,bank_b.csv", lines)

    def test_normalize_stdout(self):
        code, out, _ = run("normalize", self.a)
        self.assertEqual(code, 0)
        self.assertIn("2025-04-01,Salary,1000.00", out)

    def test_summary(self):
        code, out, _ = run("summary", self.a, self.b, "--rules", self.rules)
        self.assertEqual(code, 0)
        self.assertIn("2025-04", out)
        self.assertIn("Food", out)
        self.assertIn("Mystery Shop", out)  # listed as uncategorised

    def test_missing_file(self):
        code, _, err = run("summary", os.path.join(self.tmp.name, "nope.csv"))
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_empty_file(self):
        p = os.path.join(self.tmp.name, "empty.csv")
        open(p, "w").close()
        code, _, err = run("normalize", p)
        self.assertEqual(code, 2)
        self.assertIn("empty", err)

    def test_summary_no_transactions(self):
        self.assertEqual(bankcsv.format_summary([]), "No transactions.")

    def test_unwritable_output(self):
        code, _, err = run("normalize", self.a, "-o", os.path.join(self.tmp.name, "no", "x.csv"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
