#!/usr/bin/env node
'use strict';
const fs = require('fs');
const { analyze } = require('./analyze');

const USAGE = `usage: plainwrite [options] [file]
Reads FILE (or stdin when omitted or "-") and reports readability.

  --markdown          strip Markdown (code, links, headings) before analysing
  --json              print the result as JSON
  --max-grade N       exit 1 if the grade level is above N
  --max-sentence N    flag sentences longer than N words (default 25)
  -h, --help          show this help
Exit codes: 0 ok, 1 grade limit exceeded, 2 bad usage or unreadable input.`;

function parseArgs(argv) {
  const o = { markdown: false, json: false, maxGrade: null, maxSentence: 25, file: null, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const num = (name) => {
      const v = argv[++i];
      const n = Number(v);
      if (v === undefined || v === '' || !Number.isFinite(n) || n <= 0) throw new Error(`${name} needs a positive number, got ${JSON.stringify(v)}`);
      return n;
    };
    if (a === '-h' || a === '--help') o.help = true;
    else if (a === '--markdown') o.markdown = true;
    else if (a === '--json') o.json = true;
    else if (a === '--max-grade') o.maxGrade = num(a);
    else if (a === '--max-sentence') o.maxSentence = Math.floor(num(a));
    else if (a === '-') o.file = '-';
    else if (a.startsWith('-')) throw new Error(`unknown option ${a}`);
    else if (o.file !== null) throw new Error('only one input file is supported');
    else o.file = a;
  }
  return o;
}

function format(r) {
  if (r.empty) return 'No text to analyse.';
  const lines = [
    `Words: ${r.stats.words}   Sentences: ${r.stats.sentences}   Avg sentence: ${r.avgSentenceLength} words`,
    `Reading ease: ${r.readingEase} (${r.label})   Grade level: ${r.gradeLevel}`,
  ];
  if (r.issues.length === 0) lines.push('No issues flagged.');
  else {
    lines.push('', `${r.issues.length} thing(s) to look at:`);
    for (const it of r.issues) {
      const snippet = it.text.length > 70 ? it.text.slice(0, 67) + '...' : it.text;
      lines.push(`  sentence ${it.sentence}: ${it.type} (${it.detail}) - "${snippet}"`);
    }
  }
  return lines.join('\n');
}

function run(argv, stdinText, out, err, readFile = (p) => fs.readFileSync(p, 'utf8')) {
  let o;
  try { o = parseArgs(argv); } catch (e) { err(`plainwrite: ${e.message}\n${USAGE}`); return 2; }
  if (o.help) { out(USAGE); return 0; }
  let text;
  if (o.file && o.file !== '-') {
    try { text = readFile(o.file); } catch (e) { err(`plainwrite: cannot read ${o.file}: ${e.code || e.message}`); return 2; }
  } else {
    if (stdinText === null) { err('plainwrite: no input file and nothing on stdin'); return 2; }
    text = stdinText;
  }
  if (text.includes('\u0000')) { err('plainwrite: input looks like a binary file'); return 2; }
  const r = analyze(text.replace(/^﻿/, ''), { markdown: o.markdown, maxSentenceWords: o.maxSentence });
  out(o.json ? JSON.stringify(r, null, 2) : format(r));
  if (o.maxGrade !== null && !r.empty && r.gradeLevel > o.maxGrade) {
    err(`plainwrite: grade level ${r.gradeLevel} is above the limit of ${o.maxGrade}`);
    return 1;
  }
  return 0;
}

if (require.main === module) {
  const argv = process.argv.slice(2);
  const wantsStdin = !argv.some((a) => !a.startsWith('-') || a === '-') ;
  let stdin = null;
  if (wantsStdin && !process.stdin.isTTY && !argv.includes('-h') && !argv.includes('--help')) {
    try { stdin = fs.readFileSync(0, 'utf8'); } catch { stdin = null; }
  }
  process.exitCode = run(argv, stdin, (s) => console.log(s), (s) => console.error(s));
}

module.exports = { run, parseArgs, format };
