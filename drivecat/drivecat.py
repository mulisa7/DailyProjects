#!/usr/bin/env python3
"""drivecat - keep a searchable catalog of what is on drives that are not plugged in."""

import argparse
import fnmatch
import os
import sqlite3
import sys
import time
from collections import defaultdict

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".drivecat.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS disks (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    scanned_at INTEGER NOT NULL,
    skipped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS files (
    disk_id INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS files_disk ON files(disk_id);
CREATE INDEX IF NOT EXISTS files_name ON files(name);
"""


class CatError(Exception):
    """Problem the user can fix; reported without a traceback."""


def human(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def parse_size(text):
    """Turn 500, 10k, 2.5MB or 1g into bytes."""
    s = text.strip().lower().rstrip("b")
    mult = 1
    if s and s[-1] in "kmgt":
        mult = 1024 ** ("kmgt".index(s[-1]) + 1)
        s = s[:-1]
    try:
        value = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a size: {text!r}")
    if value < 0:
        raise argparse.ArgumentTypeError(f"size cannot be negative: {text!r}")
    return int(value * mult)


def connect(path):
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        raise CatError(f"catalog folder does not exist: {parent}")
    con = None
    try:
        con = sqlite3.connect(path)
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(SCHEMA)
    except sqlite3.Error as exc:
        if con is not None:
            con.close()
        raise CatError(f"cannot open catalog {path}: {exc}")
    return con


def find_disk(con, label):
    row = con.execute("SELECT id, root FROM disks WHERE label = ?", (label,)).fetchone()
    if row is None:
        known = [r[0] for r in con.execute("SELECT label FROM disks ORDER BY label")]
        hint = f" Known disks: {', '.join(known)}." if known else " The catalog is empty; run 'scan' first."
        raise CatError(f"no disk labelled {label!r}.{hint}")
    return row


def scan_tree(root):
    """Return (rows, skipped). Rows are (relative posix path, name, size, mtime)."""
    rows = []
    skipped = [0]

    def on_error(_exc):
        skipped[0] += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            try:
                if os.path.islink(full):
                    continue
                st = os.stat(full)
            except OSError:
                skipped[0] += 1
                continue
            rel = fname if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/" + fname
            rows.append((rel, fname, st.st_size, int(st.st_mtime)))
    return rows, skipped[0]


def cmd_scan(args, con, out, err):
    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        raise CatError(f"not a folder: {args.path}")
    label = args.label or os.path.basename(root.rstrip("\\/")) or root
    if not label.strip():
        raise CatError("label is empty")
    rows, skipped = scan_tree(root)
    with con:
        con.execute("DELETE FROM disks WHERE label = ?", (label,))
        cur = con.execute(
            "INSERT INTO disks(label, root, scanned_at, skipped) VALUES (?,?,?,?)",
            (label, root, int(time.time()), skipped),
        )
        disk_id = cur.lastrowid
        con.executemany(
            "INSERT INTO files(disk_id, path, name, size, mtime) VALUES (?,?,?,?,?)",
            [(disk_id,) + r for r in rows],
        )
    total = sum(r[2] for r in rows)
    out.write(f"{label}: {len(rows)} files, {human(total)} cataloged\n")
    if skipped:
        err.write(f"warning: {skipped} entries could not be read and were skipped\n")
    if not rows:
        err.write("warning: the folder contains no files\n")
    return 0


def cmd_disks(args, con, out, err):
    rows = con.execute(
        """SELECT d.label, d.root, d.scanned_at, d.skipped, COUNT(f.path), COALESCE(SUM(f.size), 0)
           FROM disks d LEFT JOIN files f ON f.disk_id = d.id
           GROUP BY d.id ORDER BY d.label"""
    ).fetchall()
    if not rows:
        out.write("No disks cataloged yet. Run: drivecat scan <folder> --label <name>\n")
        return 0
    for label, root, ts, skipped, n, total in rows:
        when = time.strftime("%Y-%m-%d", time.localtime(ts))
        extra = f", {skipped} unreadable" if skipped else ""
        out.write(f"{label:<20} {n:>8} files {human(total):>10}  scanned {when}  from {root}{extra}\n")
    return 0


def make_matcher(pattern):
    pat = pattern.lower()
    if any(c in pat for c in "*?["):
        if "/" in pat:
            return lambda path, name: fnmatch.fnmatchcase(path.lower(), pat)
        return lambda path, name: fnmatch.fnmatchcase(name.lower(), pat)
    return lambda path, name: pat in path.lower()


def cmd_search(args, con, out, err):
    if not args.pattern.strip():
        raise CatError("search pattern is empty")
    if con.execute("SELECT COUNT(*) FROM disks").fetchone()[0] == 0:
        raise CatError("the catalog is empty; run 'scan' first")
    match = make_matcher(args.pattern)
    sql = "SELECT d.label, f.path, f.name, f.size FROM files f JOIN disks d ON d.id = f.disk_id"
    params = []
    where = []
    if args.label:
        find_disk(con, args.label)
        where.append("d.label = ?")
        params.append(args.label)
    if args.min_size:
        where.append("f.size >= ?")
        params.append(args.min_size)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.label, f.path"
    shown = 0
    more = 0
    for label, path, name, size in con.execute(sql, params):
        if not match(path, name):
            continue
        if shown >= args.limit:
            more += 1
            continue
        out.write(f"[{label}] {path}  ({human(size)})\n")
        shown += 1
    if shown == 0:
        out.write("No matches.\n")
        return 1
    if more:
        out.write(f"... {more} more, raise --limit to see them\n")
    return 0


def disk_files(con, disk_id):
    return con.execute("SELECT path, size FROM files WHERE disk_id = ?", (disk_id,)).fetchall()


def cmd_ls(args, con, out, err):
    disk_id, _root = find_disk(con, args.label)
    prefix = args.dir.strip("/")
    prefix = prefix + "/" if prefix else ""
    seen = 0
    dirs = defaultdict(lambda: [0, 0])
    entries = []
    for path, size in disk_files(con, disk_id):
        if not path.startswith(prefix):
            continue
        seen += 1
        rest = path[len(prefix):]
        if "/" in rest:
            d = rest.split("/", 1)[0]
            dirs[d][0] += 1
            dirs[d][1] += size
        else:
            entries.append((rest, size))
    if seen == 0:
        raise CatError(f"nothing under {args.dir!r} on {args.label!r}")
    for d in sorted(dirs, key=str.lower):
        n, total = dirs[d]
        out.write(f"{d + '/':<40} {human(total):>10}  {n} files\n")
    for name, size in sorted(entries, key=lambda e: e[0].lower()):
        out.write(f"{name:<40} {human(size):>10}\n")
    return 0


def cmd_big(args, con, out, err):
    disk_id, _root = find_disk(con, args.label)
    if args.depth < 1:
        raise CatError("--depth must be at least 1")
    rows = disk_files(con, disk_id)
    if not rows:
        raise CatError(f"{args.label!r} has no files cataloged")
    totals = defaultdict(lambda: [0, 0])
    for path, size in rows:
        parts = path.split("/")[:-1][: args.depth]
        key = "/".join(parts) + "/" if parts else "(top level files)"
        totals[key][0] += 1
        totals[key][1] += size
    ranked = sorted(totals.items(), key=lambda kv: kv[1][1], reverse=True)[: args.top]
    for key, (n, total) in ranked:
        out.write(f"{human(total):>10}  {n:>7} files  {key}\n")
    return 0


def cmd_dupes(args, con, out, err):
    groups = defaultdict(list)
    for label, path, name, size in con.execute(
        "SELECT d.label, f.path, f.name, f.size FROM files f JOIN disks d ON d.id = f.disk_id WHERE f.size >= ?",
        (args.min_size,),
    ):
        groups[(name.lower(), size)].append((label, path))
    found = [(k, v) for k, v in groups.items() if len(v) > 1]
    if args.across_disks:
        found = [(k, v) for k, v in found if len({label for label, _ in v}) > 1]
    if not found:
        out.write("No duplicates found.\n")
        return 0
    found.sort(key=lambda kv: (-kv[0][1] * (len(kv[1]) - 1), kv[0][0]))
    for (name, size), copies in found[: args.limit]:
        out.write(f"{name}  {human(size)}  x{len(copies)}\n")
        for label, path in sorted(copies):
            out.write(f"    [{label}] {path}\n")
    wasted = sum(size * (len(copies) - 1) for (_n, size), copies in found)
    out.write(f"{len(found)} groups of same-name, same-size files; about {human(wasted)} in extra copies\n")
    out.write("Matching is by name and size only, contents are not compared.\n")
    return 0


def cmd_forget(args, con, out, err):
    find_disk(con, args.label)
    with con:
        con.execute("DELETE FROM disks WHERE label = ?", (args.label,))
    out.write(f"removed {args.label} from the catalog\n")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="drivecat", description="Catalog drives so you can search them while they are unplugged.")
    p.add_argument("--db", default=os.environ.get("DRIVECAT_DB", DEFAULT_DB), help="catalog file (env DRIVECAT_DB, default ~/.drivecat.db)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="catalog a folder or mounted drive (re-scanning a label replaces it)")
    s.add_argument("path")
    s.add_argument("--label", help="name for this disk (default: folder name)")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("disks", help="list cataloged disks")
    s.set_defaults(func=cmd_disks)

    s = sub.add_parser("search", help="find files by substring or glob across all disks")
    s.add_argument("pattern", help="holiday matches the path; *.mkv or report_??.pdf matches the file name")
    s.add_argument("--label")
    s.add_argument("--min-size", type=parse_size, default=0, metavar="SIZE", help="for example 500m or 2g")
    s.add_argument("--limit", type=int, default=200)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("ls", help="list one folder of a disk")
    s.add_argument("label")
    s.add_argument("dir", nargs="?", default="")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("big", help="largest folders on a disk")
    s.add_argument("label")
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--depth", type=int, default=1)
    s.set_defaults(func=cmd_big)

    s = sub.add_parser("dupes", help="files with the same name and size")
    s.add_argument("--min-size", type=parse_size, default=1, metavar="SIZE")
    s.add_argument("--across-disks", action="store_true", help="only groups that span more than one disk")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_dupes)

    s = sub.add_parser("forget", help="remove a disk from the catalog")
    s.add_argument("label")
    s.set_defaults(func=cmd_forget)
    return p


def run(argv, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    for name in ("limit", "top"):
        if getattr(args, name, 1) < 1:
            err.write(f"drivecat: --{name} must be at least 1\n")
            return 2
    try:
        con = connect(args.db)
        try:
            return args.func(args, con, out, err)
        finally:
            con.close()
    except CatError as exc:
        err.write(f"drivecat: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
