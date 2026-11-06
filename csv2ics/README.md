# csv2ics

Turns a CSV of events, or a class timetable, into an `.ics` file you can import into Google Calendar, Outlook, Apple Calendar or Thunderbird.

## The problem

People keep timetables, rosters and event lists in spreadsheets and then want them in a calendar. The usual options are bad:

- Google Calendar's CSV import only works in Google, needs exact column names (`Subject`, `Start Date`, `Start Time`...), wants US dates, and has no way to say "every Monday until the end of term".
- Outlook's import wizard is different again and only runs on desktop Outlook.
- So people write one-off scripts. Stack Overflow has questions like "Convert csv to ical using Google Apps Script" and "Have ICS file with multiple events save to my Calendar", and a Hacker News commenter built a whole site just to turn course timetables into a semester calendar.

A semester timetable is the clearest case: 15 classes a week, each repeating weekly until a fixed date. Typing that into a calendar by hand takes an evening.

## What it does

csv2ics reads a CSV with fairly loose column names and writes a standards-compliant iCalendar file (RFC 5545). One file works in every calendar app.

There is a command-line tool and a small web page. Both use the same conversion code, and the page does everything in the browser, so the CSV never leaves your machine.

## Features

- Recognises common header names: `Title`/`Subject`/`Course`/`Event`, `Start Date`/`Date`/`Day`, `Start Time`/`Time`, `End Time`, `Start`/`End` (date and time in one cell), `Location`/`Room`/`Venue`, `Description`/`Notes`, `All Day`, `Repeat`, `Repeat Until`, `Repeat Count`. Case, spaces and underscores do not matter.
- Comma, semicolon and tab separated files, detected automatically. Quoted fields with commas and line breaks work. A UTF-8 BOM from Excel is ignored.
- Dates as `2027-02-01`, `2027/02/01`, `25/12/2027` or `12/25/2027`. When a date like `03/04/2027` could be either, it stops and asks you for `--date-order dmy` or `mdy` instead of guessing.
- Times as `14:00`, `2:00 pm`, `2pm` or `14:00:00`.
- Time zones: pass `--tz Africa/Johannesburg` (any IANA name) and times are converted to UTC, with daylight saving handled. Without `--tz` the times are "floating" and every app shows them as local time.
- All-day events when there is no time, or when the `All Day` column says yes. Multi-day all-day events from a start and end date.
- Events with no end time get a default length (60 minutes, change with `--duration`). An end time earlier than the start time, like a 22:00 to 06:00 shift, is treated as the next day.
- Repeats: `daily`, `weekly`, `monthly`, `yearly`, ending on a `Repeat Until` date or after a `Repeat Count`.
- Every bad row is reported with its line number and the reason. By default nothing is written until all rows are valid; `--skip-invalid` writes the good ones.
- Event UIDs are derived from the row (title, start, location, position), so importing the same file twice into an app that honours UIDs does not create duplicates. Changing an event's time gives it a new UID.
- Text is escaped and long lines are folded at 75 bytes without breaking multi-byte characters, as the spec requires.

## Install

Needs Node.js 18 or newer. There are no dependencies.

```
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/csv2ics
```

Optionally put it on your PATH with `npm link`, then use `csv2ics` instead of `node src/cli.js`.

## Usage

```
node src/cli.js examples/timetable.csv --tz Africa/Johannesburg -o semester.ics
```

```
node src/cli.js events.csv --date-order dmy --duration 30 > events.ics
```

```
cat events.csv | node src/cli.js - --skip-invalid -o events.ics
```

Options:

| Option | Meaning |
|--------|---------|
| `-o, --output FILE` | Write the calendar to a file instead of stdout |
| `--tz ZONE` | IANA time zone the CSV times are in. Default: floating local times |
| `--date-order dmy\|mdy` | How to read ambiguous slash dates |
| `--duration MINUTES` | Length of events without an end time (default 60) |
| `--delimiter CHAR` | Force the separator; `tab` for tabs |
| `--name NAME` | Calendar name (shown by Google and Apple) |
| `--skip-invalid` | Leave out bad rows instead of failing |

Exit codes: `0` success, `1` bad rows or unreadable file, `2` bad command-line usage or option values.

Example input (`examples/timetable.csv`):

```
Course,Day,Start Time,End Time,Room,Repeat,Repeat Until,Notes
Linear Algebra,2027-02-01,08:00,09:30,Room B12,weekly,2027-05-28,Bring the problem set
Mid-term recess,2027-03-29,,,,,,All campus closed
```

Error output looks like this:

```
line 4: invalid date "2027-02-31"
line 7: ambiguous date "03/04/2027"; pass a date order (dmy or mdy)
csv2ics: 2 bad row(s), no calendar written. Fix them or use --skip-invalid.
```

### Web page

The page in `web/` needs to be served over HTTP because it loads the converter as an ES module. From the `csv2ics` folder:

```
python -m http.server 8000
```

Then open http://localhost:8000/web/. Paste or choose a CSV, pick the time zone (pre-filled from your browser), check the preview table and press Download.

## Configuration

None. There are no environment variables, config files or network calls.

## Project structure

```
csv2ics/
  src/csv2ics.js     CSV parsing, column mapping, date/time and time zone handling, iCalendar output
  src/cli.js         command-line interface
  web/index.html     browser page
  web/app.js         page logic, uses src/csv2ics.js
  examples/          sample timetable (comma) and event list (semicolon)
  test/              node:test suites for the converter and the CLI
```

## Tests

```
cd csv2ics
npm test
```

44 tests cover CSV quirks (quotes, BOM, CRLF, delimiters), header mapping, date and time parsing including ambiguous and impossible dates, time zone conversion across DST changes, all-day and multi-day events, repeats, escaping and line folding, stable UIDs, per-row error reporting, empty and header-only files, bad options, and the CLI's exit codes, stdin, file output and a real child-process run.

## Limitations

- The web page was not tested in a browser in this build. Its script passes a syntax check and uses the same tested conversion code, but the page itself, the file picker and the download button have not been exercised.
- The generated files were checked against the RFC by the tests, not by importing them into Google Calendar, Outlook or Apple Calendar.
- With `--tz`, times are written as UTC. That is valid and every app converts them correctly, but the event details in some apps show UTC rather than the original zone name. A future version could emit `TZID` with a `VTIMEZONE` block.
- A time that does not exist because of a daylight saving jump (02:30 on a spring-forward night) is moved forward an hour. A time that happens twice uses the first occurrence.
- Repeats are simple: no "every second week", no specific weekdays, no exceptions for public holidays. Add holidays as separate rows or delete them in your calendar.
- No reminders/alarms, attendees or categories.
- Two-digit years are not accepted.

## Possible improvements

- `TZID` and `VTIMEZONE` output for apps that prefer local times with a zone.
- `Interval` and `Weekdays` columns for fortnightly classes and Mon/Wed/Fri patterns, plus an exceptions column.
- A `Reminder` column that becomes a `VALARM`.
- A column-mapping flag for headers that the aliases do not cover.
