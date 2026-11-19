#!/usr/bin/env python3
"""spflint: offline linter for SPF and DMARC DNS TXT records."""
import argparse
import ipaddress
import json
import re
import sys

LOOKUP_LIMIT = 10
SEGMENT_LIMIT = 255
UDP_SAFE_LIMIT = 450

QUALIFIERS = "+-~?"
LOOKUP_MECHS = {"include", "a", "mx", "ptr", "exists"}
ALL_MECHS = {"all", "include", "a", "mx", "ptr", "exists", "ip4", "ip6"}
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.)*"
    r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)


class Finding:
    def __init__(self, level, message):
        self.level = level  # "error" or "warning"
        self.message = message

    def as_dict(self):
        return {"level": self.level, "message": self.message}


def _valid_domain(value):
    # macros such as %{d} are legal in SPF domain-specs; accept them as-is
    if "%{" in value:
        return True
    return bool(DOMAIN_RE.match(value))


def _check_dual_cidr(arg, findings, mech):
    """Validate the optional /len or //len suffix of a / mx."""
    m = re.match(r"^(?:/(\d+))?(?://(\d+))?$", arg)
    if not m:
        findings.append(Finding("error", f"'{mech}' has a malformed prefix length '{arg}'"))
        return
    v4, v6 = m.group(1), m.group(2)
    if v4 is not None and not 0 <= int(v4) <= 32:
        findings.append(Finding("error", f"'{mech}' IPv4 prefix length {v4} is outside 0-32"))
    if v6 is not None and not 0 <= int(v6) <= 128:
        findings.append(Finding("error", f"'{mech}' IPv6 prefix length {v6} is outside 0-128"))


def parse_spf(record):
    """Return (terms, findings). Each term is a dict with kind/qualifier/name/value."""
    findings = []
    terms = []
    tokens = record.split()
    if not tokens or tokens[0].lower() != "v=spf1":
        findings.append(Finding("error", "record must start with 'v=spf1'"))
        return terms, findings
    seen_modifiers = set()
    for tok in tokens[1:]:
        qualifier = "+"
        body = tok
        if body and body[0] in QUALIFIERS:
            qualifier, body = body[0], body[1:]
        if not body:
            findings.append(Finding("error", f"'{tok}' is a qualifier with no mechanism"))
            continue
        # modifier: name=value (a mechanism never contains '=' before ':' or '/')
        mod = re.match(r"^([A-Za-z][A-Za-z0-9_.-]*)=(.*)$", body)
        if mod and tok[0] not in QUALIFIERS:
            name, value = mod.group(1).lower(), mod.group(2)
            if name in ("redirect", "exp"):
                if name in seen_modifiers:
                    findings.append(Finding("error", f"modifier '{name}' appears more than once"))
                seen_modifiers.add(name)
                if not value or not _valid_domain(value):
                    findings.append(Finding("error", f"'{name}=' needs a valid domain, got '{value}'"))
            terms.append({"kind": "modifier", "name": name, "value": value, "token": tok})
            continue
        if mod and tok[0] in QUALIFIERS:
            findings.append(Finding("error", f"modifier '{body}' cannot have a qualifier"))
            continue
        name, sep, arg = re.split(r"([:/])", body, maxsplit=1) if re.search(r"[:/]", body) else (body, "", "")
        if sep == "/":
            arg = "/" + arg
        name = name.lower()
        if name not in ALL_MECHS:
            findings.append(Finding("error", f"unknown mechanism '{tok}'"))
            continue
        terms.append({"kind": "mechanism", "name": name, "qualifier": qualifier,
                      "value": arg, "token": tok})
        if name == "all" and arg:
            findings.append(Finding("error", f"'all' takes no argument: '{tok}'"))
        elif name == "include":
            if sep != ":" or not arg or not _valid_domain(arg):
                findings.append(Finding("error", f"'include' needs a valid domain: '{tok}'"))
        elif name == "exists":
            if sep != ":" or not arg or not _valid_domain(arg):
                findings.append(Finding("error", f"'exists' needs a valid domain: '{tok}'"))
        elif name in ("a", "mx"):
            if sep == ":":
                domain, _, cidr = arg.partition("/")
                if not domain or not _valid_domain(domain):
                    findings.append(Finding("error", f"'{name}' has an invalid domain: '{tok}'"))
                _check_dual_cidr(("/" + cidr) if cidr else "", findings, name)
            else:
                _check_dual_cidr(arg, findings, name)
        elif name == "ptr":
            findings.append(Finding("warning", "'ptr' is deprecated (RFC 7208) and slow; replace it with ip4/ip6 or include"))
            if sep == ":" and not _valid_domain(arg):
                findings.append(Finding("error", f"'ptr' has an invalid domain: '{tok}'"))
        elif name in ("ip4", "ip6"):
            if sep != ":" or not arg:
                findings.append(Finding("error", f"'{name}' needs an address: '{tok}'"))
            else:
                try:
                    net = ipaddress.ip_network(arg, strict=False)
                    wanted = 4 if name == "ip4" else 6
                    if net.version != wanted:
                        findings.append(Finding("error", f"'{tok}' holds an IPv{net.version} address but uses {name}"))
                    elif "/" in arg:
                        # a host bit set under the prefix is almost always a typo
                        try:
                            ipaddress.ip_network(arg, strict=True)
                        except ValueError:
                            findings.append(Finding("warning", f"'{tok}' has host bits set; it covers {net}"))
                    if name == "ip4" and net.version == 4 and net.prefixlen == 0:
                        findings.append(Finding("warning", f"'{tok}' authorises every IPv4 address"))
                except ValueError:
                    findings.append(Finding("error", f"'{tok}' is not a valid address or network"))
    return terms, findings


