'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { execFileSync, spawnSync } = require('child_process');
const path = require('path');
const { parseSpec, analyze, format, categoryAverage, SpecError } = require('../grade.js');

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test('basic weighted grade and needed final', () => {
  const r = analyze(parseSpec('HW 50%: 80/100\nFinal 50%:\ntarget: 90'));
  near(r.currentGrade, 80);
  near(r.targets[0].needed, 100);
  assert.equal(r.targets[0].status, 'possible');
});

test('out of reach and secured', () => {
  const r = analyze(parseSpec('A 80%: 100%\nFinal 20%:\ntarget: 50'));
  assert.equal(r.targets[0].status, 'secured');
  const r2 = analyze(parseSpec('A 80%: 50%\nFinal 20%:\ntarget: 90'));
  assert.equal(r2.targets[0].status, 'out of reach');
  near(r2.targets[0].needed, 250);
});

test('drop lowest uses percentage, never drops all', () => {
  near(categoryAverage({ drop: 1, scores: [{ earned: 1, possible: 10 }, { earned: 50, possible: 100 }] }), 50);
  near(categoryAverage({ drop: 5, scores: [{ earned: 3, possible: 10 }] }), 30);
});

test('mixed score formats and decimals', () => {
  const s = parseSpec('Q 100%: 7.5/10, 50%');
  near(categoryAverage(s.categories[0]), (7.5 + 50) / 110 * 100);
});

test('comments, blank lines, CRLF, default targets', () => {
  const s = parseSpec('# hi\r\n\r\nA 100%: 90/100 # trailing\r\n');
  assert.equal(s.categories.length, 1);
  assert.deepEqual(s.targets, [90, 80, 70, 60]);
});

test('all graded: reached or missed', () => {
  const r = analyze(parseSpec('A 100%: 85%\ntarget: 80 90'));
  assert.deepEqual(r.targets.map(t => t.status), ['missed', 'reached']);
});

test('no scores at all', () => {
  const r = analyze(parseSpec('A 100%:'));
  assert.equal(r.currentGrade, null);
  assert.match(format(r), /No scores entered/);
});

test('errors', () => {
  assert.throws(() => parseSpec(''), SpecError);
  assert.throws(() => parseSpec('   \n# only comment'), /no categories/);
  assert.throws(() => parseSpec(null), SpecError);
  assert.throws(() => parseSpec('garbage'), /line 1/);
  assert.throws(() => parseSpec('A 10%: 5/0'), /above 0/);
  assert.throws(() => parseSpec('A 10%: abc'), /cannot read score/);
  assert.throws(() => parseSpec('A 10%: -3/10'), /negative/);
  assert.throws(() => parseSpec('A 0%: 5/10'), /above 0/);
  assert.throws(() => parseSpec('A 50%: 1/2\na 50%: 1/2'), /duplicate/);
  assert.throws(() => parseSpec('A 100%: 1/2\ntarget: 120'), /bad target/);
  assert.throws(() => analyze(parseSpec('A 50%: 1/2\nB 40%:')), /add up to 90%/);
});

test('scores above 100% are allowed (extra credit)', () => {
  near(analyze(parseSpec('A 100%: 11/10')).currentGrade, 110);
});

const cli = path.join(__dirname, '..', 'cli.js');
test('cli runs on the example', () => {
  const out = execFileSync('node', [cli, path.join(__dirname, '..', 'example.txt')]).toString();
  assert.match(out, /To finish with 90%/);
});
test('cli exit codes', () => {
  assert.equal(spawnSync('node', [cli]).status, 2);
  assert.equal(spawnSync('node', [cli, '/no/such/file']).status, 2);
  const r = spawnSync('node', [cli, '-'], { input: 'bad line' });
  assert.equal(r.status, 1);
  assert.match(r.stderr.toString(), /^error: line 1/);
});
