# cronlint

A linter for crontab files that catches the mistakes which make a job work in your terminal and fail silently under cron.

## Problem

A cron job that runs fine by hand often does nothing under cron. People report losing hours to the same handful of causes: cron's minimal `PATH` (`/usr/bin:/bin`), an unescaped `%` that cron turns into a newline, relative paths, `[[ ]]` run by `/bin/sh`, and output that is mailed to nobody. Cron gives no feedback when it skips a bad line, so the first sign is a backup that never ran.

## Solution

`cronlint` reads a crontab (from a file or stdin) and reports each problem with a line number and a short code. It checks the schedule syntax and the command text, and can optionally look commands up on the local disk to spot ones that exist on your `PATH` but not on cron's.

## Features

- Schedule validation: five fields, ranges, lists, steps, month and day names, `@daily`-style shortcuts, `7` as Sunday, backwards ranges, bad steps.
- Day-of-month plus day-of-week both restricted (cron runs on either, not both).
- Dates that can never happen, such as `0 0 30 2 *`.
- Unescaped `%` in the command.
- Last line without a newline (cron ignores it) and stray carriage returns.
- Relative command paths, bash-only syntax when `SHELL` is not set, `$VAR` in environment lines.
- Jobs with no output redirection and no `MAILTO`.
- Duplicate lines.
- With `-check-exists`: commands only found outside cron's `PATH`, missing or non-executable files.
- `-system` for `/etc/crontab` and `/etc/cron.d` files that have a user column.

## Install

Needs Go 1.21 or newer.

```
cd cronlint
go build -o cronlint .
```

## Usage

```
crontab -l | ./cronlint
./cronlint mycrontab
./cronlint -system /etc/crontab
./cronlint -check-exists -strict mycrontab
```

Output looks like:

```
<stdin>:1: error: [unescaped-percent] unescaped % in command: ...
<stdin>:2: warning: [never-runs] no selected day exists in the selected months; this job never runs
2 error(s), 1 warning(s)
```

Exit codes: 0 no errors, 1 errors found (or warnings with `-strict`), 2 usage or file error.

### Flags

| Flag | Meaning |
| --- | --- |
| `-system` | Lines have a user column after the schedule |
| `-check-exists` | Look commands up on this machine |
| `-strict` | Exit 1 on warnings as well |
| `-cron-path` | PATH to assume when the file sets none (default `/usr/bin:/bin`) |

No environment variables are used, apart from `PATH` for `-check-exists`.

## Project structure

```
cronlint.go       checks (Check function)
main.go           flags, file reading, output, exit codes
cronlint_test.go  tests
```

## Tests

```
cd cronlint
go test -cover ./...
```

The tests cover valid lines, every field error, empty input, comment-only files, missing newline, escaping, system format, the `-check-exists` lookups (using temporary files), and the exit codes.

## Limitations

- Cron implementations differ. It follows Vixie/cronie behaviour; Busybox, fcron and macOS cron may treat some lines differently. It does not know about `L`, `W` or `#` extensions from Quartz-style schedulers.
- Command analysis is text matching, not shell parsing. Only the first word of the command is looked up, and commands after `&&` or `;` are not.
- The output-redirection check is a heuristic and can be fooled by `>` inside quotes.
- `-check-exists` checks the machine it runs on, which may not be the one where cron runs. Per-user `PATH` or `SHELL` defaults set elsewhere are not known.
- Tested on Linux only. Not run against real cron daemons.

## Future improvements

- Check every command in a `&&`/`;`/`|` chain.
- JSON output.
- Show the next few run times for a line.
- Read `/etc/cron.d` recursively.
