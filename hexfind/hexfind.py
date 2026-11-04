"""hexfind: search binary files for a structure instead of a fixed byte string.

A pattern is a list of whitespace-separated elements that must match one after
another, starting at some offset. Elements:

    4B 50            literal bytes (pairs of hex digits, may be joined: 504B0304)
    str(PK)          literal ASCII text, no spaces
    ??               any single byte
    *N               any N bytes
    u16le>=10        unsigned/signed integer field with an optional constraint
    name:u32be<4096  the same, with a name shown in the output

Integer types: u8 u16 u32 u64 i8 i16 i32 i64, followed by le or be (not for
8-bit). Constraints: == != < <= > >= and = (same as ==); the right side is a
decimal or 0x number, a range lo..hi (inclusive), or a list a|b|c.
"""

import json
import mmap
import os
import re
import struct
import sys

MAX_SKIP = 1 << 20


class PatternError(ValueError):
    pass


_NUM = r"-?(?:0[xX][0-9a-fA-F]+|\d+)"
_TOKEN_NAME = re.compile(r"^(?:([A-Za-z_]\w*):)?(.+)$")
_INT = re.compile(r"^([ui])(8|16|32|64)(le|be)?(.*)$")
_HEX = re.compile(r"^(?:[0-9a-fA-F]{2})+$")
_OPS = ("==", "!=", ">=", "<=", ">", "<", "=")


def _num(text, token):
    try:
        return int(text, 0)
    except ValueError:
        raise PatternError("bad number %r in %r" % (text, token))


class Element:
    """One piece of a pattern. size is fixed, so a full pattern has a fixed length."""

    def __init__(self, size, name=None, literal=None, fmt=None, test=None, label=None):
        self.size = size
        self.name = name
        self.literal = literal
        self.fmt = fmt
        self.test = test
        self.label = label or name
        self.wild = literal is None and fmt is None

    def match(self, data, off):
        if self.literal is not None:
            return data[off:off + self.size] == self.literal, None
        if self.fmt is None:
            return True, None
        value = struct.unpack_from(self.fmt, data, off)[0]
        if self.test is not None and not self.test(value):
            return False, value
        return True, value


def _parse_constraint(text, token, lo_limit, hi_limit):
    if not text:
        return None
    op = next((o for o in _OPS if text.startswith(o)), None)
    if op is None:
        raise PatternError("bad constraint %r in %r" % (text, token))
    rhs = text[len(op):]
    if not rhs:
        raise PatternError("missing value after %s in %r" % (op, token))
    if op in ("=", "=="):
        if ".." in rhs:
            lo_s, _, hi_s = rhs.partition("..")
            lo, hi = _num(lo_s, token), _num(hi_s, token)
            if lo > hi:
                raise PatternError("empty range %r in %r" % (rhs, token))
            return lambda v: lo <= v <= hi
        if "|" in rhs:
            vals = {_num(p, token) for p in rhs.split("|")}
            return lambda v: v in vals
    n = _num(rhs, token)
    if not lo_limit <= n <= hi_limit:
        raise PatternError("value %d does not fit the field type in %r" % (n, token))
    return {
        "=": lambda v: v == n,
        "==": lambda v: v == n,
        "!=": lambda v: v != n,
        "<": lambda v: v < n,
        "<=": lambda v: v <= n,
        ">": lambda v: v > n,
        ">=": lambda v: v >= n,
    }[op]


