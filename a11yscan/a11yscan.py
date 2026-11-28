#!/usr/bin/env python3
"""a11yscan: offline accessibility checks for static HTML files."""
import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
VAGUE_LINKS = {"click here", "here", "read more", "more", "link", "this link",
               "learn more", "details"}
FILENAME_ALT = re.compile(r"^(img|image|dsc|photo|picture|screenshot)[-_ ]?\d*$|\.(png|jpe?g|gif|svg|webp)$", re.I)
NO_LABEL_TYPES = {"hidden", "submit", "button", "reset", "image"}
RULES = {
    "img-alt": "Image has no alt attribute",
    "img-alt-filename": "Alt text looks like a file name or placeholder",
    "html-lang": "<html> has no lang attribute",
    "page-title": "Page has no non-empty <title>",
    "heading-skip": "Heading level skips (for example h2 to h4)",
    "heading-h1": "Page should have exactly one h1",
    "link-name": "Link has no accessible name",
    "link-vague": "Link text does not say where it goes",
    "button-name": "Button has no accessible name",
    "input-label": "Form field has no label",
    "duplicate-id": "id is used more than once",
    "tabindex-positive": "Positive tabindex breaks natural focus order",
    "table-header": "Table has no header cells (th)",
    "iframe-title": "iframe has no title",
    "viewport-zoom": "Viewport blocks zooming",
    "media-autoplay": "Media autoplays",
}


class Scanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.findings = []
        self.stack = []          # open elements: dicts
        self.ids = {}
        self.label_for = set()
        self.labelled_inputs = []  # (line, id, ok_now)
        self.last_heading = 0
        self.h1_count = 0
        self.saw_html = False
        self.html_lang = None
        self.title_text = None
        self.in_title = False
        self.tables = []         # stack of [line, has_th]

    def add(self, rule, line, detail=""):
        self.findings.append({"rule": rule, "line": line,
                              "message": RULES[rule] + (": " + detail if detail else "")})

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        line = self.getpos()[0]
        if "id" in a and a["id"].strip():
            self.ids.setdefault(a["id"].strip(), []).append(line)
        if "tabindex" in a:
            try:
                if int(a["tabindex"].strip()) > 0:
                    self.add("tabindex-positive", line)
            except ValueError:
                pass
        if tag == "html":
            self.saw_html = True
            self.html_lang = a.get("lang", "").strip()
        elif tag == "title":
            self.in_title = True
            self.title_text = ""
        elif tag == "meta" and a.get("name", "").lower() == "viewport":
            c = a.get("content", "").lower().replace(" ", "")
            if "user-scalable=no" in c or "user-scalable=0" in c or \
               re.search(r"maximum-scale=1(\.0)?(,|$)", c):
                self.add("viewport-zoom", line)
        elif tag == "img":
            self.check_img(a, line)
        elif re.fullmatch(r"h[1-6]", tag):
            lvl = int(tag[1])
            if lvl == 1:
                self.h1_count += 1
            if self.last_heading and lvl > self.last_heading + 1:
                self.add("heading-skip", line, "h%d after h%d" % (lvl, self.last_heading))
            self.last_heading = lvl
        elif tag == "table":
            self.tables.append([line, False])
        elif tag == "th" and self.tables:
            self.tables[-1][1] = True
        elif tag == "iframe":
            if not (a.get("title", "").strip() or a.get("aria-label", "").strip()):
                self.add("iframe-title", line)
        elif tag in ("video", "audio") and "autoplay" in a:
            self.add("media-autoplay", line)
        elif tag == "label" and a.get("for"):
            self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            self.check_field(tag, a, line)
        if tag in ("a", "button", "label"):
            self.stack.append({"tag": tag, "line": line, "text": "",
                               "named": bool(a.get("aria-label", "").strip()
                                             or a.get("aria-labelledby", "").strip()),
                               "href": "href" in a, "role": a.get("role", "")})

    def check_img(self, a, line):
        if "alt" not in a and a.get("role") not in ("presentation", "none"):
            self.add("img-alt", line, a.get("src", "")[:60])
        elif a.get("alt", "").strip() and FILENAME_ALT.search(a["alt"].strip()):
            self.add("img-alt-filename", line, repr(a["alt"].strip()))
        if self.stack and self.stack[-1]["tag"] in ("a", "button", "label") and \
                a.get("alt", "").strip():
            for el in self.stack:
                el["text"] += a["alt"]

    def check_field(self, tag, a, line):
        if tag == "input" and a.get("type", "text").lower() in NO_LABEL_TYPES:
            return
        named = bool(a.get("aria-label", "").strip() or a.get("aria-labelledby", "").strip()
                     or a.get("title", "").strip())
        wrapped = any(e["tag"] == "label" for e in self.stack)
        self.labelled_inputs.append((line, a.get("id", "").strip(), named or wrapped))

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        for el in self.stack:
            el["text"] += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "table" and self.tables:
            line, has_th = self.tables.pop()
            if not has_th:
                self.add("table-header", line)
        if tag in ("a", "button", "label"):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] == tag:
                    el = self.stack.pop(i)
                    self.finish(el)
                    break

    def finish(self, el):
        text = re.sub(r"\s+", " ", el["text"]).strip()
        if el["tag"] == "a" and el["href"]:
            if not text and not el["named"]:
                self.add("link-name", el["line"])
            elif text.lower().strip(" .!") in VAGUE_LINKS and not el["named"]:
                self.add("link-vague", el["line"], repr(text))
        elif el["tag"] == "button":
            if not text and not el["named"]:
                self.add("button-name", el["line"])

    def finalize(self):
        if self.saw_html and not self.html_lang:
            self.add("html-lang", 1)
        if self.saw_html and not (self.title_text or "").strip():
            self.add("page-title", 1)
        if self.saw_html and self.h1_count != 1:
            self.add("heading-h1", 1, "found %d" % self.h1_count)
        for ident, lines in self.ids.items():
            if len(lines) > 1:
                self.add("duplicate-id", lines[1], repr(ident))
        for line, ident, ok in self.labelled_inputs:
            if not ok and not (ident and ident in self.label_for):
                self.add("input-label", line)
        self.findings.sort(key=lambda f: (f["line"], f["rule"]))


