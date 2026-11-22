import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mdrefs


def make(tree):
    d = tempfile.mkdtemp()
    for name, content in tree.items():
        p = os.path.join(d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return d


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mdrefs.main(args)
    return code, out.getvalue(), err.getvalue()


class Slug(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(mdrefs.slugify("Hello, World!"), "hello-world")
        self.assertEqual(mdrefs.slugify("`code` and *em*"), "code-and-em")
        self.assertEqual(mdrefs.slugify("A [link](http://x.y) here"), "a-link-here")
        self.assertEqual(mdrefs.slugify("Under_score ok"), "under_score-ok")

    def test_duplicates(self):
        a = mdrefs.collect_anchors("# Intro\n## Intro\n## Intro\n")
        self.assertEqual(a, {"intro", "intro-1", "intro-2"})

    def test_headings_in_fences_ignored(self):
        self.assertEqual(mdrefs.collect_anchors("```\n# fake\n```\n# real\n"), {"real"})

    def test_html_id(self):
        self.assertIn("top", mdrefs.collect_anchors('<a id="top"></a>\n'))


class Links(unittest.TestCase):
    def test_all_good(self):
        d = make({"a.md": "# A\n[b](b.md) [sec](b.md#part-two) [self](#a)\n", "b.md": "# B\n## Part Two\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 0, out)
        self.assertIn("0 problem", out)

    def test_missing_file(self):
        d = make({"a.md": "[x](nope.md)\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("file not found: nope.md", out)
        self.assertIn(":1:", out)

    def test_bad_anchor(self):
        d = make({"a.md": "[x](b.md#missing)\n", "b.md": "# B\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("no heading", out)

    def test_bad_self_anchor(self):
        d = make({"a.md": "# A\n[x](#nothing)\n"})
        self.assertEqual(run([d])[0], 1)

    def test_anchor_case_insensitive(self):
        d = make({"a.md": "# Hello\n[x](#HELLO)\n"})
        self.assertEqual(run([d])[0], 0)

    def test_external_ignored(self):
        d = make({"a.md": "[x](https://example.com/q#z) [m](mailto:a@b.c) [p](//cdn.x/y)\n"})
        self.assertEqual(run([d])[0], 0)

    def test_code_ignored(self):
        d = make({"a.md": "```\n[x](nope.md)\n```\nUse `[y](nope2.md)` inline.\n"})
        self.assertEqual(run([d])[0], 0)

    def test_images_and_titles(self):
        d = make({"a.md": '![i](img/p.png "title") [t](b.md \'t\')\n', "b.md": "x\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("img/p.png", out)
        self.assertEqual(out.count("not found"), 1)

    def test_spaces_and_percent(self):
        d = make({"a.md": "[x](<my file.md>) [y](my%20file.md)\n", "my file.md": "x\n"})
        self.assertEqual(run([d])[0], 0)

    def test_parens_in_url(self):
        d = make({"a.md": "[x](f(1).md)\n", "f(1).md": "x\n"})
        self.assertEqual(run([d])[0], 0)

    def test_query_string_stripped(self):
        d = make({"a.md": "[x](b.md?raw=1)\n", "b.md": "x\n"})
        self.assertEqual(run([d])[0], 0)

    def test_directory_link(self):
        d = make({"a.md": "[x](sub/) [y](sub/#anything)\n", "sub/c.md": "x\n"})
        self.assertEqual(run([d])[0], 0)

    def test_non_markdown_anchor_not_checked(self):
        d = make({"a.md": "[x](code.py#L10)\n", "code.py": "x\n"})
        self.assertEqual(run([d])[0], 0)

    def test_reference_links(self):
        d = make({"a.md": "[x][r] [ok][good]\n\n[r]: nope.md\n[good]: a.md\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertEqual(out.count("not found"), 1)

    def test_undefined_reference(self):
        d = make({"a.md": "see [x][ghost]\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("no definition", out)

    def test_empty_target(self):
        d = make({"a.md": "[x]()\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("empty link target", out)

    def test_root_relative_and_escape(self):
        d = make({"docs/a.md": "[x](/top.md) [y](../../outside.md)\n", "top.md": "x\n"})
        code, out, _ = run([d])
        self.assertEqual(code, 1)
        self.assertIn("outside", out)
        self.assertEqual(out.count("not found"), 0)


class Cli(unittest.TestCase):
    def test_empty_folder(self):
        d = tempfile.mkdtemp()
        code, out, _ = run([d])
        self.assertEqual(code, 0)
        self.assertIn("no Markdown files", out)

    def test_empty_file(self):
        d = make({"a.md": ""})
        self.assertEqual(run([d])[0], 0)

    def test_missing_path(self):
        code, _, err = run(["/no/such/path-xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_single_file(self):
        d = make({"a.md": "[x](nope.md)\n"})
        self.assertEqual(run([os.path.join(d, "a.md")])[0], 1)

    def test_skips_git_and_node_modules(self):
        d = make({".git/x.md": "[x](nope)\n", "node_modules/y.md": "[x](nope)\n", "ok.md": "hi\n"})
        self.assertEqual(run([d])[0], 0)

    def test_binary_garbage_does_not_crash(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.md"), "wb") as f:
            f.write(b"\xff\xfe\x00[x](\x80\n")
        self.assertIn(run([d])[0], (0, 1))


if __name__ == "__main__":
    unittest.main()
