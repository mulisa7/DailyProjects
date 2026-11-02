# rangespec

Turns a plain-English date range into concrete start and end dates.

## The problem

Reports, queries and exports all need a date range, and every tool wants it in a different form. People end up working out "the last full quarter" or "4 weeks ago to 2 weeks from now" by hand, and get the off-by-one at the end of the range wrong. A thread on Hacker News ("What small library or tool do you want that doesn't exist?") asked for exactly this: a parser for simple, relative and "to"-style ranges.

## What it does

`rangespec` takes a phrase, resolves it against a given "today", and prints the first and last day of the range. Both ends are inclusive, and it can also print the exclusive end date, which is what you usually want in a SQL `<` comparison.

```
$ rangespec last 3 months
2026-08-03 to 2026-11-02 (92 days)

$ rangespec "4 weeks ago to 2 weeks from now" --format json
{"input": "4 weeks ago to 2 weeks from now", "start": "2026-10-05", "end": "2026-11-16", "end_exclusive": "2026-11-17", "days": 43}

$ rangespec last quarter --format sql --column created_at
created_at >= '2026-07-01' AND created_at < '2026-10-01'
```

## Supported phrases

| Kind | Examples |
|------|----------|
| Days | `today`, `yesterday`, `tomorrow` |
| Calendar periods | `this week`, `last month`, `next quarter`, `last year` |
| To-date | `ytd`, `mtd`, `qtd`, `year to date` |
| Rolling | `last 7 days`, `past 3 months`, `next 2 weeks` |
| Relative points | `4 weeks ago`, `in 3 days`, `2 weeks from now`, `a month ago` |
| ISO | `2026-04-01`, `2026-04`, `2026` |
| Quarters | `q3 2026`, `2026-q1`, `q2` (this year) |
| Month names | `march 2026`, `sept 2025`, `feb` (this year), `march 5`, `March 5th, 2025` |
| Ranges | `A to B`, `A through B`, `A..B`, `from A to B`, `between A and B`, `since A` |

Rules worth knowing:

- Rolling ranges end today and include it: `last 7 days` is today and the six days before. `last 3 months` starts the day after the date three months ago.
- In a range, each side expands to its whole period. `march 2026 to may 2026` runs from 1 March to 31 May. `2026-04-01 to 2026-05-01` includes both days.
- `last week` and `this week` are calendar weeks starting Monday. Use `--week-start sun` to change that.
- Month arithmetic clamps to the end of the month: one month before 31 March is 28 February.
- Input is case-insensitive and extra spaces are ignored.

## Install

Python 3.8 or later, no third-party packages. Copy `rangespec.py` somewhere on your path, or run it in place:

```
python rangespec.py last month
```

## Usage

```
rangespec [--today YYYY-MM-DD] [--week-start mon|sun]
          [--format text|iso|json|sql|days] [--column NAME] EXPRESSION...
```

- Unquoted words are joined, so `rangespec last month` works. Quote the expression when it contains shell characters.
- `--format iso` prints `start/end`. `--format days` prints every date, one per line (refuses ranges over 100000 days). `--format sql` takes `--column`, which must look like an identifier (letters, digits, underscore, dot).
- Pass `-` as the expression to read one expression per line from stdin. Blank lines are skipped, and a bad line is reported on stderr without stopping the rest.

Exit codes: 0 success, 1 an expression could not be parsed, 2 bad usage or options.

## Configuration

| Setting | Effect |
|---------|--------|
| `--today` or `RANGESPEC_TODAY` | Fix "today" to a date. Useful for repeatable reports and for tests. Defaults to the system date. |

## Project structure

```
rangespec/
  rangespec.py        parser, formatter and CLI
  test_rangespec.py   unittest suite
  README.md
```

`parse_range(expr, today, week_start)` can be imported and used as a library. It returns a `DateRange` with `start`, `end`, `end_exclusive` and `days`, or raises `ParseError`.

## Tests

```
cd rangespec
python -m unittest -v
```

The suite uses a fixed "today" (Monday 2026-11-02) and covers calendar periods, rolling ranges, month-end and leap-day clamping, ranges, both week starts, and the CLI (formats, stdin batches, exit codes). It also covers invalid input: impossible dates, quarter 5, zero counts, reversed ranges, empty input and dates past year 9999.

## Limitations

- Dates only. There are no times of day and no time zones; "today" is the local system date unless you set it.
- English only. No weekday phrases such as `last friday` or `next tuesday`, and no `5 march` day-first form or slash dates like `03/04/2026`, because those are ambiguous.
- `since` is the only open-ended form; there is no "until".
- Fiscal years and quarters that do not start in January are not supported.
- Tested on Windows with Python 3.15 only. It uses nothing platform specific, but I have not run it on Linux or macOS.

## Possible improvements

- Weekday names and "first/last N business days".
- A configurable fiscal year start.
- Time-of-day support with an explicit time zone.
