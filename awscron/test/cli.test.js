'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { run } = require('../bin/awscron');

function cli(args, stdin = '') {
  let out = '';
  let err = '';
  const code = run(args, stdin, { write: (s) => (out += s) }, { write: (s) => (err += s) });
  return { code, out, err };
}

test('valid expression exits 0 and lists runs', () => {
  const r = cli(['-n', '2', '--from', '2026-11-01T00:00:00Z', 'cron(0 12 * * ? *)']);
  assert.equal(r.code, 0);
  assert.match(r.out, /OK {3}cron\(0 12 \* \* \? \*\)/);
  assert.match(r.out, /Sun 2026-11-01 12:00 UTC/);
  assert.match(r.out, /Mon 2026-11-02 12:00 UTC/);
});

test('invalid expression exits 1 with a message on stderr', () => {
  const r = cli(['cron(0 12 * * *)']);
  assert.equal(r.code, 1);
  assert.match(r.err, /FAIL/);
  assert.match(r.err, /expected 6 fields/);
});

test('mixed input still checks all and exits 1', () => {
  const r = cli(['rate(5 minutes)', 'bogus', '--quiet']);
  assert.equal(r.code, 1);
  assert.match(r.out, /OK {3}rate\(5 minutes\)/);
  assert.doesNotMatch(r.out, /UTC/);
  assert.match(r.err, /FAIL bogus/);
});

test('no arguments is a usage error', () => {
  const r = cli([]);
  assert.equal(r.code, 2);
  assert.match(r.err, /no expression/);
});

test('bad options are usage errors', () => {
  assert.equal(cli(['-n', '0', 'rate(1 hour)']).code, 2);
  assert.equal(cli(['-n', 'abc', 'rate(1 hour)']).code, 2);
  assert.equal(cli(['-n', '101', 'rate(1 hour)']).code, 2);
  assert.equal(cli(['-n']).code, 2);
  assert.equal(cli(['--from', 'not-a-date', 'rate(1 hour)']).code, 2);
  assert.equal(cli(['--nope', 'rate(1 hour)']).code, 2);
});

test('help exits 0', () => {
  const r = cli(['--help']);
  assert.equal(r.code, 0);
  assert.match(r.out, /usage: awscron/);
});

test('reads expressions from stdin, skipping blanks and comments', () => {
  const r = cli(['-', '--quiet'], '# nightly\r\ncron(0 2 * * ? *)\n\nrate(1 day)\n');
  assert.equal(r.code, 0);
  assert.equal((r.out.match(/^OK/gm) || []).length, 2);
});

test('empty stdin is a usage error', () => {
  assert.equal(cli(['-'], '\n\n').code, 2);
});

test('schedule with no future runs says so', () => {
  const r = cli(['--from', '2026-11-01T00:00:00Z', 'cron(0 0 1 1 ? 2020)']);
  assert.equal(r.code, 0);
  assert.match(r.out, /no run times/);
});
