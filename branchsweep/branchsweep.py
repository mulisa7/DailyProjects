#!/usr/bin/env python3
"""branchsweep: list and optionally delete local git branches that are done with."""
import argparse
import json
import subprocess
import sys
import time

PROTECTED = {"main", "master", "develop", "dev", "trunk"}


class GitError(Exception):
    pass


def git(repo, *args):
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH")
    if p.returncode != 0:
        raise GitError(p.stderr.strip() or "git %s failed" % " ".join(args))
    return p.stdout


def ref_exists(repo, ref):
    try:
        git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        return True
    except GitError:
        return False


def detect_base(repo):
    """Pick the branch other branches are compared against."""
    try:
        head = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
        name = head.rsplit("/", 1)[-1]
        if ref_exists(repo, "refs/heads/" + name):
            return name
    except GitError:
        pass
    for name in ("main", "master", "trunk", "develop"):
        if ref_exists(repo, "refs/heads/" + name):
            return name
    raise GitError("could not find a base branch; pass one with --base")


def list_branches(repo):
    fmt = "%(refname:short)%09%(committerdate:unix)%09%(upstream:track)%09%(subject)"
    out = git(repo, "for-each-ref", "--format=" + fmt, "refs/heads")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        name, ts, track, subject = parts
        rows.append({"name": name, "timestamp": int(ts), "gone": "gone" in track,
                     "subject": subject})
    return rows


def is_merged(repo, base, branch):
    out = git(repo, "branch", "--merged", base, "--format=%(refname:short)")
    return branch in out.split()


def is_squash_merged(repo, base, branch):
    """True if every commit on branch has an equivalent patch already in base."""
    out = git(repo, "cherry", base, branch).splitlines()
    return bool(out) and all(l.startswith("-") for l in out)


def classify(repo, base, stale_days, now=None, extra_protected=()):
    now = time.time() if now is None else now
    if not ref_exists(repo, "refs/heads/" + base):
        raise GitError("base branch '%s' does not exist" % base)
    current = git(repo, "branch", "--show-current").strip()
    merged = set(git(repo, "branch", "--merged", base, "--format=%(refname:short)").split())
    protected = PROTECTED | set(extra_protected) | {base, current}
    result = []
    for b in list_branches(repo):
        age = int((now - b["timestamp"]) // 86400)
        if b["name"] in protected:
            status = "protected"
        elif b["name"] in merged:
            status = "merged"
        elif is_squash_merged(repo, base, b["name"]):
            status = "squash-merged"
        elif b["gone"]:
            status = "upstream-gone"
        elif stale_days is not None and age >= stale_days:
            status = "stale"
        else:
            status = "active"
        result.append({"name": b["name"], "status": status, "age_days": age,
                       "subject": b["subject"]})
    return result


def delete_branches(repo, branches, force):
    """Delete branches. Squash-merged, gone and stale ones need force (-D)."""
    done, failed = [], []
    for b in branches:
        flag = None
        if b["status"] == "merged":
            flag = "-d"
        elif force:
            flag = "-D"
        else:
            failed.append((b["name"], "needs --force (not fully merged by git's rules)"))
            continue
        try:
            git(repo, "branch", flag, b["name"])
            done.append(b["name"])
        except GitError as e:
            failed.append((b["name"], str(e)))
    return done, failed


def build_parser():
    p = argparse.ArgumentParser(prog="branchsweep",
                                description="Find local git branches you can delete.")
    p.add_argument("repo", nargs="?", default=".", help="repository path (default .)")
    p.add_argument("--base", help="base branch (default: origin/HEAD, main, master...)")
    p.add_argument("--stale-days", type=int, default=90,
                   help="unmerged branches older than this are 'stale' (0 disables; default 90)")
    p.add_argument("--keep", action="append", default=[], metavar="NAME",
                   help="extra branch name to protect (repeatable)")
    p.add_argument("--only", choices=["merged", "squash-merged", "upstream-gone", "stale", "active"],
                   action="append", help="show/delete only these statuses (repeatable)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--delete", action="store_true",
                   help="delete candidates (merged ones with -d; others only with --force)")
    p.add_argument("--force", action="store_true",
                   help="with --delete, also delete squash-merged/gone/stale branches (-D)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.stale_days < 0:
        print("branchsweep: --stale-days must be >= 0", file=sys.stderr)
        return 2
    if args.force and not args.delete:
        print("branchsweep: --force only makes sense with --delete", file=sys.stderr)
        return 2
    try:
        git(args.repo, "rev-parse", "--git-dir")
        base = args.base or detect_base(args.repo)
        rows = classify(args.repo, base, args.stale_days or None, extra_protected=args.keep)
    except GitError as e:
        print("branchsweep: %s" % e, file=sys.stderr)
        return 2
    shown = [r for r in rows if r["status"] not in ("protected",)]
    if args.only:
        shown = [r for r in shown if r["status"] in args.only]
    else:
        shown = [r for r in shown if r["status"] != "active"] if not args.json else shown
    if args.delete:
        cands = [r for r in shown if r["status"] != "active"]
        done, failed = delete_branches(args.repo, cands, args.force)
        for n in done:
            print("deleted %s" % n)
        for n, why in failed:
            print("skipped %s: %s" % (n, why), file=sys.stderr)
        if not cands:
            print("nothing to delete (base: %s)" % base)
        return 1 if failed else 0
    if args.json:
        print(json.dumps({"base": base, "branches": shown}, indent=2))
    elif not shown:
        print("no candidate branches (base: %s)" % base)
    else:
        print("base: %s" % base)
        w = max(len(r["name"]) for r in shown)
        for r in shown:
            print("%-*s  %-13s  %4dd  %s" % (w, r["name"], r["status"], r["age_days"], r["subject"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
