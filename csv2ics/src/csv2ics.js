// Core conversion: CSV text in, iCalendar (RFC 5545) text out.
// Works in Node and in the browser; no dependencies.

export class InputError extends Error {}

// Bad options rather than bad data.
export class ConfigError extends InputError {}

// ---------- CSV ----------

export function detectDelimiter(text) {
  const firstLine = text.split(/\r?\n/, 1)[0] || '';
  let best = ',';
  let bestCount = 0;
  for (const d of [',', ';', '\t']) {
    let count = 0;
    let quoted = false;
    for (const ch of firstLine) {
      if (ch === '"') quoted = !quoted;
      else if (ch === d && !quoted) count++;
    }
    if (count > bestCount) {
      best = d;
      bestCount = count;
    }
  }
  return best;
}

export function parseCsv(text, delimiter) {
  if (typeof text !== 'string') throw new InputError('CSV input must be text');
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const d = delimiter || detectDelimiter(text);
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        quoted = false;
      } else {
        field += ch;
      }
      i++;
      continue;
    }
    if (ch === '"' && field === '') {
      quoted = true;
    } else if (ch === d) {
      row.push(field);
      field = '';
    } else if (ch === '\n' || ch === '\r') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
      if (ch === '\r' && text[i + 1] === '\n') i++;
    } else {
      field += ch;
    }
    i++;
  }
  if (quoted) throw new InputError('CSV has an unclosed quote');
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  // Drop fully blank lines.
  return rows.filter((r) => r.some((c) => c.trim() !== ''));
}

// ---------- column mapping ----------

const ALIASES = {
  title: ['title', 'subject', 'summary', 'name', 'event', 'course', 'class'],
  start: ['start', 'starts', 'start datetime', 'begin'],
  startDate: ['start date', 'date', 'day'],
  startTime: ['start time', 'time', 'from'],
  end: ['end', 'ends', 'end datetime', 'finish'],
  endDate: ['end date'],
  endTime: ['end time', 'to', 'until time'],
  allDay: ['all day', 'all day event', 'allday', 'all-day'],
  location: ['location', 'place', 'room', 'venue', 'where'],
  description: ['description', 'notes', 'note', 'details'],
  repeat: ['repeat', 'repeats', 'recurrence', 'frequency'],
  repeatUntil: ['repeat until', 'until'],
  repeatCount: ['repeat count', 'count', 'occurrences'],
};

function normHeader(h) {
  return h.trim().toLowerCase().replace(/[_\s]+/g, ' ');
}

export function mapColumns(header) {
  const map = {};
  const seen = header.map(normHeader);
  for (const [key, names] of Object.entries(ALIASES)) {
    const idx = seen.findIndex((h) => names.includes(h));
    if (idx !== -1) map[key] = idx;
  }
  if (map.title === undefined) {
    throw new InputError(`no title column found; expected one of: ${ALIASES.title.join(', ')}`);
  }
  if (map.start === undefined && map.startDate === undefined) {
    throw new InputError('no start column found; add a "Start Date" (or "Start") column');
  }
  return map;
}

// ---------- dates and times ----------

function pad(n, w = 2) {
  return String(n).padStart(w, '0');
}

function validDate(y, m, d) {
  if (m < 1 || m > 12 || d < 1) return false;
  const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return d <= dim;
}

