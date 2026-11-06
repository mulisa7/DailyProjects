#!/usr/bin/env node
import { readFileSync, writeFileSync, realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { convert, InputError, ConfigError } from './csv2ics.js';

const USAGE = `usage: csv2ics <file.csv | -> [options]

Convert a CSV list of events or a class timetable into an .ics calendar file.

options:
  -o, --output FILE        write the calendar here (default: stdout)
  --tz ZONE                IANA time zone the CSV times are in, e.g. Africa/Johannesburg
                           (default: floating times, read as local by the calendar app)
  --date-order ORDER       how to read dates like 03/04/2026: dmy or mdy (default: guess, fail if ambiguous)
  --duration MINUTES       length of events that have no end time (default 60)
  --delimiter CHAR         field separator; "tab" for tabs (default: detected)
  --name NAME              calendar name shown by some apps
  --skip-invalid           leave out bad rows instead of failing
  -h, --help               show this help

exit codes: 0 ok, 1 bad rows or bad file, 2 usage error`;

function parseArgs(argv) {
  const opts = {};
  let input = null;
  let output = null;
  const need = (i, flag) => {
    if (i + 1 >= argv.length) throw new UsageError(`${flag} needs a value`);
    return argv[i + 1];
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '-h':
      case '--help':
        return { help: true };
      case '-o':
      case '--output':
        output = need(i, a);
        i++;
        break;
      case '--tz':
        opts.timeZone = need(i, a);
        i++;
        break;
      case '--date-order':
        opts.dateOrder = need(i, a).toLowerCase();
        i++;
        break;
      case '--duration': {
        const v = need(i, a);
        if (!/^\d+$/.test(v)) throw new UsageError(`--duration must be a whole number of minutes, got "${v}"`);
        opts.defaultDuration = Number(v);
        i++;
        break;
      }
      case '--delimiter': {
        const v = need(i, a);
        opts.delimiter = v === 'tab' || v === '\\t' ? '\t' : v;
        if (opts.delimiter.length !== 1) throw new UsageError('--delimiter must be one character or "tab"');
        i++;
        break;
      }
      case '--name':
        opts.calendarName = need(i, a);
        i++;
        break;
      case '--skip-invalid':
        opts.skipInvalid = true;
        break;
      default:
        if (a.startsWith('-') && a !== '-') throw new UsageError(`unknown option ${a}`);
        if (input !== null) throw new UsageError('only one input file can be given');
        input = a;
    }
  }
  if (input === null) throw new UsageError('no input file given');
  return { input, output, opts };
}

class UsageError extends Error {}

export function main(argv, io = {}) {
  const out = io.stdout || ((s) => process.stdout.write(s));
  const err = io.stderr || ((s) => process.stderr.write(s));
  const readStdin = io.readStdin || (() => readFileSync(0, 'utf8'));

  let args;
  try {
    args = parseArgs(argv);
  } catch (e) {
    if (!(e instanceof UsageError)) throw e;
    err(`csv2ics: ${e.message}\n\n${USAGE}\n`);
    return 2;
  }
  if (args.help) {
    out(USAGE + '\n');
    return 0;
  }

  let text;
  try {
    text = args.input === '-' ? readStdin() : readFileSync(args.input, 'utf8');
  } catch (e) {
    err(`csv2ics: cannot read ${args.input}: ${e.code === 'ENOENT' ? 'file not found' : e.message}\n`);
    return 1;
  }

  let result;
  try {
    result = convert(text, args.opts);
  } catch (e) {
    if (!(e instanceof InputError)) throw e;
    err(`csv2ics: ${e.message}\n`);
    return e instanceof ConfigError ? 2 : 1;
  }

  for (const { line, message } of result.errors) {
    err(`line ${line}: ${message}${args.opts.skipInvalid ? ' (skipped)' : ''}\n`);
  }
  if (!result.ics) {
    err(result.errors.length && !args.opts.skipInvalid
      ? `csv2ics: ${result.errors.length} bad row(s), no calendar written. Fix them or use --skip-invalid.\n`
      : 'csv2ics: no valid events, no calendar written\n');
    return 1;
  }

  if (args.output) {
    try {
      writeFileSync(args.output, result.ics);
    } catch (e) {
      err(`csv2ics: cannot write ${args.output}: ${e.message}\n`);
      return 1;
    }
    err(`wrote ${result.events.length} event(s) to ${args.output}\n`);
  } else {
    out(result.ics);
  }
  return 0;
}

const invokedDirectly =
  process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (invokedDirectly) process.exitCode = main(process.argv.slice(2));
