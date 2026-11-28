import io
import os
import tempfile
import unittest

import a11yscan as A

GOOD = """<!doctype html><html lang="en"><head><title>Home</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body><h1>Welcome</h1><h2>Intro</h2>
<img src="a.png" alt="A red bicycle"><img src="deco.png" alt="">
<a href="/docs">Documentation</a><button>Save</button>
<label for="n">Name</label><input id="n" type="text">
<label>Email <input type="email"></label>
<input type="submit" value="Go"><input type="hidden" name="x">
<table><tr><th>A</th></tr><tr><td>1</td></tr></table>
</body></html>"""


def rules(html):
    return [f["rule"] for f in A.scan_html(html)]


class Scan(unittest.TestCase):
    def test_clean_page(self):
        self.assertEqual(A.scan_html(GOOD), [])

    def test_img_without_alt(self):
        self.assertIn("img-alt", rules('<img src="x.png">'))

    def test_img_presentation_role_ok(self):
        self.assertNotIn("img-alt", rules('<img src="x.png" role="presentation">'))

    def test_empty_alt_ok(self):
        self.assertEqual(rules('<img src="x.png" alt="">'), [])

    def test_filename_alt(self):
        for alt in ("photo.jpg", "IMG_1234", "image"):
            self.assertIn("img-alt-filename", rules('<img src="x" alt="%s">' % alt), alt)

    def test_real_alt_not_flagged(self):
        self.assertEqual(rules('<img src="x" alt="Image of the team in 2020">'), [])

    def test_missing_lang_title_h1(self):
        r = rules("<html><head></head><body><p>x</p></body></html>")
        self.assertEqual(sorted(r), ["heading-h1", "html-lang", "page-title"])

    def test_fragment_skips_page_rules(self):
        self.assertEqual(rules("<p>just a snippet</p>"), [])

    def test_two_h1(self):
        r = rules('<html lang="en"><title>t</title><h1>a</h1><h1>b</h1></html>')
        self.assertEqual(r, ["heading-h1"])

    def test_heading_skip(self):
        self.assertIn("heading-skip", rules("<h1>a</h1><h3>b</h3>"))
        self.assertNotIn("heading-skip", rules("<h3>a</h3><h2>b</h2>"))

    def test_empty_link(self):
        self.assertIn("link-name", rules('<a href="/x"></a>'))
        self.assertIn("link-name", rules('<a href="/x"> <span> </span></a>'))

    def test_link_with_image_alt(self):
        self.assertEqual(rules('<a href="/x"><img src="i" alt="Home"></a>'), [])

    def test_link_aria_label(self):
        self.assertEqual(rules('<a href="/x" aria-label="Home"></a>'), [])

    def test_anchor_without_href_ignored(self):
        self.assertEqual(rules('<a name="top"></a>'), [])

    def test_vague_link(self):
        self.assertIn("link-vague", rules('<a href="/x">Click here</a>'))
        self.assertIn("link-vague", rules('<a href="/x">Read more.</a>'))

    def test_empty_button(self):
        self.assertIn("button-name", rules("<button></button>"))
        self.assertEqual(rules('<button aria-label="Close"></button>'), [])

    def test_input_without_label(self):
        self.assertIn("input-label", rules('<input type="text">'))
        self.assertIn("input-label", rules('<textarea></textarea>'))

    def test_input_labelled_variants(self):
        self.assertEqual(rules('<input aria-label="q">'), [])
        self.assertEqual(rules('<input id="a"><label for="a">A</label>'), [])
        self.assertEqual(rules('<label for="a">A</label><input id="a">'), [])
        self.assertEqual(rules('<label>A <select></select></label>'), [])

    def test_duplicate_id(self):
        self.assertEqual(rules('<p id="a"></p><p id="a"></p>'), ["duplicate-id"])

    def test_tabindex(self):
        self.assertIn("tabindex-positive", rules('<div tabindex="3"></div>'))
        self.assertEqual(rules('<div tabindex="0"></div><div tabindex="-1"></div>'), [])
        self.assertEqual(rules('<div tabindex="abc"></div>'), [])

    def test_table_without_th(self):
        self.assertIn("table-header", rules("<table><tr><td>1</td></tr></table>"))

    def test_nested_table_th_scoped(self):
        h = "<table><tr><td><table><tr><th>x</th></tr></table></td></tr></table>"
        self.assertEqual(rules(h), ["table-header"])

    def test_iframe_title(self):
        self.assertIn("iframe-title", rules('<iframe src="x"></iframe>'))
        self.assertEqual(rules('<iframe src="x" title="Map"></iframe>'), [])

    def test_viewport_zoom(self):
        self.assertIn("viewport-zoom", rules('<meta name="viewport" content="width=device-width, user-scalable=no">'))
        self.assertIn("viewport-zoom", rules('<meta name="viewport" content="maximum-scale=1.0">'))
        self.assertEqual(rules('<meta name="viewport" content="maximum-scale=5">'), [])

    def test_autoplay(self):
        self.assertIn("media-autoplay", rules("<video autoplay></video>"))

    def test_malformed_html_does_not_crash(self):
        rules("<div><a href=x><b>unclosed <img alt=")
        rules("</p></a></table><<>>")

    def test_empty_input(self):
        self.assertEqual(A.scan_html(""), [])

    def test_line_numbers(self):
        f = A.scan_html("<p>x</p>\n\n<img src='q'>")
        self.assertEqual(f[0]["line"], 3)

    def test_uppercase_tags(self):
        self.assertIn("img-alt", rules('<IMG SRC="x">'))


