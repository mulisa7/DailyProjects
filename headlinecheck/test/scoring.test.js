'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { scoreHeadline, normalise } = require('../extension/scoring.js');

const reasonsOf = (h) => scoreHeadline(h).reasons.join(' | ');

test('plain factual headline scores zero', () => {
  const r = scoreHeadline('Council approves new budget for road repairs');
  assert.strictEqual(r.score, 0);
  assert.strictEqual(r.level, 'low');
  assert.deepStrictEqual(r.reasons, []);
});

test('curiosity gap phrase is flagged', () => {
  const r = scoreHeadline("You won't believe what happened next");
  assert.ok(r.score >= 3);
  assert.match(reasonsOf("You won't believe what happened next"), /curiosity gap/);
});

test('curly apostrophes are treated like straight ones', () => {
  assert.ok(scoreHeadline('You won’t believe this').score >= 3);
  assert.strictEqual(normalise('It’s “fine”'), 'It\'s "fine"');
});

test('yes/no question headline is flagged, wh-question is not', () => {
  assert.match(reasonsOf('Is this the end of the office?'), /yes\/no question/);
  assert.doesNotMatch(reasonsOf('Who won the election?'), /yes\/no question/);
  assert.doesNotMatch(reasonsOf('Is the library open on Monday'), /yes\/no question/);
});

test('stacked punctuation adds points', () => {
  assert.match(reasonsOf('Prices rise again!!'), /stacked punctuation/);
  assert.match(reasonsOf('Wait, what?!'), /stacked punctuation/);
  assert.doesNotMatch(reasonsOf('Prices rise again!'), /stacked punctuation/);
});

test('listicle opener is flagged but year-starting headlines are not', () => {
  assert.match(reasonsOf('10 things only people from Durban will understand'), /listicle/);
  assert.match(reasonsOf('7 weird tips for sleeping'), /listicle/);
  assert.doesNotMatch(reasonsOf('2024 election results by province'), /listicle/);
});

test('dangling pronoun opener is flagged, "this week" is not', () => {
  assert.match(reasonsOf('This changes everything for renters'), /pronoun/);
  assert.doesNotMatch(reasonsOf('This week in parliament'), /pronoun/);
});

test('emotive words are capped at two points', () => {
  const r = scoreHeadline('Shocking, stunning, insane, epic bombshell');
  const emotive = r.reasons.find((x) => x.startsWith('emotive'));
  assert.ok(emotive);
  assert.strictEqual(r.score, 2);
});

test('combat verbs are flagged', () => {
  assert.match(reasonsOf('Minister slams critics over budget'), /combat verb/);
});

test('acronyms alone do not count as shouting', () => {
  assert.doesNotMatch(reasonsOf('NASA and FBI sign data sharing deal'), /capitals/);
  assert.match(reasonsOf('Minister DESTROYS critic in EPIC reply'), /words in capitals/);
});

test('whole headline in capitals is flagged', () => {
  assert.match(reasonsOf('BREAKING NEWS ABOUT THE ECONOMY'), /whole headline in capitals/);
  assert.doesNotMatch(reasonsOf('NATO'), /whole headline/);
});

test('a concrete figure lowers but never below zero', () => {
  const plain = scoreHeadline('Minister slams critics');
  const figure = scoreHeadline('Minister slams critics over R40 million deal');
  assert.strictEqual(figure.score, plain.score - 1);
  assert.strictEqual(scoreHeadline('Rates held at 4.25%').score, 0);
});

test('combined signals reach high', () => {
  const r = scoreHeadline("SHOCKING: Minister DESTROYS critic in epic reply!!");
  assert.strictEqual(r.level, 'high');
  assert.ok(r.score >= 4);
});

test('level boundaries', () => {
  assert.strictEqual(scoreHeadline('Is this the end?').level, 'medium');
  assert.strictEqual(scoreHeadline('Minister slams critics').level, 'low');
});

test('empty and whitespace-only input score zero without throwing', () => {
  for (const v of ['', '   ', '\n\t']) {
    const r = scoreHeadline(v);
    assert.strictEqual(r.score, 0);
    assert.strictEqual(r.words, 0);
  }
});

test('non-string input throws TypeError', () => {
  for (const v of [null, undefined, 42, {}, ['a']]) {
    assert.throws(() => scoreHeadline(v), TypeError);
  }
});

test('very long input is truncated and still scores', () => {
  const r = scoreHeadline('word '.repeat(5000) + "you won't believe");
  assert.strictEqual(r.score, 0);
  assert.ok(r.words <= 400);
});

test('non-latin text does not crash and scores zero', () => {
  assert.strictEqual(scoreHeadline('议会批准新的道路维修预算').score, 0);
  assert.strictEqual(scoreHeadline('🔥🔥🔥').score, 0);
});

test('regex special characters in input are harmless', () => {
  assert.doesNotThrow(() => scoreHeadline('(((*+?[ \\ ^$|'));
});

test('result is stable between calls (no shared regex state)', () => {
  const a = scoreHeadline("You won't believe what happened next");
  const b = scoreHeadline("You won't believe what happened next");
  assert.deepStrictEqual(a, b);
});
