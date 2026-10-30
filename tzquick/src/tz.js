// Core logic for tzquick: parse a phrase like "tomorrow 17:00 Pacific in UTC, London"
// and convert it between time zones. No DOM access here so it can run under node.

export const ALIASES = {
  utc: 'UTC', gmt: 'UTC', z: 'UTC',
  pt: 'America/Los_Angeles', pacific: 'America/Los_Angeles', pst: 'America/Los_Angeles', pdt: 'America/Los_Angeles',
  mt: 'America/Denver', mountain: 'America/Denver', mst: 'America/Denver', mdt: 'America/Denver',
  ct: 'America/Chicago', central: 'America/Chicago', cst: 'America/Chicago', cdt: 'America/Chicago',
  et: 'America/New_York', eastern: 'America/New_York', est: 'America/New_York', edt: 'America/New_York',
  bst: 'Europe/London', cet: 'Europe/Paris', cest: 'Europe/Paris', eet: 'Europe/Athens', eest: 'Europe/Athens',
  wat: 'Africa/Lagos', cat: 'Africa/Maputo', eat: 'Africa/Nairobi', sast: 'Africa/Johannesburg',
  ist: 'Asia/Kolkata', pkt: 'Asia/Karachi', jst: 'Asia/Tokyo', kst: 'Asia/Seoul', hkt: 'Asia/Hong_Kong',
  sgt: 'Asia/Singapore', aest: 'Australia/Sydney', aedt: 'Australia/Sydney', acst: 'Australia/Adelaide',
  awst: 'Australia/Perth', nzst: 'Pacific/Auckland', nzdt: 'Pacific/Auckland',
  london: 'Europe/London', paris: 'Europe/Paris', berlin: 'Europe/Berlin', madrid: 'Europe/Madrid',
  rome: 'Europe/Rome', amsterdam: 'Europe/Amsterdam', lisbon: 'Europe/Lisbon', moscow: 'Europe/Moscow',
  istanbul: 'Europe/Istanbul', dubai: 'Asia/Dubai', mumbai: 'Asia/Kolkata', delhi: 'Asia/Kolkata',
  kolkata: 'Asia/Kolkata', karachi: 'Asia/Karachi', dhaka: 'Asia/Dhaka', bangkok: 'Asia/Bangkok',
  jakarta: 'Asia/Jakarta', singapore: 'Asia/Singapore', manila: 'Asia/Manila', 'hong kong': 'Asia/Hong_Kong',
  shanghai: 'Asia/Shanghai', beijing: 'Asia/Shanghai', tokyo: 'Asia/Tokyo', seoul: 'Asia/Seoul',
  sydney: 'Australia/Sydney', melbourne: 'Australia/Melbourne', perth: 'Australia/Perth',
  auckland: 'Pacific/Auckland', honolulu: 'Pacific/Honolulu', anchorage: 'America/Anchorage',
  'los angeles': 'America/Los_Angeles', 'san francisco': 'America/Los_Angeles', seattle: 'America/Los_Angeles',
  denver: 'America/Denver', chicago: 'America/Chicago', 'new york': 'America/New_York', nyc: 'America/New_York',
  toronto: 'America/Toronto', vancouver: 'America/Vancouver', 'mexico city': 'America/Mexico_City',
  bogota: 'America/Bogota', lima: 'America/Lima', 'sao paulo': 'America/Sao_Paulo',
  'buenos aires': 'America/Argentina/Buenos_Aires', cairo: 'Africa/Cairo', lagos: 'Africa/Lagos',
  nairobi: 'Africa/Nairobi', johannesburg: 'Africa/Johannesburg', 'cape town': 'Africa/Johannesburg',
  durban: 'Africa/Johannesburg', pretoria: 'Africa/Johannesburg', accra: 'Africa/Accra',
  casablanca: 'Africa/Casablanca', 'addis ababa': 'Africa/Addis_Ababa',
};

// Abbreviations that mean different things in different places. We pick one and say so.
export const AMBIGUOUS = {
  ist: 'IST read as India Standard Time (Irish and Israel Standard Time also use it)',
  cst: 'CST read as US Central (China Standard Time also uses it)',
  bst: 'BST read as British Summer Time (Bangladesh Standard Time also uses it)',
  cat: 'CAT read as Central Africa Time',
};

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

