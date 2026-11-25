'use strict';
// Pure text analysis, no DOM or Node APIs, so it runs in the browser and in tests.

const ABBREV = new Set(['mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'st', 'vs', 'etc', 'e.g', 'i.e', 'no', 'fig', 'inc', 'ltd']);
const FILLERS = ['very', 'really', 'just', 'quite', 'actually', 'basically', 'simply', 'somewhat', 'rather', 'literally', 'various', 'several'];
const IRREGULAR_PARTICIPLES = new Set(['been', 'done', 'given', 'taken', 'written', 'made', 'seen', 'known', 'shown', 'found', 'built', 'held', 'sent', 'kept', 'left', 'lost', 'brought', 'chosen', 'broken', 'driven', 'gone', 'thrown', 'eaten', 'stolen', 'hidden', 'forgotten', 'begun', 'spoken', 'told', 'sold', 'paid']);
const BE_FORMS = new Set(['is', 'are', 'was', 'were', 'be', 'been', 'being', 'am']);

function stripMarkdown(text) {
  return String(text)
    .replace(/\r\n?/g, '\n')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/~~~[\s\S]*?~~~/g, ' ')
    .replace(/`[^`\n]*`/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/<[^>\n]+>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/[*_]{1,3}([^*_\n]+)[*_]{1,3}/g, '$1');
}

function countSyllables(word) {
  let w = word.toLowerCase().replace(/[^a-z]/g, '');
  if (!w) return 0;
  if (w.length <= 3) return 1;
  w = w.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, '').replace(/^y/, '');
  const m = w.match(/[aeiouy]{1,2}/g);
  return Math.max(1, m ? m.length : 1);
}

function wordsOf(sentence) {
  return sentence.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g) || [];
}

function splitSentences(text) {
  const out = [];
  const paragraphs = text.split(/\n\s*\n/);
  for (const para of paragraphs) {
    const flat = para.replace(/\s+/g, ' ').trim();
    if (!flat) continue;
    let start = 0;
    const re = /[.!?]+["')\]]*\s+(?=[A-Z0-9"'(\[])|[.!?]+["')\]]*$/g;
    let m;
    while ((m = re.exec(flat)) !== null) {
      const end = m.index + m[0].length;
      const piece = flat.slice(start, end).trim();
      const before = flat.slice(start, m.index).split(' ').pop().toLowerCase().replace(/^[("']+/, '');
      const isAbbrev = m[0].startsWith('.') && !/^[.]{2,}/.test(m[0]) && (ABBREV.has(before) || /^[a-z]$/i.test(before));
      if (isAbbrev && end < flat.length) continue;
      if (piece) out.push(piece);
      start = end;
    }
    const rest = flat.slice(start).trim();
    if (rest) out.push(rest);
  }
  return out;
}

function findPassive(words) {
  const hits = [];
  for (let i = 0; i < words.length - 1; i++) {
    if (!BE_FORMS.has(words[i].toLowerCase())) continue;
    let j = i + 1;
    if (/^(not|being|also|then|often|always|never|already)$/i.test(words[j]) && j + 1 < words.length) j++;
    const nxt = words[j].toLowerCase();
    if (/^[a-z]{3,}ed$/.test(nxt) && !/^(need|speed|feed|seed|bleed|breed|proceed|exceed|succeed|indeed)ed?$/.test(nxt) || IRREGULAR_PARTICIPLES.has(nxt)) {
      hits.push(words.slice(i, j + 1).join(' '));
    }
  }
  return hits;
}

function analyze(input, opts = {}) {
  if (typeof input !== 'string') throw new TypeError('text must be a string');
  const maxWords = opts.maxSentenceWords ?? 25;
  const text = opts.markdown ? stripMarkdown(input) : input;
  const sentences = splitSentences(text);
  const issues = [];
  let wordCount = 0, syllables = 0, longWords = 0;
  const lowered = [];

  sentences.forEach((s, idx) => {
    const ws = wordsOf(s);
    if (ws.length === 0) return;
    wordCount += ws.length;
    for (const w of ws) {
      const sy = countSyllables(w);
      syllables += sy;
      if (sy >= 3) longWords++;
      lowered.push(w.toLowerCase());
    }
    const n = idx + 1;
    if (ws.length > maxWords) issues.push({ type: 'long-sentence', sentence: n, detail: `${ws.length} words`, text: s });
    for (const p of findPassive(ws)) issues.push({ type: 'passive', sentence: n, detail: p, text: s });
    for (const w of ws) {
      if (FILLERS.includes(w.toLowerCase())) issues.push({ type: 'filler', sentence: n, detail: w.toLowerCase(), text: s });
    }
    for (let i = 1; i < ws.length; i++) {
      if (ws[i].toLowerCase() === ws[i - 1].toLowerCase() && /[a-z]/i.test(ws[i])) {
        issues.push({ type: 'repeated-word', sentence: n, detail: ws[i].toLowerCase(), text: s });
      }
    }
  });

  const sentenceCount = sentences.filter((s) => wordsOf(s).length > 0).length;
  const stats = { words: wordCount, sentences: sentenceCount, syllables, longWords };
  if (wordCount === 0) {
    return { empty: true, stats, avgSentenceLength: 0, readingEase: null, gradeLevel: null, label: 'no text', issues: [] };
  }
  const wps = wordCount / sentenceCount;
  const spw = syllables / wordCount;
  const ease = 206.835 - 1.015 * wps - 84.6 * spw;
  const grade = 0.39 * wps + 11.8 * spw - 15.59;
  return {
    empty: false,
    stats,
    avgSentenceLength: round(wps),
    readingEase: round(ease),
    gradeLevel: round(Math.max(0, grade)),
    label: easeLabel(ease),
    issues,
  };
}

function easeLabel(e) {
  if (e >= 90) return 'very easy';
  if (e >= 70) return 'easy';
  if (e >= 60) return 'plain English';
  if (e >= 50) return 'fairly difficult';
  if (e >= 30) return 'difficult';
  return 'very difficult';
}

function round(n) { return Math.round(n * 10) / 10; }

const api = { analyze, countSyllables, splitSentences, stripMarkdown, findPassive };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else if (typeof globalThis !== 'undefined') Object.assign(globalThis, api);