def scan_html(text):
    """Return a list of findings for an HTML string."""
    s = Scanner()
    s.feed(text)
    s.close()
    s.finalize()
    return s.findings


def read_file(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def collect(paths):
    files, missing = [], []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in (".git", "node_modules"))
                files += [os.path.join(root, n) for n in sorted(names)
                          if n.lower().endswith((".html", ".htm"))]
        elif os.path.isfile(p):
            files.append(p)
        else:
            missing.append(p)
    return files, missing


def main(argv=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    ap = argparse.ArgumentParser(prog="a11yscan",
                                 description="Offline accessibility checks for static HTML.")
    ap.add_argument("paths", nargs="*", help="HTML files or folders")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--ignore", default="", help="comma-separated rule ids to skip")
    ap.add_argument("--list-rules", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.list_rules:
        for k, v in RULES.items():
            print("%-18s %s" % (k, v), file=out)
        return 0
    if not args.paths:
        print("a11yscan: no files or folders given", file=err)
        return 2
    ignore = {x.strip() for x in args.ignore.split(",") if x.strip()}
    unknown = ignore - set(RULES)
    if unknown:
        print("a11yscan: unknown rule(s): " + ", ".join(sorted(unknown)), file=err)
        return 2
    files, missing = collect(args.paths)
    for m in missing:
        print("a11yscan: not found: " + m, file=err)
    if missing:
        return 2
    if not files:
        print("a11yscan: no .html or .htm files found", file=err)
        return 2
    results = {}
    for f in files:
        try:
            found = scan_html(read_file(f))
        except OSError as e:
            print("a11yscan: cannot read %s: %s" % (f, e), file=err)
            return 2
        results[f] = [x for x in found if x["rule"] not in ignore]
    total = sum(len(v) for v in results.values())
    if args.json:
        json.dump({"files": results, "total": total}, out, indent=2)
        out.write("\n")
    else:
        for f, found in results.items():
            for x in found:
                print("%s:%d: [%s] %s" % (f, x["line"], x["rule"], x["message"]), file=out)
        print("%d issue(s) in %d file(s)" % (total, len(files)), file=out)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
