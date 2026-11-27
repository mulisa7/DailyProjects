# harscrub

Removes cookies, tokens and passwords from a HAR file so it can be sent to a support team or attached to a bug report.

## The problem

Browser dev tools export network traffic as HAR files, and support teams routinely ask for one. A HAR file contains everything the browser sent, including `Cookie` and `Authorization` headers, session ids in URLs, and passwords in login request bodies. Anyone who gets the file can often replay the session. Sanitising by hand in a text editor is slow and easy to get wrong in a file with thousands of entries.

I could not reach Hacker News or Stack Exchange from the environment this was built in, so I did not collect fresh threads. The motivation is the well-known pattern of session tokens leaking through shared HAR files, and the fact that the common sanitisers are web pages you have to paste the file into, which defeats the purpose.

## The solution

A single Go binary with no dependencies. It reads a HAR file, redacts sensitive values, writes a new file, and prints a count of what it removed by category. It never changes the input file. Nothing leaves your machine.

## Features

- Redacts well-known headers: `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`, `X-CSRF-Token` and a few more.
- Redacts every cookie value in the `cookies` arrays.
- Redacts query string, URL fragment and form values whose names look sensitive (token, secret, password, session, signature, key, code, and similar), including inside the request URL, the `queryString` array and `redirectURL`.
- Redacts the same key names inside JSON request and response bodies, at any depth.
- Replaces JWTs and `Bearer`/`Basic` credentials wherever they appear in text, including HTML and JavaScript responses.
- Removes `user:password@` from URLs.
- `--drop-bodies` deletes response bodies entirely, for when you want to be sure.
- `--header` and `--param` add your own names to redact.
- `--check` reports without writing anything and exits 1 if something sensitive is present, so it can run in a script.

## Install

Needs Go 1.21 or newer.

```
cd harscrub
go build -o harscrub .
```

## Usage

```
harscrub session.har                  # writes session.scrubbed.har
harscrub -o clean.har session.har
harscrub --drop-bodies session.har
harscrub --header X-Tenant --param org_id session.har
harscrub --check session.har          # exit 1 if anything sensitive is found
cat session.har | harscrub -o - -     # stdin to stdout
```

The report goes to stderr, for example:

```
4 value(s) redacted:
  request-body:password: 1
  request-header:cookie: 1
  response-body:access_token: 1
  url-query:session_id: 1
```

Exit codes: 0 success, 1 sensitive data found (only with `--check`), 2 bad usage or unreadable or invalid input.

## Configuration

None. No environment variables or config files. Extra names come from the command line.

## Project structure

```
main.go            argument parsing, file and stream handling, report output
scrub/scrub.go     the redaction rules
scrub/scrub_test.go
main_test.go       command line tests
```

## Tests

```
cd harscrub
go test ./...
```

The tests cover headers, cookies, URL query strings, fragments and userinfo, JSON and form bodies, JWT and Bearer patterns in plain text, custom names, `--drop-bodies`, base64 bodies, clean files, malformed entries, non-HAR input, empty input, a UTF-8 BOM, stdin and stdout, check mode and every usage error.

## Limitations

- This is rule based. It finds secrets by name and by pattern. A secret with an innocent key name (for example `{"data":"s3cr3t"}`) or a custom header you did not list will survive. Read the output, or use `--drop-bodies` and add `--header` names, before sharing.
- Personal data such as email addresses, names and IP addresses is not touched, only credentials.
- Base64-encoded response bodies are left as they are, so a secret inside one is not found.
- Output is re-indented JSON with keys sorted alphabetically. It is still a valid HAR file, but the key order differs from the browser's.
- Large files are loaded fully into memory.
- Tested only on small hand-written HAR samples, not on exports from real browsers.

## Future improvements

- Stream large files.
- Optional redaction of email addresses and IPs.
- Decode and scan base64 bodies.
- A config file for a team's own list of header and key names.
