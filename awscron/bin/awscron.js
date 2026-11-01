#!/usr/bin/env node
'use strict';

const { parse, CronError } = require('../src/parse');
const { nextRuns } = require('../src/schedule');
const { fmt } = require('../src/format');

const USAGE = `usage: awscron [-n COUNT] [--from ISO_DATE] [--quiet] EXPRESSION [EXPRESSION...]
       awscron [options] -        (read one expression per line from stdin)

Checks AWS EventBridge / CloudWatch Events schedule expressions and prints
the next run times in UTC.

  -n, --count N     number of run times to print (default 5, max 100)
  --from ISO_DATE   start point instead of now, e.g. 2026-01-01T00:00:00Z
  -q, --quiet       print only errors, no run times
  -h, --help        show this help

Exit codes: 0 all valid, 1 at least one invalid, 2 bad usage.`;

function parseArgs(argv) {
  const opts = { count: 5, from: null, quiet: false, exprs: [], stdin: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') return { help: true };
    if (a === '-q' || a === '--quiet') opts.quiet = true;
    else if (a === '-n' || a === '--count') {
      const v = argv[++i];
      if (v === undefined || !/^\d+$/.test(v) || Number(v) < 1 || Number(v) > 100) {
        return { error: '--count needs a whole number from 1 to 100' };
      }
      opts.count = Number(v);
    } else if (a === '--from') {
      const v = argv[++i];
      const d = v === undefined ? null : new Date(v);
      if (!d || Number.isNaN(d.getTime())) return { error: '--from needs a valid date such as 2026-01-01T00:00:00Z' };
      opts.from = d;
    } else if (a === '-') opts.stdin = true;
    else if (a.startsWith('-') && a.length > 1 && !/^-?\w*\(/.test(a)) return { error: `unknown option ${a}` };
    else opts.exprs.push(a);
  }
  return opts;
}

function run(argv, stdin, out, err) {
  const opts = parseArgs(argv);
  if (opts.help) {
    out.write(USAGE + '\n');
    return 0;
  }
  if (opts.error) {
    err.write(`awscron: ${opts.error}\n`);
    return 2;
  }
  let exprs = opts.exprs;
  if (opts.stdin) {
    exprs = exprs.concat(stdin.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith('#')));
  }
  if (exprs.length === 0) {
    err.write('awscron: no expression given\n' + USAGE + '\n');
    return 2;
  }
  const from = opts.from || new Date();
  let bad = 0;
  for (const e of exprs) {
    try {
      const p = parse(e);
      out.write(`OK   ${e}\n`);
      if (!opts.quiet) {
        const runs = nextRuns(p, from, opts.count);
        if (runs.length === 0) out.write('     (no run times in the next 20 years)\n');
        for (const r of runs) out.write(`     ${fmt(r)}\n`);
      }
    } catch (ex) {
      if (!(ex instanceof CronError)) throw ex;
      bad++;
      err.write(`FAIL ${e}\n     ${ex.message}\n`);
    }
  }
  return bad ? 1 : 0;
}

if (require.main === module) {
  const argv = process.argv.slice(2);
  let input = '';
  if (argv.includes('-')) {
    try {
      input = require('fs').readFileSync(0, 'utf8');
    } catch (e) {
      input = '';
    }
  }
  process.exitCode = run(argv, input, process.stdout, process.stderr);
}

module.exports = { run, parseArgs };
