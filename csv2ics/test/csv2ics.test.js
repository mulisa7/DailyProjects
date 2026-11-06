import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseCsv, detectDelimiter, mapColumns, parseDate, parseTime, zonedToUtc,
  escapeText, foldLine, convert, InputError, ConfigError,
} from '../src/csv2ics.js';

const NOW = new Date(Date.UTC(2026, 10, 6, 12, 0, 0));
const run = (csv, opts = {}) => convert(csv, { now: NOW, ...opts });
const lines = (ics) => ics.split('\r\n');

// ---------- CSV parsing ----------

test('parses quoted fields with commas, quotes and newlines', () => {
  const rows = parseCsv('a,b\n"x, y","say ""hi""\nthere"\n');
  assert.deepEqual(rows, [['a', 'b'], ['x, y', 'say "hi"\nthere']]);
});

test('strips BOM, handles CRLF and drops blank lines', () => {
  const rows = parseCsv('﻿a,b\r\n1,2\r\n\r\n,\r\n3,4');
  assert.deepEqual(rows, [['a', 'b'], ['1', '2'], ['3', '4']]);
});

test('detects semicolon and tab delimiters', () => {
  assert.equal(detectDelimiter('a;b;c\n1;2;3'), ';');
  assert.equal(detectDelimiter('a\tb\n1\t2'), '\t');
  assert.equal(detectDelimiter('"a;b",c'), ',');
});

test('unclosed quote is an error', () => {
  assert.throws(() => parseCsv('a,b\n"oops,1'), InputError);
});

// ---------- columns ----------

test('maps common header names case-insensitively', () => {
  const m = mapColumns(['Subject', 'START_DATE', 'Start Time', 'end time', 'Room']);
  assert.equal(m.title, 0);
  assert.equal(m.startDate, 1);
  assert.equal(m.startTime, 2);
  assert.equal(m.endTime, 3);
  assert.equal(m.location, 4);
});

test('missing title or start column is reported', () => {
  assert.throws(() => mapColumns(['Date', 'Time']), /no title column/);
  assert.throws(() => mapColumns(['Title', 'Room']), /no start column/);
});

// ---------- dates and times ----------

test('parses ISO and slash dates', () => {
  assert.deepEqual(parseDate('2027-02-01'), { y: 2027, m: 2, d: 1 });
  assert.deepEqual(parseDate('2027/2/1'), { y: 2027, m: 2, d: 1 });
  assert.deepEqual(parseDate('25/12/2027'), { y: 2027, m: 12, d: 25 });
  assert.deepEqual(parseDate('12/25/2027'), { y: 2027, m: 12, d: 25 });
  assert.deepEqual(parseDate('03/04/2027', 'dmy'), { y: 2027, m: 4, d: 3 });
  assert.deepEqual(parseDate('03/04/2027', 'mdy'), { y: 2027, m: 3, d: 4 });
});

test('ambiguous and impossible dates are rejected', () => {
  assert.throws(() => parseDate('03/04/2027'), /ambiguous/);
  assert.throws(() => parseDate('2027-02-30'), /invalid date/);
  assert.throws(() => parseDate('2027-13-01'), /invalid date/);
  assert.throws(() => parseDate('next tuesday'), /unrecognised date/);
  assert.deepEqual(parseDate('2028-02-29'), { y: 2028, m: 2, d: 29 });
});

test('parses 24h and am/pm times', () => {
  assert.deepEqual(parseTime('08:05'), { h: 8, mi: 5, s: 0 });
  assert.deepEqual(parseTime('2:30 PM'), { h: 14, mi: 30, s: 0 });
  assert.deepEqual(parseTime('12am'), { h: 0, mi: 0, s: 0 });
  assert.deepEqual(parseTime('12:15pm'), { h: 12, mi: 15, s: 0 });
  assert.deepEqual(parseTime('23:59:30'), { h: 23, mi: 59, s: 30 });
});

test('bad times are rejected', () => {
  for (const t of ['24:00', '9', '13pm', '10:60', 'noon', '0am']) {
    assert.throws(() => parseTime(t), InputError, t);
  }
});

test('converts wall time in a zone to UTC, including DST', () => {
  const d = (y, m, day) => ({ y, m, d: day });
  const t = (h, mi = 0) => ({ h, mi, s: 0 });
  assert.equal(new Date(zonedToUtc(d(2027, 2, 1), t(8), 'Africa/Johannesburg')).toISOString(), '2027-02-01T06:00:00.000Z');
  assert.equal(new Date(zonedToUtc(d(2027, 1, 15), t(9), 'America/New_York')).toISOString(), '2027-01-15T14:00:00.000Z');
  assert.equal(new Date(zonedToUtc(d(2027, 7, 15), t(9), 'America/New_York')).toISOString(), '2027-07-15T13:00:00.000Z');
  // 02:30 does not exist on 2027-03-14 in New York; it moves forward to 03:30 EDT.
  assert.equal(new Date(zonedToUtc(d(2027, 3, 14), t(2, 30), 'America/New_York')).toISOString(), '2027-03-14T07:30:00.000Z');
  // 01:30 happens twice on 2027-11-07; the first (EDT) one is used.
  assert.equal(new Date(zonedToUtc(d(2027, 11, 7), t(1, 30), 'America/New_York')).toISOString(), '2027-11-07T05:30:00.000Z');
});

