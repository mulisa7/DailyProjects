import io
import json
import os
import tempfile
import unittest

import spflint as s


def msgs(findings, level=None):
    return [f.message for f in findings if level is None or f.level == level]


def has(findings, level, text):
    return any(text in m for m in msgs(findings, level))


class SpfBasics(unittest.TestCase):
    def test_clean_record(self):
        f, n = s.lint_spf("v=spf1 ip4:192.0.2.0/24 mx -all")
        self.assertEqual(msgs(f), [])
        self.assertEqual(n, 1)

    def test_missing_version(self):
        f, _ = s.lint_spf("ip4:1.2.3.4 -all")
        self.assertTrue(has(f, "error", "must start with"))

    def test_empty_string(self):
        f, _ = s.lint_spf("")
        self.assertTrue(has(f, "error", "must start with"))

    def test_version_case_insensitive(self):
        f, _ = s.lint_spf("V=SPF1 -all")
        self.assertEqual(msgs(f, "error"), [])

    def test_unknown_mechanism(self):
        f, _ = s.lint_spf("v=spf1 inlcude:x.com -all")
        self.assertTrue(has(f, "error", "unknown mechanism"))

    def test_bad_ip4(self):
        f, _ = s.lint_spf("v=spf1 ip4:300.1.1.1 -all")
        self.assertTrue(has(f, "error", "not a valid address"))

    def test_ip4_with_ipv6_address(self):
        f, _ = s.lint_spf("v=spf1 ip4:2001:db8::1 -all")
        self.assertTrue(has(f, "error", "IPv6"))

    def test_ip6_ok(self):
        f, _ = s.lint_spf("v=spf1 ip6:2001:db8::/32 -all")
        self.assertEqual(msgs(f, "error"), [])

    def test_host_bits_warning(self):
        f, _ = s.lint_spf("v=spf1 ip4:192.0.2.5/24 -all")
        self.assertTrue(has(f, "warning", "host bits"))

    def test_ip4_zero_prefix(self):
        f, _ = s.lint_spf("v=spf1 ip4:0.0.0.0/0 -all")
        self.assertTrue(has(f, "warning", "every IPv4"))

    def test_plus_all_is_error(self):
        f, _ = s.lint_spf("v=spf1 a all")
        self.assertTrue(has(f, "error", "any server"))

    def test_question_all_warns(self):
        f, _ = s.lint_spf("v=spf1 a ?all")
        self.assertTrue(has(f, "warning", "neutral"))

    def test_softfail_warns(self):
        f, _ = s.lint_spf("v=spf1 a ~all")
        self.assertTrue(has(f, "warning", "soft fail"))

    def test_no_all(self):
        f, _ = s.lint_spf("v=spf1 a")
        self.assertTrue(has(f, "warning", "no 'all'"))

    def test_redirect_is_fine_without_all(self):
        f, n = s.lint_spf("v=spf1 redirect=_spf.example.com")
        self.assertEqual(msgs(f, "error"), [])
        self.assertFalse(has(f, "warning", "no 'all'"))
        self.assertEqual(n, 1)

    def test_redirect_ignored_with_all(self):
        f, _ = s.lint_spf("v=spf1 -all redirect=x.com")
        self.assertTrue(has(f, "warning", "redirect"))

    def test_mechanism_after_all(self):
        f, _ = s.lint_spf("v=spf1 -all ip4:1.2.3.4")
        self.assertTrue(has(f, "warning", "after 'all'"))

    def test_ptr_deprecated(self):
        f, n = s.lint_spf("v=spf1 ptr -all")
        self.assertTrue(has(f, "warning", "deprecated"))
        self.assertEqual(n, 1)

    def test_include_without_domain(self):
        f, _ = s.lint_spf("v=spf1 include: -all")
        self.assertTrue(has(f, "error", "include"))

    def test_include_bad_domain(self):
        f, _ = s.lint_spf("v=spf1 include:not a domain -all")
        self.assertTrue(has(f, "error", "unknown mechanism"))
        f, _ = s.lint_spf("v=spf1 include:bad..com -all")
        self.assertTrue(has(f, "error", "include"))

    def test_all_with_argument(self):
        f, _ = s.lint_spf("v=spf1 all:foo")
        self.assertTrue(has(f, "error", "takes no argument"))

    def test_cidr_ranges_on_a_and_mx(self):
        f, _ = s.lint_spf("v=spf1 a/33 -all")
        self.assertTrue(has(f, "error", "outside 0-32"))
        f, _ = s.lint_spf("v=spf1 mx:mail.example.com/24//64 -all")
        self.assertEqual(msgs(f, "error"), [])
        f, _ = s.lint_spf("v=spf1 a//129 -all")
        self.assertTrue(has(f, "error", "outside 0-128"))

    def test_qualifier_only(self):
        f, _ = s.lint_spf("v=spf1 + -all")
        self.assertTrue(has(f, "error", "no mechanism"))

    def test_duplicate_redirect(self):
        f, _ = s.lint_spf("v=spf1 redirect=a.com redirect=b.com")
        self.assertTrue(has(f, "error", "more than once"))

    def test_unicode_garbage(self):
        f, _ = s.lint_spf("v=spf1 éè -all")
        self.assertTrue(has(f, "error", "unknown mechanism"))


