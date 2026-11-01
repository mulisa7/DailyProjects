# awscron

Checks AWS EventBridge (CloudWatch Events) schedule expressions and prints the next times they will fire, in UTC.

## The problem

AWS cron is not Unix cron. It has six fields instead of five, a year column, day-of-week numbers that start at 1 for Sunday, and a rule that exactly one of day-of-month and day-of-week must be `?`. If you get any of that wrong, the console or the API rejects the rule with a generic message. Crontab.guru does not understand this dialect, so people end up deploying to find out whether an expression is valid. This came up in the Hacker News thread "What small library or tool do you want that doesn't exist?", where someone asked for exactly this for CloudWatch syntax.

## The solution

A small command line tool. Give it one or more `cron(...)` or `rate(...)` expressions. It says whether each is valid, explains what is wrong if not, and lists the next few run times so you can see that `6#3` really means the third Friday.

```
$ awscron -n 3 --from 2026-11-01T00:00:00Z "cron(15 10 ? * 6#3 *)" "cron(0 12 * * * *)"
OK   cron(15 10 ? * 6#3 *)
     Fri 2026-11-20 10:15 UTC
     Fri 2026-12-18 10:15 UTC
     Fri 2027-01-15 10:15 UTC
FAIL cron(0 12 * * * *)
     day-of-month and day-of-week: one of them must be "?" (you cannot set both)
```

## Features

- Six-field cron: minutes, hours, day-of-month, month, day-of-week, year
- `*`, lists, ranges, steps (`0/15`, `*/5`, `1-10/2`), month and weekday names
- `?`, `L`, `nW` (nearest weekday), `nL` (last given weekday of the month), `n#m` (nth weekday)
- `rate(n unit)` with the singular/plural rule AWS enforces
- Next N run times in UTC, correctly skipping months without the day and handling leap years
- Reads expressions from stdin, one per line, ignoring blank lines and `#` comments
- Exit code 0 if everything is valid, 1 if anything is invalid, 2 for bad usage

## Install

Needs Node.js 18 or newer. There are no dependencies.

```
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/awscron
node bin/awscron.js --help
```

Optionally run `npm link` in that folder to get an `awscron` command on your path.

## Usage

```
awscron [-n COUNT] [--from ISO_DATE] [--quiet] EXPRESSION [EXPRESSION...]
awscron [options] -
```

- `-n, --count N` number of run times to show, 1 to 100, default 5
- `--from ISO_DATE` start from this moment instead of now (useful for repeatable output)
- `-q, --quiet` only report valid or invalid, do not list run times
- `-` read expressions from stdin

Quote expressions, since they contain spaces, `*` and parentheses.

Check a list of expressions from a file, for example in CI:

```
node bin/awscron.js - --quiet < schedules.txt
```

## Configuration

None. There are no environment variables or config files.

## Project structure

```
awscron/
  bin/awscron.js      command line entry point and output
  src/parse.js        expression parser and validation rules
  src/schedule.js     next-run calculation
  src/format.js       date formatting
  test/               node:test suites for parser, scheduler and CLI
```

## Running tests

```
npm test
```

This runs 30 tests with the built-in `node:test` runner. They cover valid and invalid expressions, wrong field counts, out-of-range values, malformed lists and ranges, empty and missing input, leap years, months with no day 31, nearest-weekday edge cases, exhausted year ranges, and the CLI exit codes.

## Limitations

- I wrote the rules from the AWS documentation and my own reading of it. I did not compare results against a real AWS account, so a rare expression could be accepted here and rejected by AWS, or the reverse.
- Run times are always UTC. EventBridge cron rules run in UTC; EventBridge Scheduler supports time zones and this tool does not.
- Quartz-only features that AWS does not document (such as `L-3`) are rejected on purpose.
- `rate()` run times count from the `--from` time (or now). AWS counts from when the rule is created, so only the spacing is meaningful.
- The AWS rule that a single expression cannot fire more often than once a minute is satisfied by construction and not separately checked.
- Only the next 20 years are searched. An expression that matches nothing in that window prints a note instead of looping forever.
- Not tested on Linux or macOS. Developed and run on Windows with Node 22.

## Future improvements

- Optional time zone argument for EventBridge Scheduler
- A plain-English description of each expression
- Support for the Unix five-field form, with a suggested AWS equivalent
