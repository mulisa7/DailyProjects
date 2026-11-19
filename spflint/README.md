# spflint

Offline linter for SPF and DMARC DNS TXT records.

## The problem

SPF and DMARC records are one long line of text in a DNS panel, and mistakes in them fail quietly. A typo in a mechanism name, a second SPF record added by a new email provider, or an eleventh DNS lookup makes receivers treat the record as broken, and the only symptom is mail landing in spam. Online checkers exist but need the domain to be live in DNS already, so you only find out after publishing.

## The solution

`spflint` reads a record you paste in (or a file of records) and checks it before you publish it. It needs no network access and no dependencies beyond Python 3.8+.

## Features

- SPF syntax check: unknown mechanisms, bad `ip4`/`ip6` values, wrong IP family, bad prefix lengths, malformed `include`/`exists` domains, duplicate `redirect`.
- Warnings for `+all`, `?all`, `~all`, missing `all`, deprecated `ptr`, mechanisms after `all`, `redirect` that is ignored, host bits set in a CIDR.
- DNS lookup counting against the limit of 10 (`include`, `a`, `mx`, `ptr`, `exists`, `redirect`).
- Optional include expansion from a local JSON file, with nested counting and loop detection.
- Length warnings (255 characters per TXT string, 450 bytes for safe UDP responses).
- Detects more than one SPF or DMARC record in a set.
- DMARC checks: version, required `p`, valid `p`/`sp`, `pct`, `adkim`/`aspf`, `ri`, `rua`/`ruf` mailto URIs, duplicate tags; warnings for `p=none`, partial `pct` and a missing `rua`.
- Accepts DNS-style quoted segments (`"v=spf1 a" " -all"`).
- Text or JSON output, and exit codes for scripts.

## Install

No install step. Copy `spflint.py` anywhere, or run it from this folder:

```
python3 spflint.py --help
```

## Usage

```
python3 spflint.py "v=spf1 include:_spf.example.com ip4:192.0.2.0/24 -all"
python3 spflint.py "v=DMARC1; p=quarantine; rua=mailto:reports@example.com"

# several records for one name, one per line (# comments allowed)
python3 spflint.py -f records.txt
cat records.txt | python3 spflint.py -f -

# expand includes from a local file so the lookup count is real
python3 spflint.py --zone zone.json "v=spf1 include:mail.example.com -all"

python3 spflint.py --json --strict "v=spf1 a ~all"
```

`zone.json` maps a domain to its SPF record. Copy the records of your providers into it with `dig +short TXT <domain>`:

```json
{
  "mail.example.com": "v=spf1 include:relay.example.net -all",
  "relay.example.net": "v=spf1 ip4:198.51.100.0/24 -all"
}
```

Exit codes: `0` no errors (warnings allowed), `1` at least one error (or a warning with `--strict`), `2` bad usage or unreadable input.

## Configuration

None. There are no environment variables.

## Project structure

```
spflint/
  spflint.py        the linter and CLI
  test_spflint.py   unit tests (unittest)
  README.md
```

## Running the tests

```
cd spflint
python3 -m unittest -v
```

## Limitations

- It never queries DNS. Includes are only expanded from a zone file you supply; otherwise they count as one lookup each and a warning says the total may be higher.
- `a`, `mx` and `exists` count as one lookup each, but the extra "void lookup" and per-MX address limits from RFC 7208 are not modelled.
- Macros (`%{d}` and similar) are accepted but not evaluated.
- DMARC checks cover the common tags only. Unknown tags are ignored, and `rua` addresses at other domains are not checked for the authorisation record.
- It checks that a record is well formed, not that it matches the servers you actually send from.
- Tested only with the unit tests and a few manual runs on Linux with Python 3.11. Not checked on Windows, and not compared against a real receiving mail server.

## Future improvements

- Optional live resolution of includes.
- DKIM selector record checks.
- Flatten a record into `ip4`/`ip6` lists when it is over the lookup limit.
