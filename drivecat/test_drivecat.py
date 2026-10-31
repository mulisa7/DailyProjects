import io
import os
import tempfile
import unittest

import drivecat


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "cat.db")

    def make_tree(self, name, files):
        root = os.path.join(self.tmp.name, name)
        for rel, size in files.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(b"x" * size)
        os.makedirs(root, exist_ok=True)
        return root

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = drivecat.run(["--db", self.db, *argv], out, err)
        return code, out.getvalue(), err.getvalue()


class ScanTests(Base):
    def test_scan_counts_files_and_sizes(self):
        root = self.make_tree("a", {"x.txt": 10, "sub/y.txt": 2048})
        code, out, err = self.run_cli("scan", root, "--label", "A")
        self.assertEqual(code, 0)
        self.assertIn("A: 2 files, 2.0 KB", out)
        self.assertEqual(err, "")

    def test_label_defaults_to_folder_name(self):
        root = self.make_tree("photos", {"a.jpg": 1})
        self.run_cli("scan", root)
        _, out, _ = self.run_cli("disks")
        self.assertIn("photos", out)

    def test_rescan_replaces_old_entries(self):
        root = self.make_tree("a", {"old.txt": 5})
        self.run_cli("scan", root, "--label", "A")
        os.remove(os.path.join(root, "old.txt"))
        with open(os.path.join(root, "new.txt"), "w") as fh:
            fh.write("hi")
        self.run_cli("scan", root, "--label", "A")
        self.assertEqual(self.run_cli("search", "old")[0], 1)
        self.assertEqual(self.run_cli("search", "new")[0], 0)

    def test_missing_folder_is_error(self):
        code, _, err = self.run_cli("scan", os.path.join(self.tmp.name, "nope"))
        self.assertEqual(code, 1)
        self.assertIn("not a folder", err)

    def test_file_instead_of_folder_is_error(self):
        root = self.make_tree("a", {"f.txt": 1})
        code, _, err = self.run_cli("scan", os.path.join(root, "f.txt"))
        self.assertEqual(code, 1)
        self.assertIn("not a folder", err)

    def test_empty_folder_warns_but_succeeds(self):
        root = self.make_tree("empty", {})
        code, out, err = self.run_cli("scan", root, "--label", "E")
        self.assertEqual(code, 0)
        self.assertIn("0 files", out)
        self.assertIn("no files", err)

    def test_blank_label_rejected(self):
        root = self.make_tree("a", {"f": 1})
        code, _, err = self.run_cli("scan", root, "--label", "  ")
        self.assertEqual(code, 1)
        self.assertIn("label is empty", err)

    def test_zero_byte_and_unicode_names(self):
        root = self.make_tree("a", {"café menu.txt": 0, "日本/写真.jpg": 3})
        self.run_cli("scan", root, "--label", "A")
        code, out, _ = self.run_cli("search", "写真")
        self.assertEqual(code, 0)
        self.assertIn("日本/写真.jpg", out)
        self.assertIn("café menu.txt", self.run_cli("search", "*MENU*")[1])


