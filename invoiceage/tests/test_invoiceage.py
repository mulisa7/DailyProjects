import datetime as dt
import io
import os
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import invoiceage as ia

T = dt.date(2026, 11, 14)
CSV = "Invoice,Client,Amount,Due Date,Paid\n"


class Load(unittest.TestCase):
    def test_normal_and_paid_skipped(self):
        inv, pr = ia.load(CSV + "A1,X,\"1,200.50\",2026-10-01,\nA2,X,5,2026-10-01,2026-10-05\n")
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["amount"], Decimal("1200.50"))
        self.assertEqual(pr, [])

    def test_empty(self):
        for t in ("", "\n\n  \n"):
            with self.assertRaises(ia.InputError):
                ia.load(t)

    def test_header_only(self):
        inv, pr = ia.load(CSV)
        self.assertEqual(inv, [])

    def test_missing_column(self):
        with self.assertRaises(ia.InputError) as c:
            ia.load("Invoice,Client,Amount\nA,B,1\n")
        self.assertIn("due", str(c.exception))

    def test_aliases_bom(self):
        inv, _ = ia.load("﻿Invoice Number,Customer,Total,due_date\nA,B,$10,2026-01-01\n")
        self.assertEqual(inv[0]["client"], "B")

    def test_bad_rows_reported(self):
        inv, pr = ia.load(CSV + "A,X,abc,2026-01-01,\nB,X,5,31-31-2026,\n,X,5,2026-01-01,\nC,X,nan,2026-01-01,\nD,X,5,2026-01-01\n")
        self.assertEqual(len(inv), 1)
        self.assertEqual(len(pr), 4)

    def test_day_first_date_and_negative(self):
        inv, _ = ia.load(CSV + "A,X,(50.00),01/10/2026,\n")
        self.assertEqual(inv[0]["due"], dt.date(2026, 10, 1))
        self.assertEqual(inv[0]["amount"], Decimal("-50.00"))

    def test_short_row(self):
        inv, pr = ia.load(CSV + "A,X\n")
        self.assertEqual(len(pr), 1)


class Buckets(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual([ia.bucket_of(d) for d in (-5, 0, 1, 30, 31, 60, 61, 90, 91)], [0, 0, 1, 1, 2, 2, 3, 3, 4])

    def test_report_totals(self):
        inv, _ = ia.load(CSV + "A,X,10,2026-11-14,\nB,X,20,2026-11-13,\nC,Y,30,2026-08-01,\n")
        totals, counts, clients = ia.report(inv, T)
        self.assertEqual(totals[0], 10)
        self.assertEqual(totals[1], 20)
        self.assertEqual(totals[4], 30)
        self.assertEqual(clients["X"]["overdue"], 20)


class Output(unittest.TestCase):
    def test_empty_state(self):
        self.assertIn("No unpaid", ia.render([], T))
        self.assertIn("No reminders", ia.reminders([], T, None))

    def test_nothing_overdue(self):
        inv, _ = ia.load(CSV + "A,X,10,2026-12-01,\n")
        self.assertIn("nothing overdue", ia.render(inv, T))
        self.assertIn("No reminders", ia.reminders(inv, T, None))

    def test_reminder_tone_and_grouping(self):
        inv, _ = ia.load(CSV + "A,X,10,2026-11-10,\nB,X,5,2026-11-01,\nC,Y,7,2026-08-01,\n")
        r = ia.reminders(inv, T, "Sam")
        self.assertIn("Overdue invoices: B, A", r)
        self.assertIn("ignore this", r)
        self.assertIn("final reminder", r)
        self.assertIn("Total: 15.00", r)
        self.assertTrue(r.rstrip().endswith("Sam"))

    def test_tone(self):
        self.assertEqual([ia.tone(d) for d in (1, 14, 15, 45, 46)], ["friendly", "friendly", "firm", "firm", "final"])


class Cli(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(text)
        try:
            old = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
            try:
                code = ia.main([f.name, "--today", "2026-11-14", *args])
                return code, sys.stdout.getvalue(), sys.stderr.getvalue()
            finally:
                sys.stdout, sys.stderr = old
        finally:
            os.unlink(f.name)

    def test_exit_codes(self):
        self.assertEqual(self.run_cli(CSV + "A,X,1,2026-01-01,\n")[0], 1)
        self.assertEqual(self.run_cli(CSV + "A,X,1,2027-01-01,\n")[0], 0)
        self.assertEqual(self.run_cli("")[0], 2)

    def test_warning_exit(self):
        code, out, err = self.run_cli(CSV + "A,X,1,2027-01-01,\nB,X,zz,2027-01-01,\n")
        self.assertEqual(code, 3)
        self.assertIn("warning", err)

    def test_missing_file_and_bad_today(self):
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(ia.main(["/nonexistent.csv"]), 2)
            self.assertEqual(ia.main(["x", "--today", "nope"]), 2)
        finally:
            sys.stderr = old

    def test_stdin(self):
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = ia.main(["-", "--today", "2026-11-14"], stdin=io.StringIO(CSV + "A,X,1,2026-11-01,\n"))
        finally:
            sys.stdout = old
        self.assertEqual(code, 1)

    def test_binary_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\xff\xfe\x00\x80")
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(ia.main([f.name]), 2)
        finally:
            sys.stderr = old
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