def _all_term(terms):
    for i, t in enumerate(terms):
        if t["kind"] == "mechanism" and t["name"] == "all":
            return i, t
    return None, None


def lint_spf(record, zone=None, _domain="(this record)", _chain=None, _top=True):
    """Lint one SPF record. Returns (findings, lookup_count)."""
    terms, findings = parse_spf(record)
    if not terms and any(f.level == "error" for f in findings):
        return findings, 0

    if _top:
        if len(record.encode("utf-8")) > UDP_SAFE_LIMIT:
            findings.append(Finding("warning", f"record is {len(record.encode('utf-8'))} bytes; over {UDP_SAFE_LIMIT} risks truncated DNS responses"))
        if len(record) > SEGMENT_LIMIT:
            findings.append(Finding("warning", f"record is {len(record)} characters; a single TXT string holds {SEGMENT_LIMIT}, so it must be split into several quoted strings"))

    idx, all_term = _all_term(terms)
    redirects = [t for t in terms if t["kind"] == "modifier" and t["name"] == "redirect"]
    if all_term is not None:
        if idx != max(
            i for i, t in enumerate(terms) if t["kind"] == "mechanism"
        ):
            findings.append(Finding("warning", "mechanisms after 'all' are never evaluated"))
        if redirects:
            findings.append(Finding("warning", "'redirect' is ignored because the record has an 'all' mechanism"))
        q = all_term["qualifier"]
        if q == "+":
            findings.append(Finding("error", "'+all' (or bare 'all') lets any server send as this domain"))
        elif q == "?":
            findings.append(Finding("warning", "'?all' is neutral, so the record gives no protection"))
        elif q == "~":
            findings.append(Finding("warning", "'~all' is a soft fail; consider '-all' once all senders are listed"))
    elif not redirects:
        findings.append(Finding("warning", "no 'all' mechanism or 'redirect'; unlisted senders get a neutral result"))

    lookups = sum(1 for t in terms if (t["kind"] == "mechanism" and t["name"] in LOOKUP_MECHS)
                  or (t["kind"] == "modifier" and t["name"] == "redirect"))

    chain = (_chain or []) + [_domain]
    if zone is not None:
        for t in terms:
            target = None
            if t["kind"] == "mechanism" and t["name"] == "include":
                target = t["value"].lower().rstrip(".")
            elif t["kind"] == "modifier" and t["name"] == "redirect" and all_term is None:
                target = t["value"].lower().rstrip(".")
            if not target or "%{" in target:
                continue
            if target in chain:
                findings.append(Finding("error", f"include loop: {' -> '.join(chain + [target])}"))
                continue
            nested = zone.get(target)
            if nested is None:
                findings.append(Finding("warning", f"'{target}' is not in the zone file, so its lookups are not counted"))
                continue
            sub_findings, sub_count = lint_spf(nested, zone, target, chain, _top=False)
            lookups += sub_count
            for f in sub_findings:
                if f.level == "error":
                    findings.append(Finding("error", f"in '{target}': {f.message}"))
    elif _top and any(t["kind"] == "mechanism" and t["name"] == "include" for t in terms):
        findings.append(Finding("warning", "includes were not expanded; the real lookup total may be higher (use --zone)"))

    if _top and lookups > LOOKUP_LIMIT:
        findings.append(Finding("error", f"{lookups} DNS lookups; the limit is {LOOKUP_LIMIT} and receivers return permerror above it"))
    elif _top and lookups == LOOKUP_LIMIT:
        findings.append(Finding("warning", f"{lookups} DNS lookups is exactly at the limit of {LOOKUP_LIMIT}"))
    return findings, lookups


