#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { scoreHeadline } = require(path.join(__dirname, 'extension', 'scoring.js'));

const USAGE = `Usage: node cli.js [options] [file ...]

Scores headlines (one per line) for clickbait signals. Reads stdin when no file is given.

Options:
  --min <n>      only print headlines scoring at least n (default 0)
  --json         print JSON instead of text
  --fail-on <n>  exit with status 1 if any headline scores at least n
  -h, --help     show this message

Exit status: 0 ok, 1 --fail-on threshold reached, 2 bad usage or input.
`;

function parseArgs(argv) {
  const opts = { min: 0, json: false, failOn: null, files: [], help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { opts.help = true; continue; }
    if (a === '--json') { opts.json = true; continue; }
    if (a === '--min' || a === '--fail-on') {
      const raw = argv[++i];
      const n = Number(raw);
      if (raw === undefined || raw === '' || !Number.isFinite(n) || n < 0) {
        throw new Error(a + ' needs a non-negative number');
      }
      if (a === '--min') opts.min = n; else opts.failOn = n;
      continue;
    }
    if (a.startsWith('-')) throw new Error('unknown option: ' + a);
    opts.files.push(a);
  }
  return opts;
}

function readInput(files) {
  if (files.length === 0) return fs.readFileSync(0, 'utf8');
  return files.map((f) => {
    try { return fs.readFileSync(f, 'utf8'); } catch (e) { throw new Error('cannot read ' + f + ': ' + e.code); }
  }).join('\n');
}

function run(argv, stdout, stderr) {
  let opts;
  try { opts = parseArgs(argv); } catch (e) {
    stderr.write('error: ' + e.message + '\n' + USAGE);
    return 2;
  }
  if (opts.help) { stdout.write(USAGE); return 0; }

  let text;
  try { text = readInput(opts.files); } catch (e) {
    stderr.write('error: ' + e.message + '\n');
    return 2;
  }
  const lines = text.replace(/^﻿/, '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) {
    stderr.write('error: no headlines in input\n');
    return 2;
  }

  const rows = lines.map((l) => Object.assign({ headline: l }, scoreHeadline(l)));
  const shown = rows.filter((r) => r.score >= opts.min);
  if (opts.json) {
    stdout.write(JSON.stringify(shown, null, 2) + '\n');
  } else if (shown.length === 0) {
    stdout.write('no headlines at or above ' + opts.min + ' (' + rows.length + ' checked)\n');
  } else {
    shown.forEach((r) => {
      stdout.write(String(r.score).padStart(4) + '  ' + r.level.padEnd(6) + '  ' + r.headline + '\n');
      r.reasons.forEach((why) => stdout.write('                - ' + why + '\n'));
    });
  }
  return opts.failOn !== null && rows.some((r) => r.score >= opts.failOn) ? 1 : 0;
}

if (require.main === module) {
  process.exitCode = run(process.argv.slice(2), process.stdout, process.stderr);
}

module.exports = { run, parseArgs };