class SpfLookups(unittest.TestCase):
    def test_count_without_zone_warns_about_includes(self):
        f, n = s.lint_spf("v=spf1 include:a.com include:b.com -all")
        self.assertEqual(n, 2)
        self.assertTrue(has(f, "warning", "not expanded"))

    def test_over_limit_direct(self):
        rec = "v=spf1 " + " ".join(f"include:s{i}.example.com" for i in range(11)) + " -all"
        f, n = s.lint_spf(rec)
        self.assertEqual(n, 11)
        self.assertTrue(has(f, "error", "11 DNS lookups"))

    def test_exactly_ten_warns(self):
        rec = "v=spf1 " + " ".join(f"a:h{i}.example.com" for i in range(10)) + " -all"
        f, n = s.lint_spf(rec)
        self.assertEqual(n, 10)
        self.assertTrue(has(f, "warning", "exactly at the limit"))
        self.assertEqual(msgs(f, "error"), [])

    def test_ip_mechanisms_are_free(self):
        rec = "v=spf1 " + " ".join(f"ip4:10.0.{i}.1" for i in range(30)) + " -all"
        _, n = s.lint_spf(rec)
        self.assertEqual(n, 0)

    def test_nested_zone_expansion(self):
        zone = {"a.com": "v=spf1 include:b.com mx -all", "b.com": "v=spf1 a a a a a a a a -all"}
        f, n = s.lint_spf("v=spf1 include:a.com -all", zone)
        self.assertEqual(n, 1 + 2 + 8)
        self.assertTrue(has(f, "error", "11 DNS lookups"))

    def test_loop_detected(self):
        zone = {"a.com": "v=spf1 include:b.com -all", "b.com": "v=spf1 include:a.com -all"}
        f, _ = s.lint_spf("v=spf1 include:a.com -all", zone)
        self.assertTrue(has(f, "error", "loop"))

    def test_missing_zone_entry(self):
        f, _ = s.lint_spf("v=spf1 include:gone.example.com -all", {})
        self.assertTrue(has(f, "warning", "not in the zone file"))

    def test_error_inside_include_reported(self):
        zone = {"a.com": "v=spf1 bogus -all"}
        f, _ = s.lint_spf("v=spf1 include:a.com -all", zone)
        self.assertTrue(has(f, "error", "in 'a.com'"))

    def test_long_record_warnings(self):
        rec = "v=spf1 " + " ".join(f"ip4:10.1.{i}.{j}" for i in range(4) for j in range(30)) + " -all"
        f, _ = s.lint_spf(rec)
        self.assertTrue(has(f, "warning", "split into several"))
        self.assertTrue(has(f, "warning", "truncated"))


class Dmarc(unittest.TestCase):
    def test_good(self):
        f = s.lint_dmarc("v=DMARC1; p=reject; rua=mailto:d@example.com; adkim=s")
        self.assertEqual(msgs(f), [])

    def test_missing_p(self):
        f = s.lint_dmarc("v=DMARC1; rua=mailto:d@example.com")
        self.assertTrue(has(f, "error", "'p' is missing"))

    def test_bad_version(self):
        f = s.lint_dmarc("p=none")
        self.assertTrue(has(f, "error", "v=DMARC1"))

    def test_policy_value(self):
        f = s.lint_dmarc("v=DMARC1; p=block")
        self.assertTrue(has(f, "error", "none, quarantine or reject"))

    def test_p_none_warns(self):
        f = s.lint_dmarc("v=DMARC1; p=none; rua=mailto:d@example.com")
        self.assertTrue(has(f, "warning", "only monitors"))

    def test_pct(self):
        self.assertTrue(has(s.lint_dmarc("v=DMARC1; p=reject; pct=150; rua=mailto:a@b.co"), "error", "pct"))
        self.assertTrue(has(s.lint_dmarc("v=DMARC1; p=reject; pct=abc; rua=mailto:a@b.co"), "error", "pct"))
        self.assertTrue(has(s.lint_dmarc("v=DMARC1; p=reject; pct=50; rua=mailto:a@b.co"), "warning", "pct=50"))

    def test_bad_rua(self):
        f = s.lint_dmarc("v=DMARC1; p=reject; rua=d@example.com")
        self.assertTrue(has(f, "error", "mailto"))

    def test_multiple_rua_and_size_suffix(self):
        f = s.lint_dmarc("v=DMARC1; p=reject; rua=mailto:a@x.com!10m, mailto:b@x.com")
        self.assertEqual(msgs(f), [])

    def test_no_rua_warns(self):
        f = s.lint_dmarc("v=DMARC1; p=reject")
        self.assertTrue(has(f, "warning", "rua"))

    def test_alignment_and_ri(self):
        f = s.lint_dmarc("v=DMARC1; p=reject; adkim=x; ri=0; rua=mailto:a@b.co")
        self.assertTrue(has(f, "error", "adkim"))
        self.assertTrue(has(f, "error", "'ri'"))

    def test_duplicate_tag_and_no_equals(self):
        f = s.lint_dmarc("v=DMARC1; p=none; p=reject; junk; rua=mailto:a@b.co")
        self.assertTrue(has(f, "error", "more than once"))
        self.assertTrue(has(f, "error", "no '='"))

    def test_trailing_semicolon(self):
        f = s.lint_dmarc("v=DMARC1; p=reject; rua=mailto:a@b.co;")
        self.assertEqual(msgs(f), [])