def lint_dmarc(record):
    findings = []
    parts = [p.strip() for p in record.split(";")]
    parts = [p for p in parts if p]
    if not parts or not re.match(r"^v\s*=\s*DMARC1$", parts[0], re.I):
        findings.append(Finding("error", "record must start with 'v=DMARC1'"))
        return findings
    tags = {}
    for p in parts[1:]:
        if "=" not in p:
            findings.append(Finding("error", f"tag '{p}' has no '='"))
            continue
        k, v = (s.strip() for s in p.split("=", 1))
        k = k.lower()
        if k in tags:
            findings.append(Finding("error", f"tag '{k}' appears more than once"))
        tags[k] = v
    if "p" not in tags:
        findings.append(Finding("error", "required tag 'p' is missing"))
    else:
        for name in ("p", "sp"):
            if name in tags and tags[name].lower() not in ("none", "quarantine", "reject"):
                findings.append(Finding("error", f"'{name}' must be none, quarantine or reject, got '{tags[name]}'"))
        if tags["p"].lower() == "none":
            findings.append(Finding("warning", "p=none only monitors; spoofed mail is still delivered"))
    if "pct" in tags:
        if not tags["pct"].isdigit() or not 0 <= int(tags["pct"]) <= 100:
            findings.append(Finding("error", f"'pct' must be a whole number from 0 to 100, got '{tags['pct']}'"))
        elif int(tags["pct"]) < 100:
            findings.append(Finding("warning", f"pct={tags['pct']} applies the policy to only part of the mail"))
    for name in ("adkim", "aspf"):
        if name in tags and tags[name].lower() not in ("r", "s"):
            findings.append(Finding("error", f"'{name}' must be r or s, got '{tags[name]}'"))
    if "ri" in tags and not (tags["ri"].isdigit() and int(tags["ri"]) > 0):
        findings.append(Finding("error", f"'ri' must be a positive number of seconds, got '{tags['ri']}'"))
    for name in ("rua", "ruf"):
        if name in tags:
            for uri in (u.strip() for u in tags[name].split(",")):
                if not re.match(r"^mailto:[^@\s,!]+@[^@\s,!]+\.[^@\s,!]+(![0-9]+[kmgt]?)?$", uri, re.I):
                    findings.append(Finding("error", f"'{name}' entry '{uri}' is not a valid mailto: URI"))
    if "rua" not in tags and "p" in tags:
        findings.append(Finding("warning", "no 'rua' address, so you will not receive aggregate reports"))
    return findings


def strip_txt_quotes(text):
    """Join DNS-style quoted segments: "v=spf1 a" " -all" -> v=spf1 a -all."""
    text = text.strip()
    if text.startswith('"') and '"' in text[1:]:
        segs = re.findall(r'"([^"]*)"', text)
        return "".join(segs)
    return text


