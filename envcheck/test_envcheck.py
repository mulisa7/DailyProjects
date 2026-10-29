import contextlib
import io
import os
import tempfile
import unittest

import envcheck


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = envcheck.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_basic_and_export(self):
        got = envcheck.parse_env("A=1\nexport B=two\n")
        self.assertEqual(got, {"A": "1", "B": "two"})

    def test_comments_blank_and_inline(self):
        got = envcheck.parse_env("# c\n\nA=1 # note\nB=a#b\n")
        self.assertEqual(got, {"A": "1", "B": "a#b"})

    def test_quotes(self):
        got = envcheck.parse_env('A="x y # z"\nB=\'q\'\nC=\n')
        self.assertEqual(got, {"A": "x y # z", "B": "q", "C": ""})

    def test_garbage_lines_ignored(self):
        self.assertEqual(envcheck.parse_env("not a pair\n=oops\n1BAD=x\n"), {})

    def test_empty_text(self):
        self.assertEqual(envcheck.parse_env(""), {})


class CompareTests(unittest.TestCase):
    def test_report(self):
        r = envcheck.compare({"A": "", "B": "", "C": ""}, {"A": "1", "C": "", "D": "x"})
        self.assertEqual(r["missing"], ["B"])
        self.assertEqual(r["extra"], ["D"])
        self.assertEqual(r["empty"], ["C"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ex = os.path.join(self.tmp.name, ".env.example")
        self.env = os.path.join(self.tmp.name, ".env")

    def test_ok(self):
        write(self.ex, "A=\nB=\n")
        write(self.env, "A=1\nB=2\n")
        code, out, _ = run("--env", self.env, "--example", self.ex)
        self.assertEqual(code, 0)
        self.assertIn("All good", out)

    def test_missing_fails(self):
        write(self.ex, "A=\nB=\n")
        write(self.env, "A=1\n")
        code, out, _ = run("--env", self.env, "--example", self.ex)
        self.assertEqual(code, 1)
        self.assertIn("- B", out)

    def test_extra_only_passes_unless_strict(self):
        write(self.ex, "A=\n")
        write(self.env, "A=1\nZ=9\n")
        self.assertEqual(run("--env", self.env, "--example", self.ex)[0], 0)
        self.assertEqual(run("--env", self.env, "--example", self.ex, "--strict")[0], 1)

    def test_missing_env_file(self):
        write(self.ex, "A=\n")
        code, _, err = run("--env", self.env, "--example", self.ex)
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_empty_example(self):
        write(self.ex, "# nothing\n")
        write(self.env, "A=1\n")
        code, _, err = run("--env", self.env, "--example", self.ex)
        self.assertEqual(code, 2)
        self.assertIn("no variables", err)

    def test_binary_file(self):
        with open(self.ex, "wb") as f:
            f.write(b"\xff\xfe\x00\x80\x81")
        write(self.env, "A=1\n")
        code, _, err = run("--env", self.env, "--example", self.ex)
        self.assertEqual(code, 2)
        self.assertIn("UTF-8", err)

    def test_json_output(self):
        write(self.ex, "A=\nB=\n")
        write(self.env, "A=1\n")
        code, out, _ = run("--env", self.env, "--example", self.ex, "--json")
        self.assertEqual(code, 1)
        self.assertIn('"missing": [\n    "B"\n  ]', out)

    def test_scan_finds_undocumented(self):
        write(self.ex, "DB_URL=\n")
        write(self.env, "DB_URL=x\n")
        src = os.path.join(self.tmp.name, "src")
        os.mkdir(src)
        write(os.path.join(src, "app.js"),
              "const a = process.env.DB_URL;\nconst b = process.env.API_KEY;\n")
        write(os.path.join(src, "x.py"), "import os\nos.environ.get('SECRET_X')\n")
        code, out, _ = run("--env", self.env, "--example", self.ex, "--scan", src)
        self.assertEqual(code, 1)
        self.assertIn("API_KEY", out)
        self.assertIn("SECRET_X", out)
        self.assertNotIn("- DB_URL", out)

    def test_scan_bad_dir(self):
        write(self.ex, "A=\n")
        write(self.env, "A=1\n")
        code, _, err = run("--env", self.env, "--example", self.ex,
                           "--scan", os.path.join(self.tmp.name, "nope"))
        self.assertEqual(code, 2)
        self.assertIn("not a directory", err)

    def test_scan_skips_node_modules(self):
        write(self.ex, "A=\n")
        write(self.env, "A=1\n")
        nm = os.path.join(self.tmp.name, "node_modules")
        os.mkdir(nm)
        write(os.path.join(nm, "lib.js"), "process.env.HIDDEN")
        code, out, _ = run("--env", self.env, "--example", self.ex,
                           "--scan", self.tmp.name)
        self.assertNotIn("HIDDEN", out)


if __name__ == "__main__":
    unittest.main()