class Loading(unittest.TestCase):
    def test_strip_quotes(self):
        self.assertEqual(s.strip_txt_quotes('"v=spf1 a" " -all"'), "v=spf1 a -all")
        self.assertEqual(s.strip_txt_quotes("v=spf1 a -all"), "v=spf1 a -all")

    def test_load_records_skips_comments_and_blanks(self):
        got = s.load_records('# note\n\n"v=spf1 -all"\n  v=DMARC1; p=none\n')
        self.assertEqual(got, ["v=spf1 -all", "v=DMARC1; p=none"])

    def test_multiple_spf_records(self):
        res = s.lint_records(["v=spf1 -all", "v=spf1 a -all"])
        self.assertTrue(any(has(r["findings"], "error", "2 SPF records") for r in res))

    def test_unknown_record(self):
        res = s.lint_records(["google-site-verification=abc"])
        self.assertEqual(res[0]["kind"], "unknown")

    def test_zone_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "z.json")
            with open(p, "w") as fh:
                fh.write("[1,2]")
            with self.assertRaises(ValueError):
                s.load_zone(p)
            with open(p, "w") as fh:
                fh.write("{oops")
            with self.assertRaises(ValueError):
                s.load_zone(p)
            with self.assertRaises(ValueError):
                s.load_zone(os.path.join(d, "missing.json"))
            with open(p, "w") as fh:
                fh.write('{"A.com.": "\\"v=spf1 -all\\""}')
            self.assertEqual(s.load_zone(p), {"a.com": "v=spf1 -all"})


class Cli(unittest.TestCase):
    def run_cli(self, argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        code = s.main(argv, io.StringIO(stdin), out, err)
        return code, out.getvalue(), err.getvalue()

    def test_clean_exit_zero(self):
        code, out, _ = self.run_cli(["v=spf1 ip4:192.0.2.1 -all"])
        self.assertEqual(code, 0)
        self.assertIn("ok", out)

    def test_error_exit_one(self):
        code, out, _ = self.run_cli(["v=spf1 +all"])
        self.assertEqual(code, 1)
        self.assertIn("ERROR", out)

    def test_warning_only_zero_unless_strict(self):
        self.assertEqual(self.run_cli(["v=spf1 ~all"])[0], 0)
        self.assertEqual(self.run_cli(["--strict", "v=spf1 ~all"])[0], 1)

    def test_no_args(self):
        code, _, err = self.run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("either", err)

    def test_both_args(self):
        self.assertEqual(self.run_cli(["v=spf1 -all", "-f", "x"])[0], 2)

    def test_unknown_flag(self):
        self.assertEqual(self.run_cli(["--nope"])[0], 2)

    def test_stdin_empty(self):
        code, _, err = self.run_cli(["-f", "-"], stdin="\n# only a comment\n")
        self.assertEqual(code, 2)
        self.assertIn("empty", err)

    def test_stdin_records(self):
        code, out, _ = self.run_cli(["-f", "-"], stdin='"v=spf1 -all"\nv=DMARC1; p=reject; rua=mailto:a@b.co\n')
        self.assertEqual(code, 0)
        self.assertIn("[SPF]", out)
        self.assertIn("[DMARC]", out)

    def test_missing_file(self):
        code, _, err = self.run_cli(["-f", "/no/such/file.txt"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_binary_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.bin")
            with open(p, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x80")
            code, _, err = self.run_cli(["-f", p])
            self.assertEqual(code, 2)
            self.assertIn("UTF-8", err)

    def test_bad_zone_reported(self):
        code, _, err = self.run_cli(["--zone", "/no/zone.json", "v=spf1 -all"])
        self.assertEqual(code, 2)
        self.assertIn("zone", err)

    def test_json_output(self):
        code, out, _ = self.run_cli(["--json", "v=spf1 a ~all"])
        data = json.loads(out)
        self.assertEqual(data[0]["kind"], "spf")
        self.assertEqual(data[0]["lookups"], 1)
        self.assertEqual(data[0]["findings"][0]["level"], "warning")
        self.assertEqual(code, 0)

    def test_zone_expansion_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "z.json")
            with open(p, "w") as fh:
                json.dump({"a.example.com": "v=spf1 " + "a " * 11 + "-all"}, fh)
            code, out, _ = self.run_cli(["--zone", p, "v=spf1 include:a.example.com -all"])
            self.assertEqual(code, 1)
            self.assertIn("12 DNS lookups", out)


if __name__ == "__main__":
    unittest.main()