// ---------- text output ----------

test('escapes iCalendar text', () => {
  assert.equal(escapeText('a,b;c\\d\ne'), 'a\\,b\\;c\\\\d\\ne');
});

test('folds long lines at 75 octets without splitting characters', () => {
  const long = 'SUMMARY:' + 'é'.repeat(80);
  const folded = foldLine(long);
  const enc = new TextEncoder();
  for (const part of folded.split('\r\n')) assert.ok(enc.encode(part).length <= 75, part);
  assert.equal(folded.split('\r\n').map((p, i) => (i ? p.slice(1) : p)).join(''), long);
  assert.equal(foldLine('SHORT:x'), 'SHORT:x');
});

// ---------- full conversion ----------

test('timetable with time zone and weekly repeat', () => {
  const csv = 'Course,Day,Start Time,End Time,Room,Repeat,Repeat Until\n' +
    'Linear Algebra,2027-02-01,08:00,09:30,Room B12,weekly,2027-05-28\n';
  const { ics, events, errors } = run(csv, { timeZone: 'Africa/Johannesburg' });
  assert.equal(errors.length, 0);
  assert.equal(events.length, 1);
  const l = lines(ics);
  assert.equal(l[0], 'BEGIN:VCALENDAR');
  assert.ok(l.includes('DTSTART:20270201T060000Z'));
  assert.ok(l.includes('DTEND:20270201T073000Z'));
  assert.ok(l.includes('RRULE:FREQ=WEEKLY;UNTIL=20270528T215959Z'));
  assert.ok(l.includes('SUMMARY:Linear Algebra'));
  assert.ok(l.includes('LOCATION:Room B12'));
  assert.ok(l.includes('DTSTAMP:20261106T120000Z'));
  assert.ok(ics.endsWith('END:VCALENDAR\r\n'));
});

test('floating times when no time zone is given', () => {
  const { ics } = run('Title,Start\nStandup,2027-01-11 09:00\n');
  assert.ok(lines(ics).includes('DTSTART:20270111T090000'));
  assert.ok(lines(ics).includes('DTEND:20270111T100000'));
  assert.ok(!ics.includes('X-WR-TIMEZONE'));
});

test('default duration applies when there is no end', () => {
  const { ics } = run('Title,Date,Time\nCall,2027-01-11,16:45\n', { defaultDuration: 30 });
  assert.ok(lines(ics).includes('DTEND:20270111T171500'));
});

test('end time earlier than start rolls over to the next day', () => {
  const { ics } = run('Title,Date,Start Time,End Time\nNight shift,2027-01-11,22:00,06:00\n');
  assert.ok(lines(ics).includes('DTEND:20270112T060000'));
});

test('all-day events: no times, explicit flag, and multi-day ranges', () => {
  const csv = 'Subject,Start Date,End Date,Start Time,All Day\n' +
    'Holiday,2027-03-29,,,\n' +
    'Conference,2027-02-03,2027-02-05,,\n' +
    'Offsite,2027-04-01,,09:00,yes\n';
  const l = lines(run(csv).ics);
  assert.ok(l.includes('DTSTART;VALUE=DATE:20270329'));
  assert.ok(l.includes('DTEND;VALUE=DATE:20270330'));
  assert.ok(l.includes('DTEND;VALUE=DATE:20270206'));
  assert.ok(l.includes('DTSTART;VALUE=DATE:20270401'));
});

test('all-day repeat uses a date UNTIL, count works too', () => {
  const csv = 'Title,Date,Repeat,Repeat Until,Repeat Count\n' +
    'Bin day,2027-01-04,weekly,2027-03-01,\n' +
    'Rent,2027-01-01,monthly,,12\n';
  const l = lines(run(csv).ics);
  assert.ok(l.includes('RRULE:FREQ=WEEKLY;UNTIL=20270301'));
  assert.ok(l.includes('RRULE:FREQ=MONTHLY;COUNT=12'));
});