export class ParseError extends Error {}

const formatterCache = new Map();
function dtf(zone) {
  let f = formatterCache.get(zone);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone, hourCycle: 'h23',
      year: 'numeric', month: 'numeric', day: 'numeric',
      hour: 'numeric', minute: 'numeric', second: 'numeric',
    });
    formatterCache.set(zone, f);
  }
  return f;
}

export function isValidZone(zone) {
  try { dtf(zone); return true; } catch { return false; }
}

// Wall-clock fields of an instant (ms since epoch) in a zone.
export function wallFields(ms, zone) {
  const out = {};
  for (const p of dtf(zone).formatToParts(new Date(ms))) {
    if (p.type !== 'literal') out[p.type] = Number(p.value);
  }
  return out;
}

// Offset of the zone from UTC at an instant, in minutes.
export function offsetMinutes(ms, zone) {
  const w = wallFields(ms, zone);
  const asUtc = Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second);
  return Math.round((asUtc - Math.floor(ms / 1000) * 1000) / 60000);
}

// Turn a wall-clock time in a zone into an instant. Reports DST gaps and repeats.
export function zonedToInstant({ year, month, day, hour, minute }, zone) {
  const naive = Date.UTC(year, month - 1, day, hour, minute);
  const o1 = offsetMinutes(naive, zone);
  let ms = naive - o1 * 60000;
  const o2 = offsetMinutes(ms, zone);
  if (o2 !== o1) ms = naive - o2 * 60000;
  const back = wallFields(ms, zone);
  const matches = back.hour === hour && back.minute === minute && back.day === day;
  if (!matches) {
    // The wall time does not exist (clock jumped forward). Move to the first valid minute after it.
    const shifted = naive - Math.min(o1, o2) * 60000;
    return { ms: shifted, note: 'that local time does not exist (clocks skip forward), shown as the moment after the jump' };
  }
  // Repeated hour: the other offset also maps to the same wall time.
  for (const alt of [ms - 3600000, ms + 3600000]) {
    const w = wallFields(alt, zone);
    if (w.hour === hour && w.minute === minute && w.day === day && offsetMinutes(alt, zone) !== offsetMinutes(ms, zone)) {
      return { ms: Math.min(ms, alt), note: 'that local time happens twice (clocks go back), using the first one' };
    }
  }
  return { ms, note: null };
}

export function resolveZone(text) {
  const raw = text.trim();
  if (!raw) throw new ParseError('empty time zone');
  const key = raw.toLowerCase().replace(/\s+/g, ' ');
  if (ALIASES[key]) return { zone: ALIASES[key], label: raw, note: AMBIGUOUS[key] || null };
  const m = key.match(/^(?:utc|gmt)\s*([+-])(\d{1,2})(?::?(\d{2}))?$/);
  if (m) {
    const hours = Number(m[2]);
    const mins = Number(m[3] || 0);
    if (hours > 14 || mins > 59) throw new ParseError(`offset out of range: ${raw}`);
    return { fixed: (m[1] === '-' ? -1 : 1) * (hours * 60 + mins), zone: null, label: raw, note: null };
  }
  // IANA names are case-insensitive for us: Africa/Johannesburg, africa/johannesburg.
  const iana = raw.split('/').map((part) => part.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join('_')).join('/');
  for (const cand of [iana, raw]) {
    if (cand.includes('/') && isValidZone(cand)) {
      const canonical = dtf(cand).resolvedOptions().timeZone;
      return { zone: canonical, label: canonical, note: null };
    }
  }
  throw new ParseError(`unknown time zone: "${raw}". Try a city (London), an abbreviation (PT) or an IANA name (Europe/London).`);
}