def parse_pattern(text):
    tokens = text.split()
    if not tokens:
        raise PatternError("empty pattern")
    elements = []
    for token in tokens:
        m = _TOKEN_NAME.match(token)
        name, body = m.group(1), m.group(2)
        if body == "??":
            elements.append(Element(1, name))
        elif body.startswith("*"):
            if not body[1:].isdigit() or int(body[1:]) < 1:
                raise PatternError("bad skip %r: use *N with N >= 1" % token)
            n = int(body[1:])
            if n > MAX_SKIP:
                raise PatternError("skip too large in %r" % token)
            elements.append(Element(n, name))
        elif body.startswith("str(") and body.endswith(")"):
            raw = body[4:-1]
            if not raw:
                raise PatternError("empty string in %r" % token)
            try:
                lit = raw.encode("ascii")
            except UnicodeEncodeError:
                raise PatternError("str() takes ASCII only: %r" % token)
            elements.append(Element(len(lit), name, literal=lit))
        elif _HEX.match(body):
            lit = bytes.fromhex(body)
            elements.append(Element(len(lit), name, literal=lit))
        else:
            im = _INT.match(body)
            if not im:
                raise PatternError("cannot parse element %r" % token)
            sign, bits, endian, rest = im.group(1), int(im.group(2)), im.group(3), im.group(4)
            if bits == 8:
                if endian:
                    raise PatternError("8-bit types take no endianness: %r" % token)
            elif not endian:
                raise PatternError("%s%d needs le or be: %r" % (sign, bits, token))
            code = {8: "b", 16: "h", 32: "i", 64: "q"}[bits]
            if sign == "u":
                code = code.upper()
            fmt = ("<" if endian == "le" else ">") + code
            if sign == "u":
                lo, hi = 0, (1 << bits) - 1
            else:
                lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
            test = _parse_constraint(rest, token, lo, hi)
            label = name or "%s%d%s" % (sign, bits, endian or "")
            elements.append(Element(bits // 8, name, fmt=fmt, test=test, label=label))
    return elements


def pattern_length(elements):
    return sum(e.size for e in elements)


def find_matches(data, elements, start=0, end=None, align=1):
    """Yield (offset, fields) for every offset where the whole pattern matches.

    fields is a list of (label, value) for the integer elements and for any
    other element that was given a name (the value is then the raw bytes).
    """
    total = pattern_length(elements)
    end = len(data) if end is None else min(end, len(data))
    last = end - total
    first = elements[0]
    prefix = first.literal
    pos = max(start, 0)
    while pos <= last:
        if prefix is not None:
            hit = data.find(prefix, pos, end)
            if hit < 0 or hit > last:
                return
            pos = hit
        if align > 1 and pos % align:
            pos += align - pos % align
            continue
        off = pos
        fields = []
        ok = True
        for el in elements:
            good, value = el.match(data, off)
            if not good:
                ok = False
                break
            if el.fmt is not None:
                fields.append((el.label, value))
            elif el.name:
                fields.append((el.name, bytes(data[off:off + el.size])))
            off += el.size
        if ok:
            yield pos, fields
        pos += 1


def _show_bytes(raw, limit=24):
    s = raw[:limit].hex(" ")
    return s + (" ..." if len(raw) > limit else "")


def _fmt_value(v):
    return v.hex() if isinstance(v, (bytes, bytearray)) else str(v)


def _open_data(path):
    """Return (data, closer). Empty files give b"" since mmap rejects them."""
    f = open(path, "rb")
    try:
        if os.fstat(f.fileno()).st_size == 0:
            f.close()
            return b"", lambda: None
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except Exception:
        f.close()
        raise

    def close():
        mm.close()
        f.close()

    return mm, close


def _parse_int_arg(text, what):
    try:
        v = int(text, 0)
    except ValueError:
        raise PatternError("%s must be a number, got %r" % (what, text))
    if v < 0:
        raise PatternError("%s cannot be negative" % what)
    return v


USAGE = """usage: hexfind [options] PATTERN FILE [FILE ...]

options:
  -n, --max N        stop after N matches per file
  -c, --count        print only the number of matches per file
  -o, --offsets      print only offsets
  --json             one JSON object per match
  --align N          only try offsets that are multiples of N
  --start OFFSET     first offset to try (decimal or 0x)
  --end OFFSET       stop searching at this offset
  --no-overlap       after a match, continue after its end
  -h, --help         show this help

exit status: 0 match found, 1 no match, 2 bad arguments or unreadable file
"""


def parse_args(argv):
    opts = {"max": None, "count": False, "offsets": False, "json": False,
            "align": 1, "start": 0, "end": None, "no_overlap": False}
    rest = []
    it = iter(argv)
    for a in it:
        def val(flag):
            try:
                return next(it)
            except StopIteration:
                raise PatternError("%s needs a value" % flag)

        if a in ("-h", "--help"):
            opts["help"] = True
        elif a in ("-n", "--max"):
            opts["max"] = _parse_int_arg(val(a), "--max")
            if opts["max"] < 1:
                raise PatternError("--max must be at least 1")
        elif a in ("-c", "--count"):
            opts["count"] = True
        elif a in ("-o", "--offsets"):
            opts["offsets"] = True
        elif a == "--json":
            opts["json"] = True
        elif a == "--align":
            opts["align"] = _parse_int_arg(val(a), "--align")
            if opts["align"] < 1:
                raise PatternError("--align must be at least 1")
        elif a == "--start":
            opts["start"] = _parse_int_arg(val(a), "--start")
        elif a == "--end":
            opts["end"] = _parse_int_arg(val(a), "--end")
        elif a == "--no-overlap":
            opts["no_overlap"] = True
        elif a.startswith("-") and len(a) > 1 and not a[1:2].isdigit():
            raise PatternError("unknown option %s" % a)
        else:
            rest.append(a)
    return opts, rest


def main(argv, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        opts, rest = parse_args(argv)
        if opts.get("help"):
            stdout.write(USAGE)
            return 0
        if len(rest) < 2:
            raise PatternError("need a pattern and at least one file")
        elements = parse_pattern(rest[0])
        files = rest[1:]
        if opts["end"] is not None and opts["end"] < opts["start"]:
            raise PatternError("--end is before --start")
    except PatternError as e:
        stderr.write("hexfind: %s\n" % e)
        stderr.write("try 'hexfind --help'\n")
        return 2

    total = pattern_length(elements)
    any_match = False
    failed = False
    for path in files:
        try:
            if os.path.isdir(path):
                raise OSError("is a directory")
            data, close = _open_data(path)
        except OSError as e:
            stderr.write("hexfind: %s: %s\n" % (path, e.strerror or e))
            failed = True
            continue
        try:
            count = 0
            next_ok = 0
            for off, fields in find_matches(data, elements, opts["start"], opts["end"], opts["align"]):
                if off < next_ok:
                    continue
                if opts["no_overlap"]:
                    next_ok = off + total
                count += 1
                if not opts["count"]:
                    _print_match(stdout, path, off, data[off:off + total], fields, opts, len(files) > 1)
                if opts["max"] and count >= opts["max"]:
                    break
            if opts["count"]:
                if len(files) > 1:
                    stdout.write("%s: %d\n" % (path, count))
                else:
                    stdout.write("%d\n" % count)
            any_match = any_match or count > 0
        finally:
            close()
    if failed:
        return 2
    return 0 if any_match else 1


def _print_match(out, path, off, raw, fields, opts, multi):
    if opts["json"]:
        rec = {"file": path, "offset": off, "bytes": bytes(raw).hex(),
               "fields": {k: (v.hex() if isinstance(v, (bytes, bytearray)) else v) for k, v in fields}}
        out.write(json.dumps(rec) + "\n")
        return
    prefix = path + ":" if multi else ""
    if opts["offsets"]:
        out.write("%s0x%08x\n" % (prefix, off))
        return
    parts = ["%s0x%08x" % (prefix, off), _show_bytes(bytes(raw))]
    if fields:
        parts.append(" ".join("%s=%s" % (k, _fmt_value(v)) for k, v in fields))
    out.write("  ".join(parts) + "\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
