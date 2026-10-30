# tzquick

## The problem
Scheduling across time zones usually means opening a converter site and clicking through dropdowns, or doing offset arithmetic in your head and getting DST wrong. On Hacker News people asked for a tool that accepts something like "today 17:00 Pacific in UTC" and just answers, using the zone names humans actually say (PDT, Mountain, a city) rather than only IANA identifiers.

## The solution
A single static page with one text box. You type a phrase, it converts it using the browser's built-in `Intl` time zone data. No server calls, no dependencies, nothing leaves the page.

## Features
- Phrase syntax: `[date] time [source zone] in zone, zone, ...` (`to` and `->` also work).
- Times: `17:00`, `1730`, `5pm`, `5:30 pm`, `9h`, `noon`, `midnight`, and `now`.
- Dates: `today`, `tomorrow`, `yesterday`, weekday names (next occurrence, never today), `2026-03-05`, `5 March`, `Mar 5`.
- Zones: cities (London, Johannesburg, New York), abbreviations (PT, ET, SAST, JST), fixed offsets (`UTC+5:30`, `GMT-3`) and IANA names in any case.
- Leaving the source zone out uses your own time zone; leaving the targets out shows your local time and UTC.
- DST aware. A time that does not exist (spring forward) or happens twice (fall back) is flagged with a note instead of silently picking one.
- Ambiguous abbreviations (IST, CST, BST) resolve to one choice and say which.
- The phrase is kept in the URL (`?q=...`) so a conversion can be bookmarked or sent.
- "Copy as text" for pasting into a message.

## Install and usage
Needs Node 20 or newer only for the test runner and the tiny dev server. The page itself needs a browser with ES modules and `Intl.DateTimeFormat` time zone support (any current one).

```
cd tzquick
npm run serve
# open http://127.0.0.1:8080
```

Use `PORT=9000 npm run serve` to change the port. ES modules do not load from `file://`, so open it through the server (or any static host).

Examples:

```
9am New York in London, Tokyo
friday 17:30 Johannesburg in PT, ET, UTC
2026-11-01 01:30 New York in UTC
now in Sydney, Kolkata
```

## Configuration
`PORT` environment variable for `serve.js` (default 8080). Nothing else.

## Project structure
```
src/tz.js        parsing and conversion, no DOM access
app.js           wires the text box to the page
index.html
style.css
serve.js         static file server for local use
test/tz.test.js  node:test suite
```

## Tests
```
cd tzquick
npm test
```
The suite pins "now" to a fixed instant and uses a fixed local zone, so results do not depend on the machine running them. It covers the clock and date formats, DST gap and repeat cases, half-hour and 45-minute zones, fixed offsets, default zones, and the error paths (empty input, unknown zones, impossible dates, too many targets, over-long input).

## Limitations
- English only. No relative phrases such as "in 3 hours" or "next week", and no date ranges.
- A date without a year is assumed to be the current year in the source zone.
- Abbreviations are a fixed list with one reading each. IST means India, CST means US Central, BST means British. If you mean the other one, use a city or IANA name.
- City list is short and hand-picked; anything else needs the IANA name (`Asia/Kathmandu`).
- Results rely on the browser's bundled time zone database, so very old or very future dates follow whatever rules the browser has.
- Tested in the in-app Chromium browser at desktop and 375px width, with the unit tests run on Node 22. Not tested in Safari or Firefox, with a screen reader, or with the clipboard button in a non-secure context.

## Future improvements
- Relative phrases ("in 3 hours", "end of day Friday").
- A small meeting planner view showing working hours across several zones side by side.
- Ask which reading was meant for ambiguous abbreviations instead of picking one.