function parseClock(text) {
  const t = text.trim().toLowerCase();
  if (t === 'noon') return { hour: 12, minute: 0 };
  if (t === 'midnight') return { hour: 0, minute: 0 };
  let m = t.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)$/);
  if (m) {
    let h = Number(m[1]);
    const min = Number(m[2] || 0);
    if (h < 1 || h > 12 || min > 59) throw new ParseError(`not a valid time: "${text}"`);
    const pm = m[3].startsWith('p');
    if (h === 12) h = pm ? 12 : 0; else if (pm) h += 12;
    return { hour: h, minute: min };
  }
  m = t.match(/^(\d{1,2}):(\d{2})$/) || t.match(/^(\d{2})(\d{2})$/);
  if (m) {
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) throw new ParseError(`not a valid time: "${text}"`);
    return { hour: h, minute: min };
  }
  m = t.match(/^(\d{1,2})h?$/);
  if (m && Number(m[1]) <= 23 && /h$/.test(t)) return { hour: Number(m[1]), minute: 0 };
  throw new ParseError(`not a valid time: "${text}"`);
}

function addDays({ year, month, day }, n) {
  const d = new Date(Date.UTC(year, month - 1, day + n));
  return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
}

function validDate(y, m, d) {
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

// Interpret a date word relative to "today" in the source zone.
function parseDateWord(word, today) {
  const w = word.toLowerCase().replace(/,/g, '').trim();
  if (w === 'today') return today;
  if (w === 'tomorrow') return addDays(today, 1);
  if (w === 'yesterday') return addDays(today, -1);
  let m = w.match(/^(?:next\s+)?(\w+day)$/);
  if (m && WEEKDAYS.includes(m[1])) {
    const target = WEEKDAYS.indexOf(m[1]);
    const cur = new Date(Date.UTC(today.year, today.month - 1, today.day)).getUTCDay();
    let diff = (target - cur + 7) % 7;
    if (diff === 0) diff = 7;
    return addDays(today, diff);
  }
  m = w.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) {
    const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
    if (!validDate(y, mo, d)) throw new ParseError(`not a real date: "${word}"`);
    return { year: y, month: mo, day: d };
  }
  m = w.match(/^(\d{1,2})\s+([a-z]{3})[a-z]*$/) || w.match(/^([a-z]{3})[a-z]*\s+(\d{1,2})$/);
  if (m) {
    const [dayText, monText] = /^\d/.test(m[1]) ? [m[1], m[2]] : [m[2], m[1]];
    const mo = MONTHS.indexOf(monText) + 1;
    if (mo > 0) {
      const d = Number(dayText);
      if (!validDate(today.year, mo, d)) throw new ParseError(`not a real date: "${word}"`);
      return { year: today.year, month: mo, day: d };
    }
  }
  throw new ParseError(`could not understand the date: "${word}"`);
}

const DATE_RE = /\b(today|tomorrow|yesterday|(?:next\s+)?(?:sun|mon|tues|wednes|thurs|fri|satur)day|\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?!\d|:|\s*(?:am|pm)))\b/i;
const TIME_RE = /\b(noon|midnight|\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}h|\d{4})(?=\s|$|,)/i;

// Split "17:00 pacific" into clock and the leftover zone text.
function splitInput(input) {
  const parts = input.split(/\s+(?:in|to|into)\s+|\s*->\s*|\s*=>\s*/i);
  if (parts.length > 2) throw new ParseError('use one "in" or "to": e.g. "5pm London in New York, Tokyo"');
  return parts;
}

/**
 * Parse and convert. Options: now (ms, defaults to Date.now()), localZone.
 * Returns { source, instant, results[], notes[] }.
 */
