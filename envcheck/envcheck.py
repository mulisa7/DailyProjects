#!/usr/bin/env python3
"""envcheck - compare a .env file against .env.example and optionally
against the environment variables your source code actually reads.

Exit codes: 0 = ok, 1 = problems found, 2 = bad usage / unreadable file.
"""
import argparse
import json
import os
import re
import sys

__version__ = "0.1.0"

LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")

# Patterns for env var reads in common languages.
USAGE_PATTERNS = [
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\.Getenv\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\"\s*\)"),
    re.compile(r"import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
]
SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
# Provided by the runtime, never expected in .env.
RUNTIME_VARS = {"NODE_ENV", "PATH", "HOME", "PWD", "USER"}


class EnvFileError(Exception):
    pass


def parse_env(text):
    """Return {KEY: value}. Handles export, comments, quotes, inline comments."""
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest[:1] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            value = rest[1:end] if end != -1 else rest[1:]
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
        values[key] = value
    return values


def load_env(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return parse_env(f.read())
    except OSError as e:
        raise EnvFileError(f"cannot read {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise EnvFileError(f"{path} is not valid UTF-8 text")


def scan_usage(root):
    """Return {KEY: [relative file paths]} for env reads found under root."""
    found = {}
    if not os.path.isdir(root):
        raise EnvFileError(f"scan path is not a directory: {root}")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1] not in SOURCE_EXTS:
                continue
            full = os.path.join(dirpath, name)
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for pat in USAGE_PATTERNS:
                for key in pat.findall(text):
                    files = found.setdefault(key, [])
                    rel = os.path.relpath(full, root)
                    if rel not in files:
                        files.append(rel)
    return found


def compare(example, env, used=None):
    report = {
        "missing": sorted(set(example) - set(env)),
        "extra": sorted(set(env) - set(example)),
        "empty": sorted(k for k in env if k in example and env[k] == ""),
    }
    if used is not None:
        known = set(example) | RUNTIME_VARS
        report["undocumented"] = sorted(k for k in used if k not in known)
        report["unused"] = sorted(k for k in example if k not in used)
    return report


def has_problems(report, strict):
    if report["missing"] or report.get("undocumented"):
        return True
    if strict and (report["extra"] or report["empty"] or report.get("unused")):
        return True
    return False


def format_report(report, used):
    labels = [
        ("missing", "Missing from .env (listed in example)"),
        ("empty", "Present but empty"),
        ("extra", "In .env but not in example"),
        ("undocumented", "Read by code but not in example"),
        ("unused", "In example but never read by code"),
    ]
    out = []
    for key, label in labels:
        items = report.get(key)
        if not items:
            continue
        out.append(f"{label}:")
        for item in items:
            where = ""
            if key == "undocumented" and used:
                where = "  (" + ", ".join(used[item][:3]) + ")"
            out.append(f"  - {item}{where}")
    return "\n".join(out) if out else "All good. .env matches the example."


def build_parser():
    p = argparse.ArgumentParser(
        prog="envcheck",
        description="Compare .env against .env.example and find missing env vars.",
    )
    p.add_argument("--env", default=".env", help="env file to check (default: .env)")
    p.add_argument("--example", default=".env.example",
                   help="template file (default: .env.example)")
    p.add_argument("--scan", metavar="DIR",
                   help="also scan source files in DIR for env var reads")
    p.add_argument("--strict", action="store_true",
                   help="also fail on extra, empty and unused keys")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--version", action="version", version=f"envcheck {__version__}")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        example = load_env(args.example)
        env = load_env(args.env)
        used = scan_usage(args.scan) if args.scan else None
    except EnvFileError as e:
        print(f"envcheck: {e}", file=sys.stderr)
        return 2

    if not example and not args.scan:
        print(f"envcheck: {args.example} has no variables to compare", file=sys.stderr)
        return 2

    report = compare(example, env, used)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report, used))
    return 1 if has_problems(report, args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
