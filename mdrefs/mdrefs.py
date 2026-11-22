#!/usr/bin/env python3
"""mdrefs: offline checker for relative links and heading anchors in Markdown files."""
import argparse
import os
import re
import sys
from urllib.parse import unquote

EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^()\s]*(?:\([^()\s]*\)[^()\s]*)*)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REFDEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]*>|\S+)")
REFUSE = re.compile(r"!?\[[^\[\]]*\]\[([^\]]*)\]")
CODESPAN = re.compile(r"`+[^`]*`+")
HTMLID = re.compile(r"""<[a-zA-Z][^>]*\s(?:id|name)=["']([^"']+)["']""")
MD_EXT = (".md", ".markdown")


def slugify(text):
    """GitHub-style heading slug."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", "", text)
    text = text.strip().lower()
    out = []
    for ch in text:
        if ch.isalnum() or ch in "_-":
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)


def strip_code(lines):
    """Yield (lineno, text) for lines outside fenced code, inline code removed."""
    fence = None
    for i, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        yield i, CODESPAN.sub("", line)


def collect_anchors(text):
    anchors = set()
    counts = {}
    for _, line in strip_code(text.splitlines()):
        m = HEADING.match(line)
        if m:
            slug = slugify(m.group(2))
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            anchors.add(slug if n == 0 else "%s-%d" % (slug, n))
        anchors.update(HTMLID.findall(line))
    return anchors


def extract_links(text):
    """Return list of (lineno, target)."""
    links = []
    defs = {}
    lines = list(strip_code(text.splitlines()))
    for i, line in lines:
        m = REFDEF.match(line)
        if m:
            defs[m.group(1).strip().lower()] = (i, m.group(2))
    for i, line in lines:
        if REFDEF.match(line):
            continue
        for m in INLINE.finditer(line):
            links.append((i, m.group(1)))
        for m in REFUSE.finditer(line):
            label = m.group(1).strip().lower()
            if label in defs and label:
                continue
            if label and label not in defs:
                links.append((i, "ref:" + label))
    for label, (i, target) in defs.items():
        links.append((i, target))
    return sorted(set(links))


class Checker:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._anchors = {}

    def anchors_of(self, path):
        if path not in self._anchors:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    self._anchors[path] = collect_anchors(f.read())
            except OSError:
                self._anchors[path] = set()
        return self._anchors[path]

    def check_file(self, path):
        problems = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            return [(0, "", "cannot read file: %s" % e.strerror)]
        base = os.path.dirname(os.path.abspath(path))
        for lineno, target in extract_links(text):
            if target.startswith("ref:"):
                problems.append((lineno, target[4:], "reference-style link has no definition"))
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            target = target.strip()
            if not target:
                problems.append((lineno, "", "empty link target"))
                continue
            if EXTERNAL.match(target):
                continue
            frag = None
            if "#" in target:
                target, frag = target.split("#", 1)
            target = unquote(target.split("?", 1)[0])
            if target:
                dest = os.path.normpath(os.path.join(self.root, target.lstrip("/")) if target.startswith("/") else os.path.join(base, target))
                if not dest.startswith(self.root):
                    problems.append((lineno, target, "points outside the checked root"))
                    continue
                if not os.path.exists(dest):
                    problems.append((lineno, target, "file not found"))
                    continue
            else:
                dest = os.path.abspath(path)
            if frag:
                frag = unquote(frag)
                if os.path.isdir(dest) or not dest.lower().endswith(MD_EXT):
                    continue  # cannot verify anchors outside Markdown files
                if frag.lower() not in {a.lower() for a in self.anchors_of(dest)}:
                    shown = (target or "") + "#" + frag
                    problems.append((lineno, shown, "no heading or id matches this anchor"))
        return problems


def find_markdown(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for d, dirs, names in os.walk(p):
                dirs[:] = sorted(x for x in dirs if x not in (".git", "node_modules"))
                files += [os.path.join(d, n) for n in sorted(names) if n.lower().endswith(MD_EXT)]
        else:
            files.append(p)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mdrefs", description="Check relative links and heading anchors in Markdown files, offline.")
    ap.add_argument("paths", nargs="*", default=["."], help="files or folders (default: current folder)")
    ap.add_argument("--root", help="folder that /absolute links resolve against (default: first folder given, or cwd)")
    args = ap.parse_args(argv)
    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print("mdrefs: no such file or folder: %s" % ", ".join(missing), file=sys.stderr)
        return 2
    root = args.root or (args.paths[0] if os.path.isdir(args.paths[0]) else os.path.dirname(os.path.abspath(args.paths[0])))
    if not os.path.isdir(root):
        print("mdrefs: root is not a folder: %s" % root, file=sys.stderr)
        return 2
    files = find_markdown(args.paths)
    if not files:
        print("mdrefs: no Markdown files found")
        return 0
    checker = Checker(root)
    total = 0
    for f in files:
        for lineno, target, msg in checker.check_file(f):
            total += 1
            print("%s:%d: %s: %s" % (os.path.relpath(f), lineno, msg, target))
    print("%d file(s) checked, %d problem(s)" % (len(files), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
