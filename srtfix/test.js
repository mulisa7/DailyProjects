'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const srt = require('./srt');
const { run, parseOffset } = require('./cli');

const SAMPLE = '1\n00:00:01,000 --> 00:00:03,000\nHello\n\n2\n00:00:05,500 --> 00:00:07,000\nWorld\nline two\n';

function tmp(content) {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'srtfix-'));
  const f = path.join(d, 'a.srt');
  if (content !== undefined) fs.writeFileSync(f, content);
  return f;
}
function cli(args) {
  const o = [], e = [];
  const code = run(args, { out: (s) => o.push(s), err: (s) => e.push(s) });
  return { code, out: o.join('\n'), err: e.join('\n') };
}

test('time parse/format round trip', () => {
  assert.strictEqual(srt.parseTime('01:02:03,456'), 3723456);
  assert.strictEqual(srt.parseTime('00:00:01.5'), 1500);
  assert.strictEqual(srt.formatTime(3723456), '01:02:03,456');
  assert.strictEqual(srt.formatTime(-5), '00:00:00,000');
});

test('bad timestamps throw', () => {
  for (const s of ['abc', '00:61:00,000', '00:00:75,000', '', '1:2']) assert.throws(() => srt.parseTime(s), /bad timestamp/);
});

test('parse handles CRLF, BOM and multi-line text', () => {
  const { cues, warnings } = srt.parse('﻿' + SAMPLE.replace(/\n/g, '\r\n'));
  assert.strictEqual(cues.length, 2);
  assert.strictEqual(cues[1].text, 'World\nline two');
  assert.deepStrictEqual(warnings, []);
});

test('parse: empty input gives no cues; garbage blocks are skipped with warnings', () => {
  assert.deepStrictEqual(srt.parse('').cues, []);
  assert.deepStrictEqual(srt.parse('  \n\n ').cues, []);
  const r = srt.parse('hello there\n\n' + SAMPLE + '\n\n3\n00:00:xx,000 --> 00:00:09,000\nbad');
  assert.strictEqual(r.cues.length, 2);
  assert.strictEqual(r.warnings.length, 2);
});

test('parse works without index lines', () => {
  const r = srt.parse('00:00:01,000 --> 00:00:02,000\nhi');
  assert.strictEqual(r.cues.length, 1);
});

test('shift forward and back, clamp and drop', () => {
  const { cues } = srt.parse(SAMPLE);
  assert.strictEqual(srt.shift(cues, 2000)[0].start, 3000);
  const back = srt.shift(cues, -2000);
  assert.strictEqual(back.length, 2);
  assert.strictEqual(back[0].start, 0);
  assert.strictEqual(back[0].end, 1000);
  assert.strictEqual(srt.shift(cues, -3000).length, 1);
  assert.throws(() => srt.shift(cues, NaN), /number/);
});

test('stretch scales times; rejects bad factor', () => {
  const { cues } = srt.parse(SAMPLE);
  assert.strictEqual(srt.stretch(cues, 2)[0].end, 6000);
  assert.throws(() => srt.stretch(cues, 0), /positive/);
  assert.throws(() => srt.stretch(cues, -1), /positive/);
});

test('sync maps two reference points linearly', () => {
  const { cues } = srt.parse(SAMPLE);
  // 1000 -> 2000 and 5500 -> 10000: factor 2, offset 0
  const r = srt.sync(cues, 1000, 2000, 5500, 11000);
  assert.strictEqual(r[0].start, 2000);
  assert.strictEqual(r[1].start, 11000);
  assert.throws(() => srt.sync(cues, 5, 5, 5, 9), /differ/);
  assert.throws(() => srt.sync(cues, 1000, 9000, 2000, 1000), /non-positive/);
});

test('validate finds overlap, bad order, empty text, zero length', () => {
  const cues = [
    { start: 0, end: 2000, text: 'a' },
    { start: 1500, end: 3000, text: 'b' },
    { start: 1000, end: 1000, text: '  ' },
  ];
  const p = srt.validate(cues);
  assert.ok(p.some((x) => /overlaps cue 1 by 500/.test(x)));
  assert.ok(p.some((x) => /starts before cue 2/.test(x)));
  assert.ok(p.some((x) => /empty text/.test(x)));
  assert.ok(p.some((x) => /end is not after start/.test(x)));
  assert.deepStrictEqual(srt.validate(srt.parse(SAMPLE).cues), []);
});

test('sortCues is stable and format renumbers', () => {
  const cues = [
    { start: 5000, end: 6000, text: 'late' },
    { start: 1000, end: 2000, text: 'early' },
  ];
  const out = srt.format(srt.sortCues(cues));
  assert.ok(out.startsWith('1\n00:00:01,000'));
  assert.strictEqual(srt.format([]), '');
});

test('parseOffset', () => {
  assert.strictEqual(parseOffset('2.5s'), 2500);
  assert.strictEqual(parseOffset('-800ms'), -800);
  assert.strictEqual(parseOffset('1500'), 1500);
  assert.throws(() => parseOffset('soon'), /bad offset/);
});

test('cli shift to stdout', () => {
  const r = cli(['shift', tmp(SAMPLE), '1s']);
  assert.strictEqual(r.code, 0);
  assert.match(r.out, /00:00:02,000 --> 00:00:04,000/);
});

test('cli stretch 23.976 -> 25 shortens times', () => {
  const r = cli(['stretch', tmp(SAMPLE), '23.976', '25']);
  assert.strictEqual(r.code, 0);
  assert.match(r.out, /00:00:00,959 --> 00:00:02,877/);
});

test('cli -o writes a file', () => {
  const f = tmp(SAMPLE);
  const o = f + '.out';
  const r = cli(['sort', f, '-o', o]);
  assert.strictEqual(r.code, 0);
  assert.match(fs.readFileSync(o, 'utf8'), /Hello/);
});

test('cli check returns 1 on problems, 0 when clean', () => {
  assert.strictEqual(cli(['check', tmp(SAMPLE)]).code, 0);
  const bad = '1\n00:00:01,000 --> 00:00:05,000\na\n\n2\n00:00:03,000 --> 00:00:06,000\nb';
  const r = cli(['check', tmp(bad)]);
  assert.strictEqual(r.code, 1);
  assert.match(r.out, /overlaps/);
});

test('cli usage errors exit 2', () => {
  assert.strictEqual(cli([]).code, 2);
  assert.strictEqual(cli(['bogus', 'x']).code, 2);
  assert.strictEqual(cli(['shift', tmp(SAMPLE)]).code, 2);
  assert.strictEqual(cli(['shift', tmp(SAMPLE), 'soon']).code, 2);
  assert.strictEqual(cli(['stretch', tmp(SAMPLE), '0', '25']).code, 2);
  assert.strictEqual(cli(['shift', tmp(SAMPLE), '1s', '-o']).code, 2);
  assert.strictEqual(cli(['--help']).code, 0);
});

test('cli missing, empty and all-dropped files', () => {
  const m = cli(['check', '/nonexistent/x.srt']);
  assert.strictEqual(m.code, 2);
  assert.match(m.err, /cannot read/);
  const e = cli(['check', tmp('')]);
  assert.strictEqual(e.code, 2);
  assert.match(e.err, /no subtitle cues/);
  const d = cli(['shift', tmp(SAMPLE), '-1h']);
  assert.strictEqual(d.code, 2); // '-1h' is a bad offset
  const g = cli(['shift', tmp(SAMPLE), '-3600000']);
  assert.strictEqual(g.code, 2);
  assert.match(g.err, /no cues left/);
});