export function parseDate(value, order = 'ymd') {
  const s = value.trim();
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
  let y, mo, d;
  if (m) {
    [y, mo, d] = [+m[1], +m[2], +m[3]];
  } else if ((m = /^(\d{1,4})[/.](\d{1,2})[/.](\d{1,4})$/.exec(s))) {
    const [a, b, c] = [+m[1], +m[2], +m[3]];
    if (m[1].length === 4) {
      [y, mo, d] = [a, b, c];
    } else if (m[3].length === 4) {
      if (order === 'dmy') [d, mo, y] = [a, b, c];
      else if (order === 'mdy') [mo, d, y] = [a, b, c];
      else if (a > 12 && b <= 12) [d, mo, y] = [a, b, c];
      else if (b > 12 && a <= 12) [mo, d, y] = [a, b, c];
      else if (a === b) [d, mo, y] = [a, b, c];
      else throw new InputError(`ambiguous date "${s}"; pass a date order (dmy or mdy)`);
    } else {
      throw new InputError(`unrecognised date "${s}"; use YYYY-MM-DD`);
    }
  } else {
    throw new InputError(`unrecognised date "${s}"; use YYYY-MM-DD`);
  }
  if (!validDate(y, mo, d)) throw new InputError(`invalid date "${s}"`);
  return { y, m: mo, d };
}

export function parseTime(value) {
  const s = value.trim().toLowerCase().replace(/\s+/g, '');
  const m = /^(\d{1,2})(?:[:.](\d{2}))?(?::(\d{2}))?(am|pm|a|p)?$/.exec(s);
  if (!m || (m[2] === undefined && !m[4])) {
    throw new InputError(`unrecognised time "${value.trim()}"; use HH:MM or h:mm am/pm`);
  }
  let h = +m[1];
  const mi = m[2] ? +m[2] : 0;
  const sec = m[3] ? +m[3] : 0;
  if (m[4]) {
    if (h < 1 || h > 12) throw new InputError(`invalid time "${value.trim()}"`);
    if (m[4].startsWith('p') && h !== 12) h += 12;
    if (m[4].startsWith('a') && h === 12) h = 0;
  }
  if (h > 23 || mi > 59 || sec > 59) throw new InputError(`invalid time "${value.trim()}"`);
  return { h, mi, s: sec };
}

function parseDateTime(value, order) {
  const s = value.trim();
  const m = /^(\S+)(?:[T ]+(.+))?$/.exec(s);
  const date = parseDate(m[1], order);
  const time = m[2] ? parseTime(m[2].replace(/z$/i, '')) : null;
  return { date, time };
}

export function checkTimeZone(tz) {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

function zoneOffsetMs(utcMs, tz) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcMs));
  const v = {};
  for (const p of parts) v[p.type] = +p.value;
  const asUtc = Date.UTC(v.year, v.month - 1, v.day, v.hour, v.minute, v.second);
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

// Wall-clock time in a zone -> UTC epoch ms. Times inside a DST gap move forward.
export function zonedToUtc(date, time, tz) {
  const wall = Date.UTC(date.y, date.m - 1, date.d, time.h, time.mi, time.s);
  let utc = wall - zoneOffsetMs(wall, tz);
  const second = wall - zoneOffsetMs(utc, tz);
  if (second !== utc) utc = Math.max(utc, second);
  return utc;
}

function fmtUtc(ms) {
  const t = new Date(ms);
  return (
    `${t.getUTCFullYear()}${pad(t.getUTCMonth() + 1)}${pad(t.getUTCDate())}` +
    `T${pad(t.getUTCHours())}${pad(t.getUTCMinutes())}${pad(t.getUTCSeconds())}Z`
  );
}

function fmtDate(date) {
  return `${pad(date.y, 4)}${pad(date.m)}${pad(date.d)}`;
}

function addDays(date, n) {
  const t = new Date(Date.UTC(date.y, date.m - 1, date.d + n));
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
}

function truthy(v) {
  return /^(1|y|yes|true|x|all day)$/i.test(v.trim());
}

// ---------- iCalendar text ----------

export function escapeText(s) {
  return s
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}

// Fold lines longer than 75 octets without splitting a UTF-8 character.
export function foldLine(line) {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  const out = [];
  let cur = '';
  let curBytes = 0;
  let limit = 75;
  for (const ch of line) {
    const b = enc.encode(ch).length;
    if (curBytes + b > limit) {
      out.push(cur);
      cur = '';
      curBytes = 0;
      limit = 74; // continuation lines start with a space
    }
    cur += ch;
    curBytes += b;
  }
  out.push(cur);
  return out.join('\r\n ');
}

