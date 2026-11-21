'use strict';
// Pure logic for gradeneed: parsing a course spec and computing grades.

class SpecError extends Error {}

const NUM = /^-?\d+(\.\d+)?$/;

function parseScore(tok, lineNo) {
  const t = tok.trim();
  let m = t.match(/^(-?\d+(?:\.\d+)?)\s*\/\s*(-?\d+(?:\.\d+)?)$/);
  if (m) {
    const earned = Number(m[1]), possible = Number(m[2]);
    if (possible <= 0) throw new SpecError(`line ${lineNo}: possible points must be above 0 in "${t}"`);
    if (earned < 0) throw new SpecError(`line ${lineNo}: negative score "${t}"`);
    return { earned, possible };
  }
  m = t.match(/^(-?\d+(?:\.\d+)?)%$/);
  if (m) {
    if (Number(m[1]) < 0) throw new SpecError(`line ${lineNo}: negative score "${t}"`);
    return { earned: Number(m[1]), possible: 100 };
  }
  throw new SpecError(`line ${lineNo}: cannot read score "${t}" (use 8/10 or 85%)`);
}

function parseSpec(text) {
  if (typeof text !== 'string') throw new SpecError('spec must be text');
  const cats = [];
  const targets = [];
  const seen = new Set();
  text.split(/\r?\n/).forEach((raw, i) => {
    const lineNo = i + 1;
    const line = raw.replace(/#.*$/, '').trim();
    if (!line) return;
    const tm = line.match(/^target\s*:?\s*(.+)$/i);
    if (tm) {
      for (const part of tm[1].split(/[,\s]+/).filter(Boolean)) {
        const v = part.replace(/%$/, '');
        if (!NUM.test(v) || Number(v) < 0 || Number(v) > 100)
          throw new SpecError(`line ${lineNo}: bad target "${part}" (0-100)`);
        targets.push(Number(v));
      }
      return;
    }
    const m = line.match(/^(.+?)\s+(\d+(?:\.\d+)?)%((?:\s+drop=\d+)?)\s*:\s*(.*)$/);
    if (!m) throw new SpecError(`line ${lineNo}: expected "Name 20%[ drop=N]: scores" but got "${line}"`);
    const name = m[1].trim();
    if (seen.has(name.toLowerCase())) throw new SpecError(`line ${lineNo}: duplicate category "${name}"`);
    seen.add(name.toLowerCase());
    const weight = Number(m[2]);
    if (weight <= 0) throw new SpecError(`line ${lineNo}: weight of "${name}" must be above 0`);
    const drop = m[3] ? Number(m[3].trim().slice(5)) : 0;
    const scores = m[4].trim()
      ? m[4].split(',').map(s => parseScore(s, lineNo))
      : [];
    cats.push({ name, weight, drop, scores });
  });
  if (cats.length === 0) throw new SpecError('no categories found');
  return { categories: cats, targets: targets.length ? targets : [90, 80, 70, 60] };
}

function categoryAverage(cat) {
  if (cat.scores.length === 0) return null;
  let scores = cat.scores.slice();
  const drop = Math.min(cat.drop, scores.length - 1);
  if (drop > 0) {
    scores.sort((a, b) => a.earned / a.possible - b.earned / b.possible);
    scores = scores.slice(drop);
  }
  const e = scores.reduce((s, x) => s + x.earned, 0);
  const p = scores.reduce((s, x) => s + x.possible, 0);
  return (e / p) * 100;
}

function analyze(spec) {
  const total = spec.categories.reduce((s, c) => s + c.weight, 0);
  if (Math.abs(total - 100) > 0.01)
    throw new SpecError(`weights add up to ${round(total)}%, not 100%`);
  const rows = spec.categories.map(c => ({
    name: c.name, weight: c.weight, count: c.scores.length, average: categoryAverage(c),
  }));
  const graded = rows.filter(r => r.average !== null);
  const pending = rows.filter(r => r.average === null);
  const gradedWeight = graded.reduce((s, r) => s + r.weight, 0);
  const points = graded.reduce((s, r) => s + (r.weight * r.average) / 100, 0);
  const pendingWeight = 100 - gradedWeight;
  const result = {
    rows,
    gradedWeight,
    pendingWeight,
    pendingNames: pending.map(r => r.name),
    currentGrade: gradedWeight > 0 ? (points / gradedWeight) * 100 : null,
    pointsSoFar: points,
    targets: [],
  };
  for (const t of [...new Set(spec.targets)].sort((a, b) => b - a)) {
    if (pendingWeight <= 0.0001) {
      result.targets.push({ target: t, status: points + 1e-9 >= t ? 'reached' : 'missed', needed: null });
      continue;
    }
    const needed = ((t - points) / pendingWeight) * 100;
    let status = 'possible';
    if (needed <= 0) status = 'secured';
    else if (needed > 100) status = 'out of reach';
    result.targets.push({ target: t, status, needed });
  }
  return result;
}

function round(n) { return Math.round(n * 100) / 100; }

function format(result) {
  const out = [];
  out.push('Category'.padEnd(20) + 'Weight'.padStart(8) + 'Scores'.padStart(8) + 'Average'.padStart(10));
  for (const r of result.rows)
    out.push(r.name.slice(0, 19).padEnd(20) + (round(r.weight) + '%').padStart(8) +
      String(r.count).padStart(8) + (r.average === null ? 'pending' : round(r.average) + '%').padStart(10));
  out.push('');
  if (result.currentGrade === null) out.push('No scores entered yet, so there is no current grade.');
  else out.push(`Current grade (graded work only): ${round(result.currentGrade)}% over ${round(result.gradedWeight)}% of the course`);
  out.push('');
  for (const t of result.targets) {
    let s;
    if (t.status === 'reached') s = 'reached';
    else if (t.status === 'missed') s = 'not reached, nothing left to earn it';
    else if (t.status === 'secured') s = 'already secured';
    else if (t.status === 'out of reach') s = `out of reach (would need ${round(t.needed)}% on ${result.pendingNames.join(', ')})`;
    else s = `need ${round(t.needed)}% on ${result.pendingNames.join(', ')}`;
    out.push(`To finish with ${round(t.target)}%: ${s}`);
  }
  return out.join('\n');
}

const api = { parseSpec, analyze, format, categoryAverage, SpecError };
if (typeof module !== 'undefined') module.exports = api;
if (typeof window !== 'undefined') window.GradeNeed = api;
