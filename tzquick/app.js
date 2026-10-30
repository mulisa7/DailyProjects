import { convert, ParseError } from './src/tz.js';

const $ = (id) => document.getElementById(id);
const input = $('q');
let lastText = '';

function dayLabel(diff) {
  if (diff === 0) return '';
  if (diff === 1) return 'next day';
  if (diff === -1) return 'previous day';
  return `${diff > 0 ? '+' : ''}${diff} days`;
}

function render(res) {
  $('source').textContent = `${res.source.text} on ${res.source.date} in ${res.source.label} (UTC${res.source.offset})`;
  const list = $('results');
  list.replaceChildren();
  const lines = [$('source').textContent];
  for (const r of res.results) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = r.label;
    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = r.text;
    const meta = document.createElement('span');
    meta.className = 'meta';
    const day = dayLabel(r.dayDiff);
    meta.textContent = `${r.date}${day ? ', ' + day : ''} · UTC${r.offset}`;
    li.append(name, time, meta);
    list.append(li);
    lines.push(`${r.label}: ${r.text} on ${r.date} (UTC${r.offset})`);
  }
  const notes = $('notes');
  notes.replaceChildren();
  for (const n of res.notes) {
    const li = document.createElement('li');
    li.textContent = n;
    notes.append(li);
  }
  lastText = lines.join('\n');
  $('out').hidden = false;
  $('empty').hidden = true;
  $('error').hidden = true;
}

function update() {
  const text = input.value;
  try {
    const url = new URL(location.href);
    if (text.trim()) url.searchParams.set('q', text); else url.searchParams.delete('q');
    history.replaceState(null, '', url);
  } catch { /* history can be unavailable in some embedded contexts */ }

  if (!text.trim()) {
    $('out').hidden = true;
    $('error').hidden = true;
    $('empty').hidden = false;
    return;
  }
  try {
    render(convert(text));
  } catch (e) {
    if (!(e instanceof ParseError)) throw e;
    $('out').hidden = true;
    $('empty').hidden = true;
    $('error').hidden = false;
    $('error').textContent = e.message;
  }
}

input.addEventListener('input', update);
$('form').addEventListener('submit', (e) => { e.preventDefault(); update(); });
$('examples').addEventListener('click', (e) => {
  if (e.target.tagName !== 'BUTTON') return;
  input.value = e.target.textContent;
  update();
});
$('copy').addEventListener('click', async () => {
  const btn = $('copy');
  try {
    await navigator.clipboard.writeText(lastText);
    btn.textContent = 'Copied';
  } catch {
    btn.textContent = 'Copy failed';
  }
  setTimeout(() => { btn.textContent = 'Copy as text'; }, 1500);
});

const initial = new URLSearchParams(location.search).get('q');
if (initial) input.value = initial;
update();
