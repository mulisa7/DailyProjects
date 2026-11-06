import io, os, subprocess, tempfile, unittest, contextlib, json, time
import branchsweep as bs


def run(cwd, *a, env=None):
    e = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e.x",
             GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e.x", **(env or {}))
    subprocess.run(["git", "-C", cwd, *a], check=True, capture_output=True, env=e)


def commit(cwd, name, msg, env=None):
    with open(os.path.join(cwd, name), "w") as f:
        f.write(msg)
    run(cwd, "add", name)
    run(cwd, "commit", "-m", msg, env=env)


class Repo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        run(self.d, "init", "-b", "main")
        commit(self.d, "a.txt", "first")

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bs.main([self.d, *args])
        return code, out.getvalue(), err.getvalue()

    def names(self):
        return bs.git(self.d, "branch", "--format=%(refname:short)").split()

    def feature(self, name, env=None):
        run(self.d, "checkout", "-b", name)
        commit(self.d, name + ".txt", "work " + name, env=env)
        run(self.d, "checkout", "main")


class Tests(Repo):
    def status(self, **kw):
        rows = bs.classify(self.d, "main", kw.get("stale", 90))
        return {r["name"]: r["status"] for r in rows}

    def test_merged(self):
        self.feature("f1")
        run(self.d, "merge", "--no-ff", "f1", "-m", "merge")
        self.assertEqual(self.status()["f1"], "merged")

    def test_squash_merged(self):
        self.feature("f2")
        run(self.d, "merge", "--squash", "f2")
        run(self.d, "commit", "-m", "squashed f2")
        self.assertEqual(self.status()["f2"], "squash-merged")

    def test_active_and_protected(self):
        self.feature("f3")
        s = self.status()
        self.assertEqual(s["f3"], "active")
        self.assertEqual(s["main"], "protected")

    def test_stale(self):
        old = {"GIT_COMMITTER_DATE": "2020-01-01T00:00:00", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00"}
        self.feature("old", env=old)
        self.assertEqual(self.status()["old"], "stale")
        self.assertEqual(self.status(stale=None)["old"], "active")

    def test_current_branch_protected(self):
        run(self.d, "checkout", "-b", "here")
        self.assertEqual(self.status()["here"], "protected")

    def test_keep(self):
        self.feature("f4")
        run(self.d, "merge", "f4")
        code, out, _ = self.cli("--keep", "f4")
        self.assertNotIn("f4", out)

    def test_list_output(self):
        self.feature("f5")
        run(self.d, "merge", "f5")
        code, out, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("f5", out)
        self.assertIn("merged", out)

    def test_json(self):
        self.feature("f6")
        code, out, _ = self.cli("--json")
        data = json.loads(out)
        self.assertEqual(data["base"], "main")
        self.assertEqual([r["name"] for r in data["branches"]], ["f6"])

    def test_empty(self):
        code, out, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("no candidate", out)

    def test_delete_merged_only_without_force(self):
        self.feature("m1")
        run(self.d, "merge", "m1")
        self.feature("sq")
        run(self.d, "merge", "--squash", "sq")
        run(self.d, "commit", "-m", "sq")
        code, out, err = self.cli("--delete")
        self.assertEqual(code, 1)
        self.assertNotIn("m1", self.names())
        self.assertIn("sq", self.names())
        self.assertIn("--force", err)

    def test_delete_force(self):
        self.feature("sq")
        run(self.d, "merge", "--squash", "sq")
        run(self.d, "commit", "-m", "sq")
        code, out, err = self.cli("--delete", "--force")
        self.assertEqual(code, 0)
        self.assertNotIn("sq", self.names())

    def test_delete_never_touches_active(self):
        self.feature("act")
        self.cli("--delete", "--force")
        self.assertIn("act", self.names())

    def test_delete_nothing(self):
        code, out, _ = self.cli("--delete")
        self.assertEqual(code, 0)
        self.assertIn("nothing to delete", out)

    def test_only_filter(self):
        self.feature("m2")
        run(self.d, "merge", "m2")
        code, out, _ = self.cli("--only", "stale")
        self.assertIn("no candidate", out)


class Errors(unittest.TestCase):
    def test_not_a_repo(self):
        d = tempfile.mkdtemp()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bs.main([d])
        self.assertEqual(code, 2)
        self.assertIn("branchsweep:", err.getvalue())

    def test_missing_path(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(bs.main(["/no/such/dir/xyz"]), 2)

    def test_bad_base(self):
        d = tempfile.mkdtemp()
        run(d, "init", "-b", "main")
        commit(d, "a", "x")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(bs.main([d, "--base", "nope"]), 2)
        self.assertIn("does not exist", err.getvalue())

    def test_negative_stale(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(bs.main([".", "--stale-days", "-1"]), 2)

    def test_force_without_delete(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(bs.main([".", "--force"]), 2)

    def test_no_commits_repo(self):
        d = tempfile.mkdtemp()
        run(d, "init", "-b", "main")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(bs.main([d]), 2)

    def test_detect_master(self):
        d = tempfile.mkdtemp()
        run(d, "init", "-b", "master")
        commit(d, "a", "x")
        self.assertEqual(bs.detect_base(d), "master")


if __name__ == "__main__":
    unittest.main()
