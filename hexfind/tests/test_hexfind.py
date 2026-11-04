import io
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hexfind  # noqa: E402


def matches(data, pattern, **kw):
    return list(hexfind.find_matches(data, hexfind.parse_pattern(pattern), **kw))


class ParseTests(unittest.TestCase):
    def test_literal_lengths(self):
        els = hexfind.parse_pattern("50 4B0304 str(abc) ?? *3")
        self.assertEqual([e.size for e in els], [1, 3, 3, 1, 3])
        self.assertEqual(hexfind.pattern_length(els), 11)

    def test_bad_patterns(self):
        for bad in ["", "   ", "4", "zz", "u16>1", "u8le", "u32le>", "u8>300", "u8=5..2",
                    "*0", "*x", "str()", "u16le>>3", "i8<-200", "u8=a|b", "str(é)"]:
            with self.assertRaises(hexfind.PatternError, msg=bad):
                hexfind.parse_pattern(bad)

    def test_hex_numbers(self):
        self.assertEqual(len(matches(b"\x10", "u8==0x10")), 1)


class MatchTests(unittest.TestCase):
    def test_plain_literal_all_offsets(self):
        self.assertEqual([o for o, _ in matches(b"abcabcab", "str(ab)")], [0, 3, 6])

    def test_overlapping_matches_reported(self):
        self.assertEqual([o for o, _ in matches(b"aaaa", "61 61")], [0, 1, 2])

    def test_wildcards(self):
        self.assertEqual([o for o, _ in matches(b"xaybxcyb", "str(a) ?? str(b)")], [1])
        self.assertEqual([o for o, _ in matches(b"a123b", "str(a) *3 str(b)")], [0])

    def test_field_constraint(self):
        data = b"HD" + struct.pack("<H", 5) + b"HD" + struct.pack("<H", 500)
        hits = matches(data, "str(HD) size:u16le<100")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], 0)
        self.assertEqual(hits[0][1], [("size", 5)])

    def test_big_endian_vs_little(self):
        data = struct.pack(">I", 0xCAFE)
        self.assertEqual(len(matches(data, "u32be==0xCAFE")), 1)
        self.assertEqual(len(matches(data, "u32le==0xCAFE")), 0)

    def test_signed(self):
        data = struct.pack("<h", -5)
        self.assertEqual(len(matches(data, "i16le<0")), 1)
        self.assertEqual(len(matches(data, "u16le<0x8000")), 0)

    def test_range_and_list(self):
        data = bytes([1, 7, 20])
        self.assertEqual([o for o, _ in matches(data, "u8=5..10")], [1])
        self.assertEqual([o for o, _ in matches(data, "u8=1|20")], [0, 2])
        self.assertEqual([o for o, _ in matches(data, "u8!=7")], [0, 2])

    def test_pattern_at_very_end_and_too_long(self):
        self.assertEqual([o for o, _ in matches(b"xxab", "str(ab)")], [2])
        self.assertEqual(matches(b"a", "str(ab)"), [])

    def test_empty_data(self):
        self.assertEqual(matches(b"", "??"), [])

    def test_align(self):
        self.assertEqual([o for o, _ in matches(b"aaaaaaaa", "61", align=4)], [0, 4])

    def test_start_end(self):
        self.assertEqual([o for o, _ in matches(b"ababab", "str(ab)", start=1)], [2, 4])
        self.assertEqual([o for o, _ in matches(b"ababab", "str(ab)", end=4)], [0, 2])

    def test_named_wildcard_returns_bytes(self):
        hits = matches(b"a\x07b", "str(a) tag:?? str(b)")
        self.assertEqual(hits[0][1], [("tag", b"\x07")])

    def test_non_literal_start(self):
        data = b"\x00\x00\x03\x00"
        self.assertEqual([o for o, _ in matches(data, "u16be==3")], [1])

    def test_works_on_bytearray_and_mmap_free_input(self):
        self.assertEqual(len(matches(bytearray(b"zzab"), "str(ab)")), 1)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, data):
        p = os.path.join(self.dir.name, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = hexfind.main(list(args), out, err)
        return code, out.getvalue(), err.getvalue()

    def test_match_output(self):
        p = self.write("a.bin", b"..PK" + struct.pack("<H", 20))
        code, out, _ = self.run_cli("str(PK) v:u16le>=10", p)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("0x00000002  50 4b 14 00"))
        self.assertIn("v=20", out)

    def test_no_match_exit_1(self):
        p = self.write("a.bin", b"hello")
        code, out, _ = self.run_cli("str(zzz)", p)
        self.assertEqual((code, out), (1, ""))

    def test_empty_file(self):
        p = self.write("empty.bin", b"")
        self.assertEqual(self.run_cli("??", p)[0], 1)
        self.assertEqual(self.run_cli("-c", "??", p)[1], "0\n")

    def test_missing_file_exit_2(self):
        code, _, err = self.run_cli("??", os.path.join(self.dir.name, "nope"))
        self.assertEqual(code, 2)
        self.assertIn("nope", err)

    def test_directory_exit_2(self):
        code, _, err = self.run_cli("??", self.dir.name)
        self.assertEqual(code, 2)
        self.assertIn("directory", err)

    def test_bad_pattern_exit_2(self):
        p = self.write("a.bin", b"x")
        code, _, err = self.run_cli("u16>1", p)
        self.assertEqual(code, 2)
        self.assertIn("needs le or be", err)

    def test_missing_args(self):
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("??")[0], 2)

    def test_unknown_option_and_missing_value(self):
        self.assertEqual(self.run_cli("--bogus", "??", "f")[0], 2)
        code, _, err = self.run_cli("??", "f", "--max")
        self.assertEqual(code, 2)
        self.assertIn("needs a value", err)

    def test_bad_numbers(self):
        for args in (["--max", "0"], ["--max", "x"], ["--align", "0"], ["--start", "-1"]):
            code, _, _ = self.run_cli(*args, "??", "f")
            self.assertEqual(code, 2, args)
        self.assertEqual(self.run_cli("--start", "10", "--end", "5", "??", "f")[0], 2)

    def test_max_and_count(self):
        p = self.write("a.bin", b"aaaaa")
        code, out, _ = self.run_cli("-n", "2", "-o", "61", p)
        self.assertEqual(out.splitlines(), ["0x00000000", "0x00000001"])
        self.assertEqual(self.run_cli("-c", "61", p)[1], "5\n")

    def test_no_overlap(self):
        p = self.write("a.bin", b"aaaaa")
        self.assertEqual(self.run_cli("-c", "--no-overlap", "61 61", p)[1], "2\n")

    def test_multiple_files_prefix_and_partial_failure(self):
        a = self.write("a.bin", b"xxQ")
        b = self.write("b.bin", b"Q")
        code, out, _ = self.run_cli("-o", "str(Q)", a, b)
        self.assertEqual(out.splitlines(), [a + ":0x00000002", b + ":0x00000000"])
        code, out, err = self.run_cli("-o", "str(Q)", a, os.path.join(self.dir.name, "gone"))
        self.assertEqual(code, 2)
        self.assertIn("0x00000002", out)

    def test_json(self):
        p = self.write("a.bin", b"\x01\x00")
        code, out, _ = self.run_cli("--json", "n:u16le==1", p)
        rec = json.loads(out)
        self.assertEqual((rec["offset"], rec["fields"], rec["bytes"]), (0, {"n": 1}, "0100"))

    def test_help(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("usage: hexfind", out)

    def test_long_match_is_truncated_in_display(self):
        p = self.write("a.bin", b"a" * 40)
        _, out, _ = self.run_cli("*40", p)
        self.assertIn("...", out)


if __name__ == "__main__":
    unittest.main()
