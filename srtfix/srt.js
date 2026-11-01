'use strict';
// Pure SRT logic: parse, shift, stretch, validate, format.

const TIME_RE = /^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})$/;

function parseTime(s) {
  const m = TIME_RE.exec(String(s).trim());
  if (!m) throw new Error(`bad timestamp: "${s}"`);
  const [, h, mi, se, ms] = m;
  if (Number(mi) > 59 || Number(se) > 59) throw new Error(`bad timestamp: "${s}"`);
  return ((Number(h) * 60 + Number(mi)) * 60 + Number(se)) * 1000 + Number(ms.padEnd(3, '0'));
}

function formatTime(ms) {
  ms = Math.round(ms);
  if (ms < 0) ms = 0;
  const h = Math.floor(ms / 3600000);
  const mi = Math.floor(ms / 60000) % 60;
  const se = Math.floor(ms / 1000) % 60;
  const r = ms % 1000;
  const p = (n, w) => String(n).padStart(w, '0');
  return `${p(h, 2)}:${p(mi, 2)}:${p(se, 2)},${p(r, 3)}`;
}

// Returns { cues, warnings }. Malformed blocks are skipped with a warning.
function parse(text) {
  const warnings = [];
  const cues = [];
  const clean = String(text).replace(/^﻿/, '').replace(/\r\n?/g, '\n').trim();
  if (!clean) return { cues, warnings };
  const blocks = clean.split(/\n{2,}/);
  blocks.forEach((block, i) => {
    const lines = block.split('\n');
    let idx = 0;
    if (/^\d+$/.test(lines[0].trim())) idx = 1;
    const timing = lines[idx];
    const m = timing && /^\s*(\S+)\s*-->\s*(\S+)/.exec(timing);
    if (!m) { warnings.push(`block ${i + 1}: no timing line, skipped`); return; }
    try {
      const start = parseTime(m[1]);
      const end = parseTime(m[2]);
      cues.push({ start, end, text: lines.slice(idx + 1).join('\n') });
    } catch (e) {
      warnings.push(`block ${i + 1}: ${e.message}, skipped`);
    }
  });
  return { cues, warnings };
}

function format(cues) {
  return cues
    .map((c, i) => `${i + 1}\n${formatTime(c.start)} --> ${formatTime(c.end)}\n${c.text}`)
    .join('\n\n') + (cues.length ? '\n' : '');
}

// Shift all cues by offsetMs (may be negative). Cues that end up entirely
// before zero are dropped; cues straddling zero are clamped to start at 0.
function shift(cues, offsetMs) {
  if (!Number.isFinite(offsetMs)) throw new Error('offset must be a number');
  const out = [];
  for (const c of cues) {
    const s = c.start + offsetMs, e = c.end + offsetMs;
    if (e <= 0) continue;
    out.push({ ...c, start: Math.max(0, s), end: e });
  }
  return out;
}

// Multiply all times by factor (e.g. 25/23.976 to fix a framerate mismatch).
function stretch(cues, factor) {
  if (!Number.isFinite(factor) || factor <= 0) throw new Error('factor must be a positive number');
  return cues.map((c) => ({ ...c, start: c.start * factor, end: c.end * factor }));
}

// Linear sync: map two known points (oldA->newA, oldB->newB) onto the whole file.
function sync(cues, oldA, newA, oldB, newB) {
  if (oldA === oldB) throw new Error('the two reference times must differ');
  const factor = (newB - newA) / (oldB - oldA);
  if (!(factor > 0)) throw new Error('reference points give a non-positive scale');
  const offset = newA - oldA * factor;
  return cues.map((c) => ({ ...c, start: Math.max(0, c.start * factor + offset), end: c.end * factor + offset }))
    .filter((c) => c.end > 0);
}

function validate(cues) {
  const problems = [];
  cues.forEach((c, i) => {
    const n = i + 1;
    if (c.end <= c.start) problems.push(`cue ${n}: end is not after start (${formatTime(c.start)} --> ${formatTime(c.end)})`);
    if (!c.text.trim()) problems.push(`cue ${n}: empty text`);
    if (i > 0) {
      const p = cues[i - 1];
      if (c.start < p.start) problems.push(`cue ${n}: starts before cue ${n - 1}`);
      else if (c.start < p.end) problems.push(`cue ${n}: overlaps cue ${n - 1} by ${p.end - c.start} ms`);
    }
  });
  return problems;
}

function sortCues(cues) {
  return cues.map((c, i) => [c, i]).sort((a, b) => a[0].start - b[0].start || a[1] - b[1]).map((x) => x[0]);
}

module.exports = { parseTime, formatTime, parse, format, shift, stretch, sync, validate, sortCues };
