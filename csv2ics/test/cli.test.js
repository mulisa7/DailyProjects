import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { main } from '../src/cli.js';

const here = dirname(fileURLToPath(import.meta.url));
const CLI = join(here, '..', 'src', 'cli.js');
const EXAMPLES = join(here, '..', 'examples');

function call(args, stdin) {
  let out = '';
  let err = '';
  const code = main(args, {
    stdout: (s) => (out += s),
    stderr: (s) => (err += s),
    readStdin: () => stdin ?? '',
  });
  return { code, out, err };
}

function withTmp(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'csv2ics-'));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('converts the example timetable to stdout', () => {
  const r = call([join(EXAMPLES, 'timetable.csv'), '--tz', 'Africa/Johannesburg']);
  assert.equal(r.code, 0, r.err);
  assert.equal((r.out.match(/BEGIN:VEVENT/g) || []).length, 4);
  assert.ok(r.out.includes('SUMMARY:Physics Practical\\, group A'));
});

test('converts the semicolon example', () => {
  const r = call([join(EXAMPLES, 'events.csv')]);
  assert.equal(r.code, 0, r.err);
  assert.equal((r.out.match(/BEGIN:VEVENT/g) || []).length, 3);
});

test('writes to an output file', () => {
  withTmp((dir) => {
    const out = join(dir, 'cal.ics');
    const r = call([join(EXAMPLES, 'events.csv'), '-o', out, '--name', 'Work']);
    assert.equal(r.code, 0);
    assert.match(r.err, /wrote 3 event\(s\)/);
    assert.ok(readFileSync(out, 'utf8').includes('X-WR-CALNAME:Work'));
  });
});

test('reads stdin with -', () => {
  const r = call(['-', '--duration', '15'], 'Title,Start\nQuick sync,2027-01-11 09:00\n');
  assert.equal(r.code, 0);
  assert.ok(r.out.includes('DTEND:20270111T091500'));
});

test('bad rows exit 1 and list line numbers', () => {
  const r = call(['-'], 'Title,Date\nOk,2027-01-01\nBad,2027-99-01\n');
  assert.equal(r.code, 1);
  assert.equal(r.out, '');
  assert.match(r.err, /line 3: invalid date/);
  assert.match(r.err, /1 bad row/);
});

test('--skip-invalid writes good rows and warns', () => {
  const r = call(['-', '--skip-invalid'], 'Title,Date\nOk,2027-01-01\nBad,2027-99-01\n');
  assert.equal(r.code, 0);
  assert.match(r.err, /line 3: .*\(skipped\)/);
  assert.ok(r.out.includes('SUMMARY:Ok'));
});

test('empty file exits 1', () => {
  const r = call(['-'], '');
  assert.equal(r.code, 1);
  assert.match(r.err, /empty/);
});

test('missing file exits 1 with a clear message', () => {
  const r = call(['does-not-exist.csv']);
  assert.equal(r.code, 1);
  assert.match(r.err, /file not found/);
});

test('usage errors exit 2', () => {
  assert.equal(call([]).code, 2);
  assert.equal(call(['a.csv', 'b.csv']).code, 2);
  assert.equal(call(['a.csv', '--bogus']).code, 2);
  assert.equal(call(['a.csv', '--tz']).code, 2);
  assert.equal(call(['a.csv', '--duration', 'ten']).code, 2);
  assert.equal(call(['a.csv', '--delimiter', ';;']).code, 2);
});

test('bad option values exit 2', () => {
  const csv = 'Title,Date\nA,2027-01-01\n';
  assert.equal(call(['-', '--tz', 'Nowhere/Special'], csv).code, 2);
  assert.equal(call(['-', '--date-order', 'xyz'], csv).code, 2);
  assert.equal(call(['-', '--duration', '0'], csv).code, 2);
});

test('tab delimiter flag', () => {
  const r = call(['-', '--delimiter', 'tab'], 'Title\tDate\nTabbed, really\t2027-01-01\n');
  assert.equal(r.code, 0);
  assert.ok(r.out.includes('SUMMARY:Tabbed\\, really'));
});

test('--help exits 0', () => {
  const r = call(['--help']);
  assert.equal(r.code, 0);
  assert.match(r.out, /usage: csv2ics/);
});

test('runs as a real process with the right exit code', () => {
  withTmp((dir) => {
    const bad = join(dir, 'bad.csv');
    writeFileSync(bad, 'Date\n2027-01-01\n');
    const r = spawnSync(process.execPath, [CLI, bad], { encoding: 'utf8' });
    assert.equal(r.status, 1);
    assert.match(r.stderr, /no title column/);
    const ok = spawnSync(process.execPath, [CLI, join(EXAMPLES, 'events.csv')], { encoding: 'utf8' });
    assert.equal(ok.status, 0);
    assert.match(ok.stdout, /^BEGIN:VCALENDAR\r\n/);
  });
});
