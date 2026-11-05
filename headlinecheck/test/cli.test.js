'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { run, parseArgs } = require('../cli.js');

const CLI = path.join(__dirname, '..', 'cli.js');

function sink() {
  let out = '';
  return { write(s) { out += s; }, get text() { return out; } };
}

function withFile(content, fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hc-'));
  const file = path.join(dir, 'h.txt');
  fs.writeFileSync(file, content);
  try { return fn(file); } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

test('scores every line of a file', () => {
  withFile("Council approves budget\nYou won't believe what happened next\n", (f) => {
    const out = sink(), err = sink();
    assert.strictEqual(run([f], out, err), 0);
    assert.match(out.text, /Council approves budget/);
    assert.match(out.text, /curiosity gap/);
    assert.strictEqual(err.text, '');
  });
});

test('--min filters and reports when nothing matches', () => {
  withFile('Council approves budget\n', (f) => {
    const out = sink();
    assert.strictEqual(run(['--min', '2', f], out, sink()), 0);
    assert.match(out.text, /no headlines at or above 2 \(1 checked\)/);
  });
});

test('--json output is valid JSON with headline included', () => {
  withFile('Is this the end?\n', (f) => {
    const out = sink();
    run(['--json', f], out, sink());
    const rows = JSON.parse(out.text);
    assert.strictEqual(rows[0].headline, 'Is this the end?');
    assert.strictEqual(rows[0].level, 'medium');
  });
});

test('--fail-on returns 1 when a headline reaches the threshold', () => {
  withFile("You won't believe it\n", (f) => {
    assert.strictEqual(run(['--fail-on', '3', f], sink(), sink()), 1);
    assert.strictEqual(run(['--fail-on', '9', f], sink(), sink()), 0);
  });
});

test('blank lines, CRLF and BOM are tolerated', () => {
  withFile('﻿Council approves budget\r\n\r\n   \r\nIs this the end?\r\n', (f) => {
    const out = sink();
    run(['--json', f], out, sink());
    assert.strictEqual(JSON.parse(out.text).length, 2);
  });
});

test('empty file is an error with status 2', () => {
  withFile('\n  \n', (f) => {
    const err = sink();
    assert.strictEqual(run([f], sink(), err), 2);
    assert.match(err.text, /no headlines/);
  });
});

test('missing file is an error with status 2', () => {
  const err = sink();
  assert.strictEqual(run(['/no/such/file.txt'], sink(), err), 2);
  assert.match(err.text, /cannot read/);
});

test('bad options are rejected', () => {
  for (const args of [['--bogus'], ['--min'], ['--min', 'abc'], ['--fail-on', '-1']]) {
    const err = sink();
    assert.strictEqual(run(args, sink(), err), 2, args.join(' '));
    assert.match(err.text, /error:/);
  }
});

test('--help prints usage', () => {
  const out = sink();
  assert.strictEqual(run(['-h'], out, sink()), 0);
  assert.match(out.text, /Usage:/);
  assert.strictEqual(parseArgs(['--json']).json, true);
});

test('reads stdin when no file is given', () => {
  const r = spawnSync(process.execPath, [CLI, '--json'], { input: "You won't believe this\n", encoding: 'utf8' });
  assert.strictEqual(r.status, 0);
  assert.ok(JSON.parse(r.stdout)[0].score >= 3);
});

test('empty stdin exits 2', () => {
  const r = spawnSync(process.execPath, [CLI], { input: '', encoding: 'utf8' });
  assert.strictEqual(r.status, 2);
});
