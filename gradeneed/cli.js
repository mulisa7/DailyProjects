#!/usr/bin/env node
'use strict';
const fs = require('fs');
const { parseSpec, analyze, format, SpecError } = require('./grade.js');

const arg = process.argv[2];
if (arg === '-h' || arg === '--help') {
  console.log('usage: node cli.js <spec-file>   (use - to read stdin)');
  process.exit(0);
}
if (!arg) {
  console.error('error: no spec file given. usage: node cli.js <spec-file>');
  process.exit(2);
}
let text;
try {
  text = fs.readFileSync(arg === '-' ? 0 : arg, 'utf8');
} catch (e) {
  console.error(`error: cannot read ${arg}: ${e.code || e.message}`);
  process.exit(2);
}
try {
  console.log(format(analyze(parseSpec(text))));
} catch (e) {
  if (e instanceof SpecError) { console.error('error: ' + e.message); process.exit(1); }
  throw e;
}