function hash(str) {
  // FNV-1a 32-bit, twice with different seeds, for a stable UID.
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193 ^ 0x5bd1e995;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ c, 0x5bd1e995) >>> 0;
  }
  return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0');
}

const FREQ = { daily: 'DAILY', weekly: 'WEEKLY', monthly: 'MONTHLY', yearly: 'YEARLY', annually: 'YEARLY' };

// ---------- row -> event ----------

function cell(row, idx) {
  return idx === undefined ? '' : (row[idx] ?? '').trim();
}

export function buildEvent(row, map, opts) {
  const order = opts.dateOrder || 'ymd';
  const tz = opts.timeZone || '';
  const duration = opts.defaultDuration ?? 60;
  const get = (k) => cell(row, map[k]);

  const title = get('title');
  if (!title) throw new InputError('title is empty');

  let startDate, startTime, endDate, endTime;
  if (get('start')) {
    ({ date: startDate, time: startTime } = parseDateTime(get('start'), order));
  } else if (get('startDate')) {
    startDate = parseDate(get('startDate'), order);
  } else {
    throw new InputError('start date is empty');
  }
  if (get('startTime')) startTime = parseTime(get('startTime'));

  if (get('end')) {
    ({ date: endDate, time: endTime } = parseDateTime(get('end'), order));
  } else if (get('endDate')) {
    endDate = parseDate(get('endDate'), order);
  }
  if (get('endTime')) endTime = parseTime(get('endTime'));

  const allDay = (map.allDay !== undefined && truthy(get('allDay'))) || (!startTime && !endTime);
  const ev = { title, allDay };

  if (allDay) {
    const last = endDate || startDate;
    ev.start = startDate;
    ev.endExclusive = addDays(last, 1);
    if (fmtDate(last) < fmtDate(startDate)) throw new InputError('end date is before start date');
  } else {
    if (!startTime) throw new InputError('end time given but start time is empty');
    const toMs = (d, t) =>
      tz ? zonedToUtc(d, t, tz) : Date.UTC(d.y, d.m - 1, d.d, t.h, t.mi, t.s);
    ev.startMs = toMs(startDate, startTime);
    if (endTime) {
      ev.endMs = toMs(endDate || startDate, endTime);
      // "22:00 to 01:00" on the same date means the next day.
      if (!endDate && ev.endMs <= ev.startMs) ev.endMs = toMs(addDays(startDate, 1), endTime);
    } else if (endDate) {
      throw new InputError('end date given without an end time');
    } else {
      ev.endMs = ev.startMs + duration * 60000;
    }
    if (ev.endMs <= ev.startMs) throw new InputError('end is not after start');
  }

  const loc = get('location');
  const desc = get('description');
  if (loc) ev.location = loc;
  if (desc) ev.description = desc;

  const rep = get('repeat').toLowerCase();
  if (rep && rep !== 'none' && rep !== 'no') {
    const freq = FREQ[rep];
    if (!freq) throw new InputError(`unknown repeat "${rep}"; use daily, weekly, monthly or yearly`);
    let rule = `FREQ=${freq}`;
    const until = get('repeatUntil');
    const count = get('repeatCount');
    if (until && count) throw new InputError('give either a repeat until date or a repeat count, not both');
    if (count) {
      if (!/^\d+$/.test(count) || +count < 1) throw new InputError(`invalid repeat count "${count}"`);
      rule += `;COUNT=${+count}`;
    } else if (until) {
      const u = parseDate(until, order);
      if (fmtDate(u) < fmtDate(startDate)) throw new InputError('repeat until is before the start date');
      // UNTIL must match DTSTART's type: a date for all-day, UTC time otherwise.
      if (allDay) rule += `;UNTIL=${fmtDate(u)}`;
      else {
        const endOfDay = { h: 23, mi: 59, s: 59 };
        const ms = tz ? zonedToUtc(u, endOfDay, tz) : Date.UTC(u.y, u.m - 1, u.d, 23, 59, 59);
        rule += `;UNTIL=${tz ? fmtUtc(ms) : fmtUtc(ms).slice(0, -1)}`;
      }
    }
    ev.rrule = rule;
  }
  return ev;
}

