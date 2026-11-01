#!/usr/bin/env node
'use strict';
const fs = require('fs');
const srt = require('./srt');

const USAGE = `srtfix - fix out-of-sync SRT subtitle files

Usage:
  srtfix shift <file> <offset>            offset like 2.5s, -800ms, 1500 (ms)
  srtfix stretch <file> <from-fps> <to-fps>   e.g. 23.976 25
  srtfix sync <file> <old1> <new1> <old2> <new2>   times like 00:01:02,500
  srtfix check <file>                     report problems, change nothing
  srtfix sort <file>                      sort by start time and renumber

Options:
  -o, --out <file>   write here instead of stdout
  -h, --help         show this help

Exit codes: 0 ok, 1 problems found by check, 2 bad usage or unreadable input.
`;

function parseOffset(s) {
  const m = /^([+-]?\d+(?:\.\d+)?)(ms|s)?$/.exec(String(s));
  if (!m) throw new Error(`bad offset "${s}" (use 2.5s, -800ms or milliseconds)`);
  const n = Number(m[1]);
  return m[2] === 's' ? n * 1000 : n;
}

function parseFps(s) {
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0) throw new Error(`bad frame rate "${s}"`);
  return n;
}

function readCues(file, err) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); }
  catch (e) { throw new Error(`cannot read ${file}: ${e.code || e.message}`); }
  const { cues, warnings } = srt.parse(text);
  warnings.forEach((w) => err(`warning: ${w}`));
  if (!cues.length) throw new Error(`${file}: no subtitle cues found`);
  return cues;
}

function run(argv, io) {
  const out = io.out, err = io.err;
  const args = [];
  let outFile = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { out(USAGE); return 0; }
    if (a === '-o' || a === '--out') {
      if (i + 1 >= argv.length) { err('error: --out needs a file name'); return 2; }
      outFile = argv[++i];
    } else args.push(a);
  }
  if (!args.length) { err(USAGE); return 2; }
  const [cmd, file, ...rest] = args;
  const need = { shift: 1, stretch: 2, sync: 4, check: 0, sort: 0 };
  if (!(cmd in need)) { err(`error: unknown command "${cmd}"\n${USAGE}`); return 2; }
  if (!file || rest.length !== need[cmd]) { err(`error: wrong number of arguments for ${cmd}\n${USAGE}`); return 2; }

  try {
    const cues = readCues(file, err);
    let result;
    if (cmd === 'check') {
      const problems = srt.validate(cues);
      if (!problems.length) { out(`${cues.length} cues, no problems found`); return 0; }
      problems.forEach((p) => out(p));
      out(`${cues.length} cues, ${problems.length} problem(s)`);
      return 1;
    }
    if (cmd === 'shift') result = srt.shift(cues, parseOffset(rest[0]));
    else if (cmd === 'stretch') result = srt.stretch(cues, parseFps(rest[0]) / parseFps(rest[1]));
    else if (cmd === 'sync') result = srt.sync(cues, srt.parseTime(rest[0]), srt.parseTime(rest[1]), srt.parseTime(rest[2]), srt.parseTime(rest[3]));
    else result = srt.sortCues(cues);
    if (!result.length) throw new Error('no cues left after the change');
    const text = srt.format(result);
    if (outFile) { fs.writeFileSync(outFile, text); err(`wrote ${result.length} cues to ${outFile}`); }
    else out(text.replace(/\n$/, ''));
    return 0;
  } catch (e) {
    err(`error: ${e.message}`);
    return 2;
  }
}

module.exports = { run, parseOffset };
if (require.main === module) {
  process.exitCode = run(process.argv.slice(2), {
    out: (s) => process.stdout.write(s + '\n'),
    err: (s) => process.stderr.write(s + '\n'),
  });
}
