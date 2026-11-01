'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parse, CronError } = require('../src/parse');

const bad = (expr, re) =>
  assert.throws(() => parse(expr), (e) => e instanceof CronError && re.test(e.message), expr);

test('accepts common valid cron expressions', () => {
  for (const e of [
    'cron(0 12 * * ? *)',
    'cron(15 10 ? * 6L 2026-2030)',
    'cron(0/15 * ? * MON-FRI *)',
    'cron(0 8 1,15 * ? *)',
    'cron(0 18 ? * MON-FRI *)',
    'cron(0 10 ? * 6#3 *)',
    'cron(0 0 15W * ? *)',
    'cron(0 0 L * ? *)',
    'CRON(0 12 * jan-mar ? *)',
    '  cron(  0   12  * * ? *  )  ',
  ]) assert.doesNotThrow(() => parse(e), e);
});

test('rejects wrong field count', () => {
  bad('cron(0 12 * * ?)', /expected 6 fields.*got 5/);
  bad('cron(0 12 * * ? * *)', /got 7/);
  bad('cron()', /got 0/);
});

test('requires exactly one of day-of-month and day-of-week to be ?', () => {
  bad('cron(0 12 * * * *)', /one of them must be/);
  bad('cron(0 12 ? * ? *)', /cannot both be/);
});

test('rejects out of range values', () => {
  bad('cron(60 12 * * ? *)', /minutes: 60 is out of range/);
  bad('cron(0 24 * * ? *)', /hours/);
  bad('cron(0 12 32 * ? *)', /day-of-month/);
  bad('cron(0 12 * 13 ? *)', /month/);
  bad('cron(0 12 ? * 0 *)', /day-of-week/);
  bad('cron(0 12 ? * 8 *)', /day-of-week/);
  bad('cron(0 12 * * ? 1969)', /year/);
  bad('cron(0 12 * * ? 2200)', /year/);
});

test('rejects malformed pieces', () => {
  bad('cron(0 12 * * ? ,)', /empty list item/);
  bad('cron(5-1 12 * * ? *)', /backwards/);
  bad('cron(0/0 12 * * ? *)', /step/);
  bad('cron(0/x 12 * * ? *)', /step/);
  bad('cron(0 12 * FOO ? *)', /not a valid value/);
  bad('cron(a 12 * * ? *)', /not a valid value/);
  bad('cron(1-2-3 12 * * ? *)', /not a valid range/);
  bad('cron(0 12 ? * 2#9 *)', /1-5/);
  bad('cron(0 12 ? * 2#1#1 *)', /nth-weekday/);
  bad('cron(? 12 * * ? *)', /only allowed in day-of-month/);
  bad('cron(0 12 L-2 * ? *)', /not supported/);
});

test('rejects bad wrappers and empty input', () => {
  bad('', /empty/);
  bad('   ', /empty/);
  bad('0 12 * * ? *', /cron\(\.\.\.\) or rate/);
  bad('cron 0 12 * * ? *', /cron\(\.\.\.\) or rate/);
  bad('cron(0 12 * * ? *', /cron\(\.\.\.\) or rate/);
  assert.throws(() => parse(undefined), CronError);
  assert.throws(() => parse(null), CronError);
});

test('rate expressions', () => {
  assert.equal(parse('rate(5 minutes)').intervalMs, 300000);
  assert.equal(parse('rate(1 hour)').intervalMs, 3600000);
  assert.equal(parse('RATE(2 days)').intervalMs, 172800000);
  bad('rate(1 minutes)', /singular/);
  bad('rate(5 minute)', /plural/);
  bad('rate(0 minutes)', /positive/);
  bad('rate(-5 minutes)', /positive/);
  bad('rate(1.5 hours)', /positive/);
  bad('rate(5 weeks)', /minute\(s\)/);
  bad('rate(5)', /value and a unit/);
  bad('rate()', /value and a unit/);
});

test('names are case-insensitive and map to numbers', () => {
  assert.ok(parse('cron(0 12 ? * sun *)').fields[4].values.has(1));
  assert.ok(parse('cron(0 12 * Dec ? *)').fields[3].values.has(12));
});
