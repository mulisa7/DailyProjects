#!/usr/bin/env python3
"""jsonshape: summarise the structure of a JSON or NDJSON file."""
import argparse
import json
import sys

EXIT_OK, EXIT_ERR, EXIT_USAGE = 0, 1, 2


def type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def load_documents(text, fmt="auto"):
    """Return a list of parsed documents. fmt: auto, json, ndjson."""
    if not text.strip():
        raise ValueError("input is empty")
    if fmt in ("auto", "json"):
        try:
            return [json.loads(text)]
        except json.JSONDecodeError as e:
            if fmt == "json":
                raise ValueError(f"invalid JSON at line {e.lineno} column {e.colno}: {e.msg}")
    docs = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            docs.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON on line {n}: {e.msg} (not valid as a single document either)")
    if not docs:
        raise ValueError("input is empty")
    return docs


class Node:
    def __init__(self):
        self.count = 0
        self.types = {}
        self.num_min = None
        self.num_max = None
        self.len_min = None
        self.len_max = None
        self.example = None

    def add(self, v):
        self.count += 1
        t = type_name(v)
        self.types[t] = self.types.get(t, 0) + 1
        if t in ("integer", "number"):
            self.num_min = v if self.num_min is None else min(self.num_min, v)
            self.num_max = v if self.num_max is None else max(self.num_max, v)
        if t in ("string", "array"):
            n = len(v)
            self.len_min = n if self.len_min is None else min(self.len_min, n)
            self.len_max = n if self.len_max is None else max(self.len_max, n)
        if t == "string" and self.example is None and v != "":
            self.example = v[:30]


def walk(v, path, nodes, parent_count, max_depth, depth=0):
    node = nodes.setdefault(path, Node())
    node.add(v)
    if depth >= max_depth:
        return
    if isinstance(v, dict):
        for k, child in v.items():
            walk(child, f"{path}.{k}" if path != "$" else f"$.{k}", nodes, 0, max_depth, depth + 1)
    elif isinstance(v, list):
        for child in v:
            walk(child, path + "[]", nodes, 0, max_depth, depth + 1)


def analyse(docs, max_depth=8):
    nodes = {}
    for d in docs:
        walk(d, "$", nodes, 0, max_depth)
    return nodes


def parent_path(path):
    if path.endswith("[]"):
        return path[:-2]
    i = path.rfind(".")
    return path[:i] if i > 0 else None


def fmt_num(x):
    return str(int(x)) if isinstance(x, float) and x.is_integer() else f"{x:g}" if isinstance(x, float) else str(x)


def describe(path, node, nodes):
    parts = []
    tn = sorted(node.types.items(), key=lambda kv: -kv[1])
    if len(tn) == 1:
        parts.append(tn[0][0])
    else:
        parts.append(" | ".join(f"{t} {c}" for t, c in tn) + "  (mixed)")
    p = parent_path(path)
    if p is not None and p in nodes and not path.endswith("[]"):
        # presence = how often this key appears among parent objects
        obj_count = nodes[p].types.get("object", 0)
        if obj_count and node.count < obj_count:
            parts.append(f"present {node.count}/{obj_count} ({100 * node.count // obj_count}%)")
    if node.num_min is not None:
        parts.append(f"range {fmt_num(node.num_min)}..{fmt_num(node.num_max)}")
    if node.len_min is not None:
        label = "length" if "string" in node.types else "items"
        parts.append(f"{label} {node.len_min}..{node.len_max}")
    if node.example is not None:
        parts.append(f"e.g. {json.dumps(node.example)}")
    return parts


def render(nodes):
    lines = []
    for path in nodes:  # insertion order = first seen
        depth = path.count(".") + path.count("[]")
        label = path if depth == 0 else path.split(".")[-1] if not path.endswith("[]") else "[]"
        if path.endswith("[]"):
            label = "[]"
        lines.append("  " * depth + f"{label}: " + ", ".join(describe(path, nodes[path], nodes)))
    return "\n".join(lines)


def to_json(nodes):
    out = {}
    for path, n in nodes.items():
        out[path] = {"count": n.count, "types": n.types,
                     "min": n.num_min, "max": n.num_max,
                     "length_min": n.len_min, "length_max": n.len_max}
    return out


def main(argv=None, stdin=None, stdout=None, stderr=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    ap = argparse.ArgumentParser(prog="jsonshape", description="Summarise the structure of JSON or NDJSON.")
    ap.add_argument("file", nargs="?", default="-", help="file path, or - for stdin")
    ap.add_argument("--format", choices=["auto", "json", "ndjson"], default="auto")
    ap.add_argument("--max-depth", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    if args.max_depth < 0:
        print("error: --max-depth must be 0 or more", file=stderr)
        return EXIT_USAGE
    try:
        if args.file == "-":
            text = stdin.read()
        else:
            with open(args.file, encoding="utf-8-sig") as f:
                text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read {args.file}: {e}", file=stderr)
        return EXIT_ERR
    text = text.lstrip("﻿")
    fmt = args.format
    try:
        docs = load_documents(text, fmt)
    except ValueError as e:
        print(f"error: {e}", file=stderr)
        return EXIT_ERR
    # NDJSON: summarise records as the root
    nodes = analyse(docs, args.max_depth)
    if args.json:
        json.dump(to_json(nodes), stdout, indent=2)
        stdout.write("\n")
    else:
        if len(docs) > 1:
            print(f"{len(docs)} records", file=stdout)
        print(render(nodes), file=stdout)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