class Cli(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = A.main(argv, out, err)
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)

    def write(self, name, text, mode="w", enc="utf-8"):
        p = os.path.join(self.d.name, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode, **({"encoding": enc} if "b" not in mode else {})) as f:
            f.write(text)
        return p

    def test_clean_exit_0(self):
        p = self.write("a.html", GOOD)
        code, out, _ = self.run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("0 issue(s)", out)

    def test_issues_exit_1(self):
        p = self.write("a.html", "<img src=x>")
        code, out, _ = self.run_cli([p])
        self.assertEqual(code, 1)
        self.assertIn("[img-alt]", out)

    def test_folder_recursion_and_filter(self):
        self.write("a/b.html", "<img src=x>")
        self.write("c.txt", "<img src=x>")
        code, out, _ = self.run_cli([self.d.name])
        self.assertEqual(code, 1)
        self.assertIn("1 issue(s) in 1 file(s)", out)

    def test_empty_folder(self):
        code, _, err = self.run_cli([self.d.name])
        self.assertEqual(code, 2)
        self.assertIn("no .html", err)

    def test_missing_path(self):
        code, _, err = self.run_cli([os.path.join(self.d.name, "nope.html")])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_no_args(self):
        self.assertEqual(self.run_cli([])[0], 2)

    def test_ignore_and_unknown(self):
        p = self.write("a.html", "<img src=x>")
        self.assertEqual(self.run_cli([p, "--ignore", "img-alt"])[0], 0)
        code, _, err = self.run_cli([p, "--ignore", "bogus"])
        self.assertEqual(code, 2)
        self.assertIn("bogus", err)

    def test_json(self):
        import json
        p = self.write("a.html", "<img src=x>")
        code, out, _ = self.run_cli([p, "--json"])
        data = json.loads(out)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["files"][p][0]["rule"], "img-alt")

    def test_latin1_and_bom(self):
        self.write("l.html", "<p>caf\xe9</p><img src=x>", enc="latin-1")
        self.write("b.html", b"\xef\xbb\xbf<p>ok</p>", mode="wb")
        code, out, _ = self.run_cli([self.d.name])
        self.assertEqual(code, 1)
        self.assertIn("1 issue(s) in 2 file(s)", out)

    def test_bad_flag(self):
        self.assertEqual(self.run_cli(["--nope"])[0], 2)

    def test_list_rules(self):
        code, out, _ = self.run_cli(["--list-rules"])
        self.assertEqual(code, 0)
        self.assertIn("img-alt", out)


if __name__ == "__main__":
    unittest.main()
