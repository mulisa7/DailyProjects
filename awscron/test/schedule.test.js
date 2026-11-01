'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parse } = require('../src/parse');
const { nextRuns, nearestWeekday } = require('../src/schedule');

const iso = (list) => list.map((d) => d.toISOString().slice(0, 16));
const runs = (expr, from, n = 3) => iso(nextRuns(parse(expr), new Date(from), n));

test('daily at noon', () => {
  assert.deepEqual(runs('cron(0 12 * * ? *)', '2026-11-01T13:00:00Z'), [
    '2026-11-02T12:00', '2026-11-03T12:00', '2026-11-04T12:00',
  ]);
});

test('start time is exclusive', () => {
  assert.deepEqual(runs('cron(0 12 * * ? *)', '2026-11-01T12:00:00Z', 1), ['2026-11-02T12:00']);
  assert.deepEqual(runs('cron(0 12 * * ? *)', '2026-11-01T11:59:59Z', 1), ['2026-11-01T12:00']);
});

test('weekdays only skips the weekend', () => {
  assert.deepEqual(runs('cron(0 9 ? * MON-FRI *)', '2026-11-06T10:00:00Z', 3), [
    '2026-11-09T09:00', '2026-11-10T09:00', '2026-11-11T09:00',
  ]);
});

test('day of week 1 is Sunday', () => {
  assert.deepEqual(runs('cron(0 0 ? * 1 *)', '2026-11-01T01:00:00Z', 1), ['2026-11-08T00:00']);
});

test('last day of month handles February and leap years', () => {
  assert.deepEqual(runs('cron(0 0 L * ? *)', '2027-12-31T01:00:00Z', 3), [
    '2028-01-31T00:00', '2028-02-29T00:00', '2028-03-31T00:00',
  ]);
  assert.deepEqual(runs('cron(0 0 L 2 ? *)', '2026-01-01T00:00:00Z', 2), [
    '2026-02-28T00:00', '2027-02-28T00:00',
  ]);
});

test('day 31 skips months without it', () => {
  assert.deepEqual(runs('cron(0 0 31 * ? *)', '2026-01-01T00:00:00Z', 4), [
    '2026-01-31T00:00', '2026-03-31T00:00', '2026-05-31T00:00', '2026-07-31T00:00',
  ]);
});

test('Feb 29 only on leap years', () => {
  assert.deepEqual(runs('cron(0 0 29 2 ? *)', '2026-01-01T00:00:00Z', 2), [
    '2028-02-29T00:00', '2032-02-29T00:00',
  ]);
});

test('nth weekday and last weekday of month', () => {
  assert.deepEqual(runs('cron(0 0 ? * 2#1 *)', '2026-11-01T00:00:00Z', 2), [
    '2026-11-02T00:00', '2026-12-07T00:00',
  ]);
  assert.deepEqual(runs('cron(0 0 ? * 6L *)', '2026-11-01T00:00:00Z', 2), [
    '2026-11-27T00:00', '2026-12-25T00:00',
  ]);
});

test('nearest weekday W', () => {
  assert.equal(nearestWeekday(2026, 11, 15), 16); // Sunday -> Monday
  assert.equal(nearestWeekday(2026, 8, 1), 3); // Saturday the 1st -> Monday the 3rd, not previous month
  assert.equal(nearestWeekday(2026, 5, 31), 29); // Sunday the 31st -> Friday the 29th
  assert.equal(nearestWeekday(2026, 11, 14), 13); // Saturday -> Friday
  assert.equal(nearestWeekday(2026, 2, 30), null); // day does not exist
  assert.deepEqual(runs('cron(0 0 15W * ? *)', '2026-11-01T00:00:00Z', 2), [
    '2026-11-16T00:00', '2026-12-15T00:00',
  ]);
});

test('step and list in minutes and hours', () => {
  assert.deepEqual(runs('cron(0/20 8-9 * * ? *)', '2026-11-01T08:30:00Z', 4), [
    '2026-11-01T08:40', '2026-11-01T09:00', '2026-11-01T09:20', '2026-11-01T09:40',
  ]);
  assert.deepEqual(runs('cron(5,35 * * * ? *)', '2026-11-01T00:10:00Z', 3), [
    '2026-11-01T00:35', '2026-11-01T01:05', '2026-11-01T01:35',
  ]);
});

test('year restriction and exhausted schedules', () => {
  assert.deepEqual(runs('cron(0 0 1 1 ? 2030)', '2026-11-01T00:00:00Z', 5), ['2030-01-01T00:00']);
  assert.deepEqual(runs('cron(0 0 1 1 ? 2020)', '2026-11-01T00:00:00Z', 5), []);
});

test('month names', () => {
  assert.deepEqual(runs('cron(0 0 1 JAN-FEB ? *)', '2026-11-01T00:00:00Z', 3), [
    '2027-01-01T00:00', '2027-02-01T00:00', '2028-01-01T00:00',
  ]);
});

test('rate runs are evenly spaced from the start', () => {
  assert.deepEqual(runs('rate(90 minutes)', '2026-11-01T00:00:00Z', 3), [
    '2026-11-01T01:30', '2026-11-01T03:00', '2026-11-01T04:30',
  ]);
});
