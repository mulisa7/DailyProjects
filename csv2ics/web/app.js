import { convert, InputError } from '../src/csv2ics.js';

const $ = (id) => document.getElementById(id);
const els = {
  csv: $('csv'), file: $('file'), sample: $('sample'), tz: $('tz'), order: $('order'),
  duration: $('duration'), skip: $('skip'), status: $('status'), errors: $('errors'),
  download: $('download'), preview: $('preview'),
};

const SAMPLE = `Course,Day,Start Time,End Time,Room,Repeat,Repeat Until
Linear Algebra,2027-02-01,08:00,09:30,Room B12,weekly,2027-05-28
Intro to Databases,2027-02-02,11:00,12:30,Lab 3,weekly,2027-05-28
"Physics Practical, group A",2027-02-04,2:00 pm,5:00 pm,Physics lab 2,weekly,2027-05-28
Mid-term recess,2027-03-29,,,,,`;

let lastIcs = null;

try {
  const zones = Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : [];
  $('zones').innerHTML = zones.map((z) => `<option value="${z}">`).join('');
  els.tz.value = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
} catch {
  /* older browsers: free text only */
}

function when(ev) {
  const fmtDay = (d) => `${d.y}-${String(d.m).padStart(2, '0')}-${String(d.d).padStart(2, '0')}`;
  if (ev.allDay) {
    const last = new Date(Date.UTC(ev.endExclusive.y, ev.endExclusive.m - 1, ev.endExclusive.d - 1));
    const end = { y: last.getUTCFullYear(), m: last.getUTCMonth() + 1, d: last.getUTCDate() };
    const a = fmtDay(ev.start);
    const b = fmtDay(end);
    return a === b ? `${a} (all day)` : `${a} to ${b} (all day)`;
  }
  const tz = els.tz.value.trim();
  const opts = { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
  // Floating times were stored as if UTC, so display them in UTC to get the wall clock back.
  const f = new Intl.DateTimeFormat(undefined, { ...opts, timeZone: tz || 'UTC' });
  const t = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: tz || 'UTC' });
  return `${f.format(ev.startMs)} to ${t.format(ev.endMs)}`;
}

function text(s) {
  const span = document.createElement('span');
  span.textContent = s;
  return span.innerHTML;
}

function render() {
  lastIcs = null;
  els.download.disabled = true;
  els.errors.innerHTML = '';
  els.preview.hidden = true;
  els.status.className = '';
  const src = els.csv.value;
  if (!src.trim()) {
    els.status.textContent = 'Paste a CSV or choose a file to start.';
    return;
  }
  const dur = Number(els.duration.value);
  let result;
  try {
    result = convert(src, {
      timeZone: els.tz.value.trim() || undefined,
      dateOrder: els.order.value || undefined,
      defaultDuration: Number.isFinite(dur) && els.duration.value !== '' ? dur : undefined,
      skipInvalid: els.skip.checked,
    });
  } catch (e) {
    if (!(e instanceof InputError)) throw e;
    els.status.className = 'bad';
    els.status.textContent = e.message.charAt(0).toUpperCase() + e.message.slice(1) + '.';
    return;
  }
  els.errors.innerHTML = result.errors
    .map((er) => `<li>Line ${er.line}: ${text(er.message)}${els.skip.checked ? ' (skipped)' : ''}</li>`)
    .join('');
  const tbody = els.preview.querySelector('tbody');
  tbody.innerHTML = result.events
    .map((ev) => `<tr><td>${ev.line}</td><td>${text(ev.title)}</td><td>${text(when(ev))}</td>` +
      `<td>${text(ev.rrule ? ev.rrule.replace('FREQ=', '').toLowerCase() : '')}</td><td>${text(ev.location || '')}</td></tr>`)
    .join('');
  els.preview.hidden = result.events.length === 0;
  if (result.ics) {
    lastIcs = result.ics;
    els.download.disabled = false;
    els.status.className = 'ok';
    els.status.textContent = `${result.events.length} event(s) ready.`;
  } else {
    els.status.className = 'bad';
    els.status.textContent = result.errors.length
      ? `${result.errors.length} bad row(s). Fix them or tick "Skip bad rows".`
      : 'No valid events.';
  }
}

els.download.addEventListener('click', () => {
  if (!lastIcs) return;
  const url = URL.createObjectURL(new Blob([lastIcs], { type: 'text/calendar' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'calendar.ics';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

els.file.addEventListener('change', async () => {
  const f = els.file.files[0];
  if (!f) return;
  els.csv.value = await f.text();
  render();
});

els.sample.addEventListener('click', () => {
  els.csv.value = SAMPLE;
  render();
});

for (const el of [els.csv, els.tz, els.order, els.duration, els.skip]) {
  el.addEventListener('input', render);
  el.addEventListener('change', render);
}

render();