test('special characters in text fields are escaped and long lines folded', () => {
  const desc = 'Bring: pens, paper; and a calculator\nSecond line ' + 'x'.repeat(80);
  const csv = `Title,Date,Notes\n"Exam, part 1",2027-06-01,"${desc}"\n`;
  const { ics } = run(csv);
  assert.ok(ics.includes('SUMMARY:Exam\\, part 1'));
  const unfolded = ics.replace(/\r\n /g, '');
  assert.ok(unfolded.includes('DESCRIPTION:Bring: pens\\, paper\\; and a calculator\\nSecond line x'));
  for (const l of lines(ics)) assert.ok(new TextEncoder().encode(l).length <= 75);
});

test('UIDs are stable across runs and unique per row', () => {
  const csv = 'Title,Date\nA,2027-01-01\nA,2027-01-01\nB,2027-01-02\n';
  const uids = (ics) => lines(ics).filter((l) => l.startsWith('UID:'));
  const first = uids(run(csv).ics);
  assert.equal(new Set(first).size, 3);
  assert.deepEqual(uids(run(csv, { now: new Date() }).ics), first);
});

test('bad rows are collected with line numbers and block output', () => {
  const csv = 'Title,Date,Start Time,End Time\n' +
    'Good,2027-01-01,09:00,10:00\n' +
    ',2027-01-02,09:00,10:00\n' +
    'Bad date,2027-02-31,09:00,10:00\n' +
    'No start,2027-01-03,,10:00\n';
  const { ics, events, errors } = run(csv);
  assert.equal(ics, null);
  assert.equal(events.length, 1);
  assert.deepEqual(errors.map((e) => e.line), [3, 4, 5]);
  assert.match(errors[0].message, /title is empty/);
  assert.match(errors[1].message, /invalid date/);
  assert.match(errors[2].message, /start time is empty/);
});

test('skipInvalid writes the good rows', () => {
  const csv = 'Title,Date\nGood,2027-01-01\nBad,someday\n';
  const { ics, events, errors } = run(csv, { skipInvalid: true });
  assert.equal(events.length, 1);
  assert.equal(errors.length, 1);
  assert.ok(ics.includes('SUMMARY:Good'));
});

test('all rows invalid gives no calendar even with skipInvalid', () => {
  const { ics, errors } = run('Title,Date\nX,nope\n', { skipInvalid: true });
  assert.equal(ics, null);
  assert.equal(errors.length, 1);
});

test('empty and header-only input', () => {
  assert.throws(() => run(''), /empty/);
  assert.throws(() => run('\n\n  \n'), /empty/);
  assert.throws(() => run('Title,Date\n'), /no events/);
});

test('invalid options raise ConfigError', () => {
  const csv = 'Title,Date\nA,2027-01-01\n';
  assert.throws(() => run(csv, { timeZone: 'Mars/Olympus' }), ConfigError);
  assert.throws(() => run(csv, { dateOrder: 'dym' }), ConfigError);
  assert.throws(() => run(csv, { defaultDuration: 0 }), ConfigError);
  assert.throws(() => run(csv, { defaultDuration: 1.5 }), ConfigError);
});

test('unknown repeat, both until and count, and until before start', () => {
  const csv = 'Title,Date,Repeat,Repeat Until,Repeat Count\n' +
    'A,2027-01-01,fortnightly,,\n' +
    'B,2027-01-01,weekly,2027-02-01,4\n' +
    'C,2027-01-10,weekly,2027-01-01,\n' +
    'D,2027-01-01,weekly,,0\n' +
    'E,2027-01-01,none,,\n';
  const { errors, events } = run(csv);
  assert.deepEqual(errors.map((e) => e.line), [2, 3, 4, 5]);
  assert.equal(events.length, 1);
  assert.equal(events[0].rrule, undefined);
});

test('end before start and end date without time are rejected', () => {
  const csv = 'Title,Start,End\n' +
    'A,2027-01-02 10:00,2027-01-01 09:00\n' +
    'B,2027-01-05,2027-01-03\n';
  const { errors } = run(csv);
  assert.match(errors[0].message, /end is not after start/);
  assert.match(errors[1].message, /end date is before start date/);
  const { errors: e2 } = run('Title,Start Date,Start Time,End Date\nC,2027-01-01,09:00,2027-01-02\n');
  assert.match(e2[0].message, /end date given without an end time/);
});

test('rows with fewer cells than the header are handled', () => {
  const { ics, errors } = run('Title,Date,Start Time,Location\nShort,2027-01-01\n');
  assert.equal(errors.length, 0);
  assert.ok(ics.includes('DTSTART;VALUE=DATE:20270101'));
});

test('calendar name is included and escaped', () => {
  const { ics } = run('Title,Date\nA,2027-01-01\n', { calendarName: 'Semester 1, 2027' });
  assert.ok(ics.includes('X-WR-CALNAME:Semester 1\\, 2027'));
});

test('non-string input is rejected', () => {
  assert.throws(() => convert(null), InputError);
});