export function convert(input, options = {}) {
  const now = options.now ?? Date.now();
  const localZone = options.localZone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  if (typeof input !== 'string' || !input.trim()) throw new ParseError('type something like "5pm London in New York, Tokyo"');
  const text = input.trim();
  if (text.length > 200) throw new ParseError('input is too long');

  const [head, tail] = splitInput(text);
  const notes = [];

  // "now" on its own, optionally followed by a zone.
  let rest = head;
  let dateWord = null;
  const dm = rest.match(DATE_RE);
  if (dm) {
    dateWord = dm[0];
    rest = (rest.slice(0, dm.index) + ' ' + rest.slice(dm.index + dm[0].length)).replace(/\s+/g, ' ').trim();
  }

  let clock = null;
  let isNow = false;
  const tm = rest.match(TIME_RE);
  if (tm) {
    clock = parseClock(tm[0]);
    rest = (rest.slice(0, tm.index) + ' ' + rest.slice(tm.index + tm[0].length)).replace(/\s+/g, ' ').trim();
  } else if (/^now\b/i.test(rest)) {
    isNow = true;
    rest = rest.replace(/^now\b/i, '').trim();
  } else {
    throw new ParseError(`no time found in "${head}". Examples: 17:00, 5pm, 5:30 pm, noon.`);
  }
  if (isNow && dateWord) throw new ParseError('"now" cannot be combined with a date');

  const sourceText = rest.replace(/^(?:at|from|@)\s+/i, '').replace(/\s+at$/i, '').trim();
  const source = sourceText ? resolveZone(sourceText) : { zone: localZone, label: 'your local time', note: null };

  let instant;
  if (isNow) {
    instant = now;
  } else {
    let today;
    if (source.fixed !== undefined) {
      const w = wallFields(now + source.fixed * 60000, 'UTC');
      today = { year: w.year, month: w.month, day: w.day };
    } else {
      const w = wallFields(now, source.zone);
      today = { year: w.year, month: w.month, day: w.day };
    }
    const date = dateWord ? parseDateWord(dateWord, today) : today;
    const wall = { ...date, ...clock };
    if (source.fixed !== undefined) {
      instant = Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute) - source.fixed * 60000;
    } else {
      const z = zonedToInstant(wall, source.zone);
      instant = z.ms;
      if (z.note) notes.push(z.note);
    }
  }
  if (source.note) notes.push(source.note);

  const targetTexts = tail === undefined
    ? []
    : tail.split(/\s*(?:,|;|\band\b|\/\/)\s*/i).map((s) => s.trim()).filter(Boolean);
  if (tail !== undefined && targetTexts.length === 0) throw new ParseError('nothing after "in": name at least one target zone');
  if (targetTexts.length > 12) throw new ParseError('at most 12 target zones');

  let targets = targetTexts.map(resolveZone);
  if (targets.length === 0) {
    targets = [{ zone: 'UTC', label: 'UTC', note: null }];
    if (source.zone !== localZone && localZone !== 'UTC') targets.unshift({ zone: localZone, label: 'your local time', note: null });
  }

  const srcWall = source.fixed !== undefined
    ? wallFields(instant + source.fixed * 60000, 'UTC')
    : wallFields(instant, source.zone);
  const srcDay = Date.UTC(srcWall.year, srcWall.month - 1, srcWall.day);

  const results = targets.map((t) => {
    if (t.note && !notes.includes(t.note)) notes.push(t.note);
    const off = t.fixed !== undefined ? t.fixed : offsetMinutes(instant, t.zone);
    const w = t.fixed !== undefined ? wallFields(instant + t.fixed * 60000, 'UTC') : wallFields(instant, t.zone);
    const dayDiff = Math.round((Date.UTC(w.year, w.month - 1, w.day) - srcDay) / 86400000);
    return {
      label: t.label,
      zone: t.zone || `UTC${formatOffset(off)}`,
      year: w.year, month: w.month, day: w.day, hour: w.hour, minute: w.minute,
      offset: formatOffset(off),
      dayDiff,
      text: `${pad(w.hour)}:${pad(w.minute)}`,
      date: `${w.year}-${pad(w.month)}-${pad(w.day)}`,
    };
  });

  return {
    instant,
    iso: new Date(instant).toISOString(),
    source: {
      label: source.label,
      zone: source.zone || `UTC${formatOffset(source.fixed)}`,
      text: `${pad(srcWall.hour)}:${pad(srcWall.minute)}`,
      date: `${srcWall.year}-${pad(srcWall.month)}-${pad(srcWall.day)}`,
      offset: formatOffset(source.fixed !== undefined ? source.fixed : offsetMinutes(instant, source.zone)),
    },
    results,
    notes,
  };
}

const pad = (n) => String(n).padStart(2, '0');

export function formatOffset(minutes) {
  const sign = minutes < 0 ? '-' : '+';
  const a = Math.abs(minutes);
  return `${sign}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
}
