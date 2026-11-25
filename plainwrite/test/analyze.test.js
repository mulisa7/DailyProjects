'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { analyze, countSyllables, splitSentences, stripMarkdown, findPassive } = require('../analyze');
const { run, parseArgs } = require('../cli');

test('syllable counts for common words', () => {
  assert.strictEqual(countSyllables('cat'), 1);
  assert.strictEqual(countSyllables('table'), 2);
  assert.strictEqual(countSyllables('banana'), 3);
  assert.strictEqual(countSyllables('walked'), 1);
  assert.strictEqual(countSyllables('123'), 0);
  assert.strictEqual(countSyllables(''), 0);
});

test('sentence splitting handles abbreviations and paragraphs', () => {
  assert.deepStrictEqual(splitSentences('Dr. Smith came. He left!'), ['Dr. Smith came.', 'He left!']);
  assert.strictEqual(splitSentences('One\n\nTwo').length, 2);
  assert.strictEqual(splitSentences('No end punctuation').length, 1);
  assert.deepStrictEqual(splitSentences('   \n\n  '), []);
});

test('empty and whitespace input gives empty result', () => {
  for (const t of ['', '   ', '\n\n', '... !!!']) {
    const r = analyze(t);
    assert.strictEqual(r.empty, true);
    assert.strictEqual(r.readingEase, null);
  }
});

test('non-string input throws', () => {
  assert.throws(() => analyze(null), TypeError);
  assert.throws(() => analyze(5), TypeError);
});

test('simple text scores easier than dense text', () => {
  const easy = analyze('The cat sat. The dog ran. We had fun.');
  const hard = analyze('Notwithstanding considerable organizational complexity, administrators systematically institutionalized comprehensive bureaucratic methodologies.');
  assert.ok(easy.readingEase > 90);
  assert.ok(hard.gradeLevel > easy.gradeLevel + 10);
  assert.strictEqual(easy.stats.sentences, 3);
  assert.strictEqual(easy.stats.words, 9);
});

test('flags long sentences using the limit', () => {
  const s = Array(30).fill('word').join(' ') + '.';
  assert.ok(analyze(s).issues.some((i) => i.type === 'long-sentence'));
  assert.ok(!analyze(s, { maxSentenceWords: 40 }).issues.some((i) => i.type === 'long-sentence'));
});

test('flags passive voice but not look-alikes', () => {
  assert.deepStrictEqual(findPassive(['The', 'ball', 'was', 'thrown', 'away']), ['was thrown']);
  assert.deepStrictEqual(findPassive(['It', 'was', 'not', 'finished']), ['was not finished']);
  assert.deepStrictEqual(findPassive(['We', 'need', 'speed']), []);
  assert.deepStrictEqual(findPassive(['It', 'is', 'red']), []);
  assert.deepStrictEqual(findPassive(['to', 'be']), []);
});

test('flags fillers and repeated words', () => {
  const r = analyze('This is really very good. It was the the best.');
  const types = r.issues.map((i) => i.type + ':' + i.detail);
  assert.ok(types.includes('filler:really'));
  assert.ok(types.includes('filler:very'));
  assert.ok(types.includes('repeated-word:the'));
});

test('clean text has no issues', () => {
  assert.deepStrictEqual(analyze('We ship on Friday. Call me if it breaks.').issues, []);
});

test('markdown stripping removes code, links, urls and markers', () => {
  const md = '# Title\n\n```js\nvery very very();\n```\n\nSee [the docs](http://x.io/a) and `inline code`. **Bold** text.\n\n- item one\n';
  const out = stripMarkdown(md);
  assert.ok(!out.includes('very'));
  assert.ok(!out.includes('http'));
  assert.ok(out.includes('the docs'));
  assert.ok(!out.includes('**'));
  assert.strictEqual(analyze('```\ncode only\n```', { markdown: true }).empty, true);
});

test('unicode and odd characters do not crash', () => {
  const r = analyze('Café naïve résumé. 日本語のテキスト。 😀😀😀');
  assert.ok(r.stats.words >= 3);
});

test('large input finishes quickly', () => {
  const t0 = Date.now();
  analyze('The quick brown fox jumps over the lazy dog. '.repeat(20000));
  assert.ok(Date.now() - t0 < 5000);
});

function runCli(args, stdin = null, files = {}) {
  const out = [], err = [];
  const code = run(args, stdin, (s) => out.push(s), (s) => err.push(s), (p) => {
    if (p in files) return files[p];
    const e = new Error('nope'); e.code = 'ENOENT'; throw e;
  });
  return { code, out: out.join('\n'), err: err.join('\n') };
}

test('cli reads stdin and prints a report', () => {
  const r = runCli([], 'The cat sat. The dog ran.');
  assert.strictEqual(r.code, 0);
  assert.match(r.out, /Words: 6/);
});

test('cli reads a file, json output parses', () => {
  const r = runCli(['--json', 'a.txt'], null, { 'a.txt': 'Hello there. Bye now.' });
  assert.strictEqual(JSON.parse(r.out).stats.sentences, 2);
});

test('cli reports missing file with exit 2', () => {
  const r = runCli(['missing.txt']);
  assert.strictEqual(r.code, 2);
  assert.match(r.err, /cannot read missing.txt: ENOENT/);
});

test('cli empty input is not an error', () => {
  const r = runCli([], '');
  assert.strictEqual(r.code, 0);
  assert.match(r.out, /No text/);
});

test('cli no input at all exits 2', () => {
  assert.strictEqual(runCli([]).code, 2);
});

test('cli rejects bad options', () => {
  assert.strictEqual(runCli(['--bogus']).code, 2);
  assert.strictEqual(runCli(['--max-grade']).code, 2);
  assert.strictEqual(runCli(['--max-grade', 'abc'], 'x').code, 2);
  assert.strictEqual(runCli(['--max-grade', '-3'], 'x').code, 2);
  assert.strictEqual(runCli(['a', 'b']).code, 2);
  assert.throws(() => parseArgs(['--max-sentence', '0']));
});

test('cli --max-grade gates exit code', () => {
  const dense = 'Notwithstanding considerable organizational complexity, administrators systematically institutionalized comprehensive methodologies.';
  assert.strictEqual(runCli(['--max-grade', '8'], dense).code, 1);
  assert.strictEqual(runCli(['--max-grade', '100'], dense).code, 0);
  assert.strictEqual(runCli(['--max-grade', '8'], '').code, 0);
});

test('cli rejects binary input and strips BOM', () => {
  assert.strictEqual(runCli([], 'a\u0000b').code, 2);
  assert.match(runCli([], '﻿Hello there.').out, /Words: 2/);
});

test('cli help', () => {
  const r = runCli(['-h']);
  assert.strictEqual(r.code, 0);
  assert.match(r.out, /usage/);
});
