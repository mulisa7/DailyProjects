'use strict';

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
const DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

class CronError extends Error {}

// Field definitions. Day of week is 1-7 with 1 = Sunday, as AWS documents it.
const FIELDS = [
  { name: 'minutes', min: 0, max: 59 },
  { name: 'hours', min: 0, max: 23 },
  { name: 'day-of-month', min: 1, max: 31, special: true },
  { name: 'month', min: 1, max: 12, names: MONTHS, nameBase: 1 },
  { name: 'day-of-week', min: 1, max: 7, names: DAYS, nameBase: 1, special: true },
  { name: 'year', min: 1970, max: 2199 },
];

function toNumber(tok, f) {
  if (/^\d+$/.test(tok)) return Number(tok);
  if (f.names) {
    const i = f.names.indexOf(tok.toUpperCase());
    if (i >= 0) return i + f.nameBase;
  }
  throw new CronError(`${f.name}: "${tok}" is not a valid value`);
}

function inRange(n, f, tok) {
  if (n < f.min || n > f.max) {
    throw new CronError(`${f.name}: ${tok} is out of range (${f.min}-${f.max})`);
  }
  return n;
}

function parseField(text, f) {
  if (text === '') throw new CronError(`${f.name}: empty field`);
  const out = { values: new Set(), any: false, noSpec: false, last: false, lastOffset: null, weekdays: [], lastDow: null, nth: [] };

  if (text === '?') {
    if (!f.special) throw new CronError(`${f.name}: "?" is only allowed in day-of-month and day-of-week`);
    out.noSpec = true;
    return out;
  }

  for (const part of text.split(',')) {
    if (part === '') throw new CronError(`${f.name}: empty list item in "${text}"`);

    if (f.name === 'day-of-month' && /^L(-\d+)?$/i.test(part)) {
      // Plain "L" is the last day. "L-n" (n days before the last day) is not listed in AWS docs.
      if (part.length > 1) throw new CronError(`day-of-month: "${part}" is not supported, only plain "L"`);
      out.last = true;
      continue;
    }
    if (f.name === 'day-of-month' && /^\d+W$/i.test(part)) {
      const d = Number(part.slice(0, -1));
      inRange(d, f, part);
      out.weekdays.push(d);
      continue;
    }
    if (f.name === 'day-of-week' && /^L$/i.test(part)) {
      // On its own "L" means Saturday (7)
      out.values.add(7);
      continue;
    }
    if (f.name === 'day-of-week' && /^[A-Za-z0-9]+L$/.test(part) && !/^(SUN|MON|TUE|WED|THU|FRI|SAT)$/i.test(part)) {
      const n = inRange(toNumber(part.slice(0, -1), f), f, part);
      out.lastDow = out.lastDow || [];
      out.lastDow.push(n);
      continue;
    }
    if (f.name === 'day-of-week' && part.includes('#')) {
      const bits = part.split('#');
      if (bits.length !== 2) throw new CronError(`day-of-week: "${part}" is not a valid nth-weekday form`);
      const d = inRange(toNumber(bits[0], f), f, part);
      if (!/^\d+$/.test(bits[1])) throw new CronError(`day-of-week: "${part}" needs a number after #`);
      const n = Number(bits[1]);
      if (n < 1 || n > 5) throw new CronError(`day-of-week: occurrence in "${part}" must be 1-5`);
      out.nth.push([d, n]);
      continue;
    }

    let [range, step] = part.split('/');
    if (part.split('/').length > 2) throw new CronError(`${f.name}: too many "/" in "${part}"`);
    let stepN = null;
    if (step !== undefined) {
      if (!/^\d+$/.test(step) || Number(step) < 1) throw new CronError(`${f.name}: step in "${part}" must be a positive number`);
      stepN = Number(step);
    }

    let lo, hi;
    if (range === '*') {
      lo = f.min;
      hi = f.max;
      if (stepN === null) out.any = true;
    } else if (range.includes('-')) {
      const [a, b, ...rest] = range.split('-');
      if (rest.length || a === '' || b === '' || b === undefined) throw new CronError(`${f.name}: "${part}" is not a valid range`);
      lo = inRange(toNumber(a, f), f, part);
      hi = inRange(toNumber(b, f), f, part);
      if (lo > hi) {
        throw new CronError(`${f.name}: range ${part} runs backwards`);
      }
    } else {
      lo = inRange(toNumber(range, f), f, part);
      hi = stepN === null ? lo : f.max;
    }
    for (let v = lo; v <= hi; v += stepN || 1) out.values.add(v);
  }
  return out;
}

function parseCron(body) {
  const tokens = body.trim().split(/\s+/);
  if (tokens.length !== 6 || tokens[0] === '') {
    throw new CronError(`expected 6 fields (minutes hours day-of-month month day-of-week year), got ${tokens[0] === '' ? 0 : tokens.length}`);
  }
  const fields = tokens.map((t, i) => parseField(t, FIELDS[i]));
  const [, , dom, , dow] = fields;
  const domQ = dom.noSpec;
  const dowQ = dow.noSpec;
  if (domQ && dowQ) throw new CronError('day-of-month and day-of-week cannot both be "?"');
  if (!domQ && !dowQ) {
    throw new CronError('day-of-month and day-of-week: one of them must be "?" (you cannot set both)');
  }
  return { kind: 'cron', fields, source: tokens.join(' ') };
}

function parseRate(body) {
  const m = /^\s*(\S+)\s+(\S+)\s*$/.exec(body);
  if (!m) throw new CronError('rate() needs a value and a unit, for example rate(5 minutes)');
  if (!/^\d+$/.test(m[1]) || Number(m[1]) < 1) throw new CronError(`rate value "${m[1]}" must be a positive whole number`);
  const n = Number(m[1]);
  const unit = m[2].toLowerCase();
  const base = ['minute', 'hour', 'day'];
  const ok = base.find((u) => unit === u || unit === u + 's');
  if (!ok) throw new CronError(`rate unit "${m[2]}" must be minute(s), hour(s) or day(s)`);
  if (n === 1 && unit.endsWith('s')) throw new CronError(`use the singular "${ok}" when the value is 1`);
  if (n > 1 && !unit.endsWith('s')) throw new CronError(`use the plural "${ok}s" when the value is greater than 1`);
  const mult = { minute: 60000, hour: 3600000, day: 86400000 }[ok];
  return { kind: 'rate', value: n, unit: ok, intervalMs: n * mult, source: `${n} ${unit}` };
}

function parse(expr) {
  if (typeof expr !== 'string' || expr.trim() === '') throw new CronError('empty expression');
  const m = /^\s*(cron|rate)\s*\(([^()]*)\)\s*$/i.exec(expr);
  if (!m) throw new CronError('expression must look like cron(...) or rate(...)');
  return m[1].toLowerCase() === 'cron' ? parseCron(m[2]) : parseRate(m[2]);
}

module.exports = { parse, CronError, MONTHS, DAYS };
