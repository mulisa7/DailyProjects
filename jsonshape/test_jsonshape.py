import io, os, tempfile, unittest, json
import jsonshape as js


def run(args, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = js.main(args, io.StringIO(stdin), out, err)
    return code, out.getvalue(), err.getvalue()


class Load(unittest.TestCase):
    def test_single(self):
        self.assertEqual(js.load_documents('{"a":1}'), [{"a": 1}])

    def test_ndjson_auto(self):
        self.assertEqual(len(js.load_documents('{"a":1}\n\n{"a":2}\n')), 2)

    def test_empty(self):
        with self.assertRaises(ValueError):
            js.load_documents("  \n")

    def test_bad_json_forced(self):
        with self.assertRaises(ValueError):
            js.load_documents('{"a":', "json")

    def test_bad_ndjson_line(self):
        with self.assertRaisesRegex(ValueError, "line 2"):
            js.load_documents('{"a":1}\n{bad}\n')


class Analyse(unittest.TestCase):
    def test_types_and_range(self):
        n = js.analyse([{"x": 3}, {"x": 10.5}])
        self.assertEqual(n["$.x"].types, {"integer": 1, "number": 1})
        self.assertEqual((n["$.x"].num_min, n["$.x"].num_max), (3, 10.5))

    def test_bool_not_integer(self):
        self.assertEqual(js.analyse([{"b": True}])["$.b"].types, {"boolean": 1})

    def test_array_items(self):
        n = js.analyse([{"t": ["a", "bb"]}, {"t": []}])
        self.assertEqual((n["$.t"].len_min, n["$.t"].len_max), (0, 2))
        self.assertEqual(n["$.t[]"].count, 2)

    def test_max_depth(self):
        n = js.analyse([{"a": {"b": {"c": 1}}}], max_depth=1)
        self.assertIn("$.a", n)
        self.assertNotIn("$.a.b", n)

    def test_top_level_scalar_and_array(self):
        self.assertEqual(js.analyse([5])["$"].types, {"integer": 1})
        self.assertIn("$[]", js.analyse([[1, 2]]))

    def test_key_with_dot_and_unicode(self):
        n = js.analyse([{"é.x": 1}])
        self.assertIn("$.é.x", n)


class Render(unittest.TestCase):
    def test_presence_and_mixed(self):
        docs = [{"a": 1, "b": None}, {"a": "x"}, {"a": 2, "b": 3}]
        text = js.render(js.analyse(docs))
        self.assertIn("present 2/3 (66%)", text)
        self.assertIn("(mixed)", text)

    def test_empty_object(self):
        self.assertEqual(js.render(js.analyse([{}])), "$: object")


class CLI(unittest.TestCase):
    def test_stdin(self):
        code, out, _ = run(["-"], '{"name":"Ann","age":30}')
        self.assertEqual(code, 0)
        self.assertIn("age: integer, range 30..30", out)
        self.assertIn('e.g. "Ann"', out)

    def test_ndjson_header(self):
        code, out, _ = run([], '{"a":1}\n{"a":2}\n')
        self.assertTrue(out.startswith("2 records"))

    def test_empty_input(self):
        code, _, err = run([], "")
        self.assertEqual(code, 1)
        self.assertIn("empty", err)

    def test_missing_file(self):
        code, _, err = run(["/no/such/file.json"])
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)

    def test_invalid_json_message(self):
        code, _, err = run(["--format", "json"], "{oops")
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", err)

    def test_bad_flag(self):
        self.assertEqual(run(["--nope"])[0], 2)

    def test_negative_depth(self):
        self.assertEqual(run(["--max-depth", "-1"], "{}")[0], 2)

    def test_json_output(self):
        code, out, _ = run(["--json"], '{"a":[1,2]}')
        self.assertEqual(json.loads(out)["$.a"]["length_max"], 2)

    def test_file_with_bom(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as f:
            f.write(b'\xef\xbb\xbf{"a":1}')
        try:
            self.assertEqual(run([f.name])[0], 0)
        finally:
            os.unlink(f.name)

    def test_binary_file(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"\xff\xfe\x00\x80")
        try:
            self.assertEqual(run([f.name])[0], 1)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