class SearchTests(Base):
    def setUp(self):
        super().setUp()
        a = self.make_tree("a", {"Holiday/IMG_001.JPG": 100, "Holiday/clip.mkv": 5000, "docs/report_01.pdf": 20})
        b = self.make_tree("b", {"movies/film.mkv": 9000, "docs/report_02.pdf": 20})
        self.run_cli("scan", a, "--label", "A")
        self.run_cli("scan", b, "--label", "B")

    def test_substring_matches_path_case_insensitive(self):
        code, out, _ = self.run_cli("search", "holiday")
        self.assertEqual(code, 0)
        self.assertIn("[A] Holiday/IMG_001.JPG", out)
        self.assertIn("[A] Holiday/clip.mkv", out)

    def test_glob_matches_name(self):
        _, out, _ = self.run_cli("search", "*.mkv")
        self.assertIn("[A] Holiday/clip.mkv", out)
        self.assertIn("[B] movies/film.mkv", out)
        self.assertNotIn("pdf", out)

    def test_glob_question_mark(self):
        _, out, _ = self.run_cli("search", "report_0?.pdf")
        self.assertEqual(out.count("report_"), 2)

    def test_glob_with_slash_matches_path(self):
        _, out, _ = self.run_cli("search", "docs/*.pdf")
        self.assertEqual(out.count("report_"), 2)

    def test_label_filter(self):
        _, out, _ = self.run_cli("search", "*.mkv", "--label", "B")
        self.assertIn("[B]", out)
        self.assertNotIn("[A]", out)

    def test_min_size_filter(self):
        _, out, _ = self.run_cli("search", "*.mkv", "--min-size", "6k")
        self.assertIn("film.mkv", out)
        self.assertNotIn("clip.mkv", out)

    def test_no_match_returns_1(self):
        code, out, _ = self.run_cli("search", "zzz")
        self.assertEqual(code, 1)
        self.assertIn("No matches", out)

    def test_limit_reports_remainder(self):
        _, out, _ = self.run_cli("search", "*", "--limit", "2")
        self.assertIn("3 more", out)

    def test_empty_pattern(self):
        code, _, err = self.run_cli("search", "  ")
        self.assertEqual(code, 1)
        self.assertIn("empty", err)

    def test_unknown_label(self):
        code, _, err = self.run_cli("search", "x", "--label", "Z")
        self.assertEqual(code, 1)
        self.assertIn("Known disks: A, B", err)

    def test_bad_size_is_usage_error(self):
        code, _, _ = self.run_cli("search", "x", "--min-size", "lots")
        self.assertEqual(code, 2)

    def test_zero_limit_is_usage_error(self):
        code, _, err = self.run_cli("search", "x", "--limit", "0")
        self.assertEqual(code, 2)
        self.assertIn("--limit", err)

    def test_search_on_empty_catalog(self):
        self.db = os.path.join(self.tmp.name, "fresh.db")
        code, _, err = self.run_cli("search", "x")
        self.assertEqual(code, 1)
        self.assertIn("catalog is empty", err)


class BrowseTests(Base):
    def setUp(self):
        super().setUp()
        a = self.make_tree("a", {"top.txt": 1, "docs/a.txt": 1000, "docs/deep/b.txt": 3000, "pics/p.jpg": 500})
        self.run_cli("scan", a, "--label", "A")

    def test_ls_root(self):
        code, out, _ = self.run_cli("ls", "A")
        self.assertEqual(code, 0)
        self.assertIn("docs/", out)
        self.assertIn("2 files", out)
        self.assertIn("top.txt", out)

    def test_ls_subfolder(self):
        _, out, _ = self.run_cli("ls", "A", "docs")
        self.assertIn("deep/", out)
        self.assertIn("a.txt", out)
        self.assertNotIn("pics", out)

    def test_ls_trailing_slash_ok(self):
        self.assertEqual(self.run_cli("ls", "A", "docs/")[0], 0)

    def test_ls_missing_dir(self):
        code, _, err = self.run_cli("ls", "A", "nothing")
        self.assertEqual(code, 1)
        self.assertIn("nothing under", err)

    def test_ls_prefix_is_not_substring_match(self):
        code, _, _ = self.run_cli("ls", "A", "doc")
        self.assertEqual(code, 1)

    def test_ls_unknown_disk(self):
        self.assertEqual(self.run_cli("ls", "Q")[0], 1)

    def test_big_orders_by_size(self):
        _, out, _ = self.run_cli("big", "A")
        lines = out.strip().splitlines()
        self.assertIn("docs/", lines[0])
        self.assertIn("pics/", lines[1])

    def test_big_depth_two(self):
        _, out, _ = self.run_cli("big", "A", "--depth", "2")
        self.assertIn("docs/deep/", out)

    def test_big_depth_zero(self):
        code, _, err = self.run_cli("big", "A", "--depth", "0")
        self.assertEqual(code, 1)
        self.assertIn("--depth", err)

    def test_big_empty_disk(self):
        e = self.make_tree("e", {})
        self.run_cli("scan", e, "--label", "E")
        code, _, err = self.run_cli("big", "E")
        self.assertEqual(code, 1)
        self.assertIn("no files", err)


