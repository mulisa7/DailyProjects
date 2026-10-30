import test from 'node:test';
import assert from 'node:assert/strict';
import { convert, resolveZone, zonedToInstant, ParseError, formatOffset } from '../src/tz.js';

// Fixed "now": Wednesday 2026-03-04 12:00 UTC, before the US spring-forward on 2026-03-08.
const NOW = Date.UTC(2026, 2, 4, 12, 0);
const opts = { now: NOW, localZone: 'Africa/Johannesburg' };
const run = (s, o = opts) => convert(s, o);

test('converts a zone abbreviation to UTC', () => {
  const r = run('17:00 PT in UTC');
  assert.equal(r.results[0].text, '01:00');
  assert.equal(r.results[0].dayDiff, 1);
  assert.equal(r.source.offset, '-08:00');
});

test('uses summer offsets once DST has started', () => {
  const r = run('2026-03-10 17:00 Pacific in UTC');
  assert.equal(r.results[0].text, '00:00');
  assert.equal(r.source.offset, '-07:00');
});

test('12-hour clock forms', () => {
  assert.equal(run('5pm London in UTC').results[0].text, '17:00');
  assert.equal(run('5:30 pm London in UTC').results[0].text, '17:30');
  assert.equal(run('12am London in UTC').results[0].text, '00:00');
  assert.equal(run('12pm London in UTC').results[0].text, '12:00');
  assert.equal(run('noon London in UTC').results[0].text, '12:00');
  assert.equal(run('midnight London in UTC').results[0].text, '00:00');
});

test('compact 24-hour forms', () => {
  assert.equal(run('1730 London in UTC').results[0].text, '17:30');
  assert.equal(run('9h London in UTC').results[0].text, '09:00');
});

test('several targets keep their order', () => {
  const r = run('9am New York in London, Tokyo, Johannesburg');
  assert.deepEqual(r.results.map((x) => x.text), ['14:00', '23:00', '16:00']);
  assert.deepEqual(r.results.map((x) => x.label), ['London', 'Tokyo', 'Johannesburg']);
});

test('"to" and arrow work like "in"', () => {
  assert.equal(run('9am London to Tokyo').results[0].text, '18:00');
  assert.equal(run('9am London -> Tokyo').results[0].text, '18:00');
});

test('tomorrow and yesterday are relative to the source zone', () => {
  // 12:00 UTC on the 4th is 01:00 on the 5th in Auckland (NZDT, +13).
  const r = run('tomorrow 9am Auckland in UTC');
  assert.equal(r.results[0].date, '2026-03-05');
  assert.equal(r.results[0].text, '20:00');
  assert.equal(run('yesterday 9am London in UTC').results[0].date, '2026-03-03');
});

test('weekday names pick the next occurrence, never today', () => {
  assert.equal(run('friday 10:00 London in UTC').results[0].date, '2026-03-06');
  assert.equal(run('wednesday 10:00 London in UTC').results[0].date, '2026-03-11');
  assert.equal(run('next monday 10:00 London in UTC').results[0].date, '2026-03-09');
});

test('month-name dates', () => {
  assert.equal(run('5 March 10:00 London in UTC').results[0].date, '2026-03-05');
  assert.equal(run('Mar 5 10:00 London in UTC').results[0].date, '2026-03-05');
});

test('defaults to local zone when source is omitted', () => {
  const r = run('15:00 in UTC');
  assert.equal(r.results[0].text, '13:00');
  assert.equal(r.source.zone, 'Africa/Johannesburg');
});

test('no target gives local time plus UTC, skipping duplicates', () => {
  const r = run('9am Tokyo');
  assert.deepEqual(r.results.map((x) => x.label), ['your local time', 'UTC']);
  const same = run('9am Johannesburg');
  assert.deepEqual(same.results.map((x) => x.label), ['UTC']);
});

test('"now" converts the current instant', () => {
  const r = run('now in Tokyo');
  assert.equal(r.results[0].text, '21:00');
  assert.equal(r.iso, '2026-03-04T12:00:00.000Z');
});

test('fixed offsets', () => {
  assert.equal(run('10:00 UTC+5:30 in UTC').results[0].text, '04:30');
  assert.equal(run('10:00 GMT-3 in UTC').results[0].text, '13:00');
  assert.equal(run('10:00 UTC in UTC-0330').results[0].text, '06:30');
});

test('IANA names are accepted in any case', () => {
  assert.equal(resolveZone('africa/johannesburg').zone, 'Africa/Johannesburg');
  assert.equal(resolveZone('EUROPE/london').zone, 'Europe/London');
});

test('ambiguous abbreviations produce a note', () => {
  const r = run('9am IST in UTC');
  assert.equal(r.results[0].text, '03:30');
  assert.ok(r.notes.some((n) => n.includes('IST')));
});

test('DST gap: 02:30 on spring-forward day does not exist', () => {
  const r = run('2026-03-08 02:30 New York in UTC');
  assert.ok(r.notes.some((n) => n.includes('does not exist')));
  assert.equal(r.results[0].text, '07:30');
});

test('DST repeat: 01:30 on fall-back day uses the first one and says so', () => {
  const r = run('2026-11-01 01:30 New York in UTC');
  assert.ok(r.notes.some((n) => n.includes('twice')));
  assert.equal(r.results[0].text, '05:30');
});

test('zonedToInstant is exact for an ordinary time', () => {
  const z = zonedToInstant({ year: 2026, month: 7, day: 1, hour: 12, minute: 0 }, 'Europe/London');
  assert.equal(new Date(z.ms).toISOString(), '2026-07-01T11:00:00.000Z');
  assert.equal(z.note, null);
});

test('half-hour and 45-minute zones', () => {
  assert.equal(run('12:00 UTC in Kolkata').results[0].text, '17:30');
  assert.equal(run('12:00 UTC in Asia/Kathmandu').results[0].text, '17:45');
});

test('errors: empty and non-string input', () => {
  assert.throws(() => run(''), ParseError);
  assert.throws(() => run('   '), ParseError);
  assert.throws(() => run(undefined), ParseError);
  assert.throws(() => run(42), ParseError);
});

test('errors: unknown zone names the offender', () => {
  assert.throws(() => run('9am Atlantis in UTC'), /Atlantis/);
  assert.throws(() => run('9am London in Narnia'), /Narnia/);
});

test('errors: invalid times and dates', () => {
  assert.throws(() => run('25:00 London in UTC'), ParseError);
  assert.throws(() => run('13pm London in UTC'), ParseError);
  assert.throws(() => run('10:75 London in UTC'), ParseError);
  assert.throws(() => run('2026-02-30 10:00 London in UTC'), /not a real date/);
  assert.throws(() => run('hello world'), /no time found/);
});

test('errors: structure problems', () => {
  assert.throws(() => run('9am London in Tokyo in Paris'), /one "in"/);
  assert.throws(() => run('9am London in '), ParseError);
  assert.throws(() => run('9am London in ' + 'Paris,'.repeat(13)), /at most 12/);
  assert.throws(() => run('x'.repeat(300)), /too long/);
  assert.throws(() => run('now 2026-03-05 in Tokyo'), /cannot be combined/);
  assert.throws(() => run('10:00 UTC+15 in UTC'), /out of range/);
});

test('formatOffset', () => {
  assert.equal(formatOffset(0), '+00:00');
  assert.equal(formatOffset(-210), '-03:30');
  assert.equal(formatOffset(345), '+05:45');
});
