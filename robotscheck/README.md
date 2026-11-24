# robotscheck

Check whether a URL is blocked by a robots.txt file, and see which rule decided it.

## Problem

Site owners editing robots.txt want to know whether `/downloads/report.pdf` is still crawlable before they deploy, and people writing crawlers want to honour the file correctly. The usual quick answers are online testers (paste your file into a web page) or Python's `urllib.robotparser`, which has historically applied the first matching rule rather than the most specific one and has had gaps with `*` and `$`. Rule precedence is where mistakes happen: `Allow: /a/b/` should beat `Disallow: /a/` no matter which line comes first.

## Solution

A small offline Rust CLI with no dependencies. It parses a robots.txt file and answers allowed or blocked for each URL or path you give it, following RFC 9309: longest matching pattern wins, Allow wins ties, `*` matches any run of characters and a trailing `$` anchors the end.

## Features

- Longest-match precedence independent of rule order
- `*` and `$` wildcards
- Picks the group with the longest user-agent token that prefixes the agent, falling back to `*`; groups that name the same agent are merged; stacked `User-agent` lines share rules
- `--explain` prints the deciding rule and its line number
- Accepts full URLs or paths; query strings are part of the match, fragments are dropped
- `/robots.txt` is always reported as allowed
- Handles BOM, CRLF, comments, unknown directives, invalid UTF-8
- Exit codes for scripts: 0 all allowed, 1 something blocked, 2 error

## Install

Requires a Rust toolchain.

```
cd robotscheck
cargo build --release
# binary: target/release/robotscheck
```

## Usage

```
robotscheck --file ROBOTS.TXT|- [--agent NAME] [--explain] [--quiet] URL_OR_PATH...
```

```
$ cat robots.txt
User-agent: *
Disallow: /private/
Allow: /private/press/

$ robotscheck -f robots.txt -e /private/a.html /private/press/kit.zip /about
BLOCKED  /private/a.html  <- Disallow /private/ (line 2, group '*')
ALLOWED  /private/press/kit.zip  <- Allow /private/press/ (line 3, group '*')
ALLOWED  /about  (no rule in group '*' matches)

$ curl -s https://example.com/robots.txt | robotscheck -f - -a Googlebot https://example.com/search?q=x
```

Fetching the file is left to you (curl, a browser); the tool never touches the network.

## Configuration

No environment variables or config files. Options: `--file/-f`, `--agent/-a` (default `*`), `--explain/-e`, `--quiet/-q`, `--help/-h`.

## Project structure

```
src/lib.rs     parser, wildcard matcher, group selection, decision logic (with unit tests)
src/main.rs    argument handling and output
tests/cli.rs   end-to-end tests of the binary
```

## Tests

```
cargo test
```

Covers rule order, ties, wildcards and backtracking, `$`, agent selection, merged and stacked groups, comments/BOM/CRLF, empty files, percent-escape case, bad URLs, missing files, bad options and garbage input.

## Limitations

- Agent matching is prefix-based on the agent string you pass; it does not split full browser-style user-agent strings into product tokens.
- Percent-escapes are only case-normalised, not decoded, so `/a%7Eb` and `/a~b` are treated as different paths. Non-ASCII paths are not percent-encoded for you.
- Only the path and query are checked; host, scheme and port are ignored, so a file for one host can be tested against URLs of another.
- Crawl-delay, Sitemap and other directives are ignored.
- Behaviour was checked against my reading of RFC 9309, not compared against Google's or another crawler's implementation. Search engines differ in edge cases (for example how they treat a trailing `*`).
- No size cap is applied to the file (RFC 9309 says crawlers should parse at least 500 KiB).

## Future improvements

- Read many URLs from a file
- Decode unreserved percent-escapes before matching
- Fetch the file over HTTP with redirect handling
- Warn about likely mistakes (rule with no leading `/`, unreachable Allow rules)