def load_records(text):
    """One record per non-empty, non-comment line."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(strip_txt_quotes(line))
    return out


def load_zone(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as e:
        raise ValueError(f"cannot read zone file: {e.strerror}")
    except json.JSONDecodeError as e:
        raise ValueError(f"zone file is not valid JSON: {e}")
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("zone file must be a JSON object mapping domain -> SPF string")
    return {k.lower().rstrip("."): strip_txt_quotes(v) for k, v in data.items()}


def lint_records(records, zone=None):
    """Lint a set of TXT values belonging to one name. Returns list of result dicts."""
    results = []
    spf = [r for r in records if r.lower().startswith("v=spf1")]
    dmarc = [r for r in records if re.match(r"^v\s*=\s*DMARC1", r, re.I)]
    other = [r for r in records if r not in spf and r not in dmarc]
    if len(spf) > 1:
        results.append({"record": "(set)", "kind": "spf", "lookups": None,
                        "findings": [Finding("error", f"{len(spf)} SPF records found; only one is allowed (permerror)")]})
    if len(dmarc) > 1:
        results.append({"record": "(set)", "kind": "dmarc", "lookups": None,
                        "findings": [Finding("error", f"{len(dmarc)} DMARC records found; only one is allowed")]})
    for r in spf:
        f, n = lint_spf(r, zone)
        results.append({"record": r, "kind": "spf", "lookups": n, "findings": f})
    for r in dmarc:
        results.append({"record": r, "kind": "dmarc", "lookups": None, "findings": lint_dmarc(r)})
    for r in other:
        results.append({"record": r, "kind": "unknown", "lookups": None,
                        "findings": [Finding("error", "not an SPF or DMARC record (expected it to start with v=spf1 or v=DMARC1)")]})
    return results


def render_text(results):
    lines = []
    for res in results:
        shown = res["record"] if len(res["record"]) <= 70 else res["record"][:67] + "..."
        head = f"[{res['kind'].upper()}] {shown}"
        if res["lookups"] is not None:
            head += f"  ({res['lookups']} lookups)"
        lines.append(head)
        if not res["findings"]:
            lines.append("  ok")
        for f in res["findings"]:
            lines.append(f"  {f.level.upper():7} {f.message}")
    return "\n".join(lines)


def build_parser():
    p = argparse.ArgumentParser(prog="spflint", description="Lint SPF and DMARC TXT records offline.")
    p.add_argument("record", nargs="?", help="one record, e.g. 'v=spf1 include:_spf.example.com -all'")
    p.add_argument("-f", "--file", help="file with one record per line ('-' for stdin); all lines are treated as one DNS name")
    p.add_argument("--zone", help="JSON file mapping domain -> SPF record, used to expand include/redirect")
    p.add_argument("--json", action="store_true", help="print results as JSON")
    p.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    return p


def main(argv=None, stdin=None, stdout=None, stderr=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if bool(args.record) == bool(args.file):
        print("spflint: give either a record or --file, not both and not neither", file=stderr)
        return 2
    try:
        if args.file:
            if args.file == "-":
                text = stdin.read()
            else:
                with open(args.file, encoding="utf-8") as fh:
                    text = fh.read()
            records = load_records(text)
        else:
            records = [strip_txt_quotes(args.record)]
        zone = load_zone(args.zone) if args.zone else None
    except OSError as e:
        print(f"spflint: cannot read {args.file}: {e.strerror}", file=stderr)
        return 2
    except UnicodeDecodeError:
        print(f"spflint: {args.file} is not UTF-8 text", file=stderr)
        return 2
    except ValueError as e:
        print(f"spflint: {e}", file=stderr)
        return 2
    if not records:
        print("spflint: no records to check (input was empty)", file=stderr)
        return 2
    results = lint_records(records, zone)
    if args.json:
        payload = [{"record": r["record"], "kind": r["kind"], "lookups": r["lookups"],
                    "findings": [f.as_dict() for f in r["findings"]]} for r in results]
        print(json.dumps(payload, indent=2), file=stdout)
    else:
        print(render_text(results), file=stdout)
    levels = {f.level for r in results for f in r["findings"]}
    if "error" in levels or (args.strict and "warning" in levels):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
