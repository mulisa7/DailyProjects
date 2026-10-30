# logfold

## The problem
Log files are full of lines that say the same thing but never match exactly, because each one carries a different timestamp, request id, IP address or counter. `sort | uniq -c` only helps after you have written a `sed` expression to strip those parts, and `uniq` alone only collapses adjacent lines. People keep asking how to get a quick "what is this log actually repeating" view.

## The solution
`logfold` replaces the variable parts of each line with placeholders (`<TS>`, `<UUID>`, `<IP>`, `<HEX>`, `<NUM>`), groups lines with the same resulting pattern anywhere in the input, and prints each pattern with a count, most frequent first.

## Features
- Recognises ISO 8601 timestamps, syslog timestamps and Apache/nginx-style timestamps, UUIDs, IPv4 addresses, `0x...` values, long hex strings and numbers.
- Works on files or standard input; several files are combined.
- `-top N`, `-min N` to cut the output down, `-examples` to show the first raw line and the line range for each pattern.
- Standard library only, no dependencies.

## Install and usage
Requires Go 1.21 or newer.

```
cd logfold
go build -o logfold .
./logfold app.log
./logfold -top 10 -examples app.log other.log
journalctl -u myservice | ./logfold -min 5
```

Sample output:

```
      3  <TS> conn from <IP> port <NUM>
         e.g. (lines 1-3) 2026-10-30T07:10:04Z conn from 10.0.0.1 port 5000
      1  disk full on /dev/sda1

4 lines, 2 patterns
```

Exit codes: 0 success, 1 unreadable file or no non-blank lines, 2 bad arguments.

## Configuration
No environment variables or config files. Options: `-top`, `-min`, `-examples`.

## Project structure
- `fold.go` - normalisation rules and grouping
- `main.go` - command line handling and output
- `fold_test.go` - unit and CLI tests

## Tests
```
cd logfold
go test ./...
```
The tests cover each placeholder type, grouping and ordering, blank lines, CRLF endings, a missing trailing newline, a 200 KB line, odd bytes, flag handling, bad flags, empty input, a missing file and multiple files.

## Limitations
- Only IPv4 is recognised. IPv6 addresses and MAC addresses are not replaced and will usually end up with `<NUM>` and `<HEX>` fragments.
- Every number becomes `<NUM>`, so "error 404" and "error 500" are folded together. Sometimes that is not what you want.
- Words that look like long hex (12+ hex characters) are replaced even if they are not ids.
- Lines are held as patterns in memory; a log with millions of genuinely distinct patterns will use a lot of RAM.
- Multi-line entries such as stack traces are treated line by line.
- Only tested on Linux with Go 1.24, and with small invented sample logs, not large real ones.

## Future improvements
- Custom rules from a file, IPv6 and MAC support, JSON output, and a mode that keeps numbers inside a chosen field (such as status codes).