class DupesAndDisksTests(Base):
    def test_dupes_same_name_and_size(self):
        a = self.make_tree("a", {"x/movie.mkv": 4096, "small.txt": 5})
        b = self.make_tree("b", {"backup/Movie.MKV": 4096, "small.txt": 6})
        self.run_cli("scan", a, "--label", "A")
        self.run_cli("scan", b, "--label", "B")
        code, out, _ = self.run_cli("dupes")
        self.assertEqual(code, 0)
        self.assertIn("movie.mkv  4.0 KB  x2", out)
        self.assertNotIn("small.txt", out)
        self.assertIn("4.0 KB in extra copies", out)

    def test_dupes_across_disks_only(self):
        a = self.make_tree("a", {"one/f.bin": 50, "two/f.bin": 50})
        self.run_cli("scan", a, "--label", "A")
        self.assertIn("x2", self.run_cli("dupes")[1])
        self.assertIn("No duplicates", self.run_cli("dupes", "--across-disks")[1])

    def test_dupes_min_size(self):
        a = self.make_tree("a", {"one/f.bin": 50, "two/f.bin": 50})
        self.run_cli("scan", a, "--label", "A")
        self.assertIn("No duplicates", self.run_cli("dupes", "--min-size", "1k")[1])

    def test_dupes_ignores_empty_files_by_default(self):
        a = self.make_tree("a", {"one/e.txt": 0, "two/e.txt": 0})
        self.run_cli("scan", a, "--label", "A")
        self.assertIn("No duplicates", self.run_cli("dupes")[1])

    def test_dupes_empty_catalog(self):
        code, out, _ = self.run_cli("dupes")
        self.assertEqual(code, 0)
        self.assertIn("No duplicates", out)

    def test_disks_empty(self):
        code, out, _ = self.run_cli("disks")
        self.assertEqual(code, 0)
        self.assertIn("No disks cataloged", out)

    def test_forget(self):
        a = self.make_tree("a", {"f.txt": 1})
        self.run_cli("scan", a, "--label", "A")
        self.assertEqual(self.run_cli("forget", "A")[0], 0)
        self.assertIn("No disks", self.run_cli("disks")[1])
        self.assertEqual(self.run_cli("forget", "A")[0], 1)

    def test_forget_removes_files_too(self):
        a = self.make_tree("a", {"f.txt": 1})
        self.run_cli("scan", a, "--label", "A")
        self.run_cli("forget", "A")
        b = self.make_tree("b", {"g.txt": 1})
        self.run_cli("scan", b, "--label", "B")
        self.assertEqual(self.run_cli("search", "f.txt")[0], 1)


class MiscTests(Base):
    def test_no_command_is_usage_error(self):
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(drivecat.run(["--db", self.db], out, err), 2)

    def test_corrupt_catalog_reports_cleanly(self):
        with open(self.db, "wb") as fh:
            fh.write(b"this is not a sqlite file" * 50)
        code, _, err = self.run_cli("disks")
        self.assertEqual(code, 1)
        self.assertIn("cannot open catalog", err)

    def test_missing_catalog_folder(self):
        self.db = os.path.join(self.tmp.name, "nodir", "c.db")
        code, _, err = self.run_cli("disks")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)

    def test_env_var_sets_default_db(self):
        old = os.environ.get("DRIVECAT_DB")
        os.environ["DRIVECAT_DB"] = self.db
        try:
            ns = drivecat.build_parser().parse_args(["disks"])
            self.assertEqual(ns.db, self.db)
        finally:
            if old is None:
                del os.environ["DRIVECAT_DB"]
            else:
                os.environ["DRIVECAT_DB"] = old

    def test_parse_size(self):
        self.assertEqual(drivecat.parse_size("500"), 500)
        self.assertEqual(drivecat.parse_size("10k"), 10240)
        self.assertEqual(drivecat.parse_size("2.5MB"), int(2.5 * 1024 ** 2))
        self.assertEqual(drivecat.parse_size("1g"), 1024 ** 3)
        with self.assertRaises(Exception):
            drivecat.parse_size("-1")
        with self.assertRaises(Exception):
            drivecat.parse_size("")

    def test_human(self):
        self.assertEqual(drivecat.human(0), "0 B")
        self.assertEqual(drivecat.human(1023), "1023 B")
        self.assertEqual(drivecat.human(1536), "1.5 KB")
        self.assertEqual(drivecat.human(5 * 1024 ** 4), "5.0 TB")

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlink support")
    def test_symlinks_not_followed(self):
        root = self.make_tree("a", {"real/f.txt": 7})
        try:
            os.symlink(os.path.join(root, "real"), os.path.join(root, "link"))
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlinks here")
        self.run_cli("scan", root, "--label", "A")
        _, out, _ = self.run_cli("search", "f.txt")
        self.assertEqual(out.count("f.txt"), 1)


if __name__ == "__main__":
    unittest.main()