function eventLines(ev, opts, stamp) {
  const floating = !opts.timeZone;
  const fmt = (ms) => (floating ? fmtUtc(ms).slice(0, -1) : fmtUtc(ms));
  const lines = ['BEGIN:VEVENT'];
  const key = [ev.title, ev.allDay ? fmtDate(ev.start) : ev.startMs, ev.location || '', ev.index].join('|');
  lines.push(`UID:${hash(key)}@csv2ics`);
  lines.push(`DTSTAMP:${stamp}`);
  if (ev.allDay) {
    lines.push(`DTSTART;VALUE=DATE:${fmtDate(ev.start)}`);
    lines.push(`DTEND;VALUE=DATE:${fmtDate(ev.endExclusive)}`);
  } else {
    lines.push(`DTSTART:${fmt(ev.startMs)}`);
    lines.push(`DTEND:${fmt(ev.endMs)}`);
  }
  if (ev.rrule) lines.push(`RRULE:${ev.rrule}`);
  lines.push(`SUMMARY:${escapeText(ev.title)}`);
  if (ev.location) lines.push(`LOCATION:${escapeText(ev.location)}`);
  if (ev.description) lines.push(`DESCRIPTION:${escapeText(ev.description)}`);
  lines.push('END:VEVENT');
  return lines;
}

/**
 * Convert CSV text to an .ics string.
 * opts: { timeZone, dateOrder ('ymd'|'dmy'|'mdy'), defaultDuration (minutes),
 *         delimiter, calendarName, skipInvalid, now (Date, for DTSTAMP) }
 * Returns { ics, events, errors } where errors is [{ line, message }].
 * Throws InputError for problems with the file as a whole.
 */
export function convert(text, opts = {}) {
  if (opts.timeZone && !checkTimeZone(opts.timeZone)) {
    throw new ConfigError(`unknown time zone "${opts.timeZone}"; use an IANA name like Africa/Johannesburg`);
  }
  if (opts.dateOrder && !['ymd', 'dmy', 'mdy'].includes(opts.dateOrder)) {
    throw new ConfigError(`date order must be ymd, dmy or mdy, not "${opts.dateOrder}"`);
  }
  const dur = opts.defaultDuration;
  if (dur !== undefined && !(Number.isInteger(dur) && dur > 0 && dur <= 7 * 24 * 60)) {
    throw new ConfigError('default duration must be a whole number of minutes between 1 and 10080');
  }
  const rows = parseCsv(text, opts.delimiter);
  if (rows.length === 0) throw new InputError('the CSV is empty');
  if (rows.length === 1) throw new InputError('the CSV has a header row but no events');
  const map = mapColumns(rows[0]);

  const events = [];
  const errors = [];
  rows.slice(1).forEach((row, i) => {
    const line = i + 2;
    try {
      const ev = buildEvent(row, map, opts);
      ev.index = i;
      ev.line = line;
      events.push(ev);
    } catch (e) {
      if (!(e instanceof InputError)) throw e;
      errors.push({ line, message: e.message });
    }
  });

  if (errors.length && !opts.skipInvalid) return { ics: null, events, errors };
  if (events.length === 0) return { ics: null, events, errors };

  const stamp = fmtUtc((opts.now || new Date()).getTime());
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//csv2ics//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'];
  if (opts.calendarName) lines.push(`X-WR-CALNAME:${escapeText(opts.calendarName)}`);
  if (opts.timeZone) lines.push(`X-WR-TIMEZONE:${opts.timeZone}`);
  for (const ev of events) lines.push(...eventLines(ev, opts, stamp));
  lines.push('END:VCALENDAR');
  return { ics: lines.map(foldLine).join('\r\n') + '\r\n', events, errors };
}
