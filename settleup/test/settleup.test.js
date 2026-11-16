import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseAmount, formatCents, splitByWeights } from '../src/money.js';
import { parseExpenses } from '../src/parse.js';
import { computeBalances, settle } from '../src/settle.js';
import { run } from '../src/cli.js';

const bal = (t) => computeBalances(parseExpenses(t));

test('parseAmount handles normal and bad input', () => {
  assert.equal(parseAmount('12'), 1200);
  assert.equal(parseAmount('12.5'), 1250);
  assert.equal(parseAmount('$0.05'), 5);
  for (const bad of ['', 'abc', '1.234', '-5', '1,5', '1e3']) assert.throws(() => parseAmount(bad), /invalid amount/);
});

test('formatCents', () => {
  assert.equal(formatCents(5), '0.05');
  assert.equal(formatCents(-1250), '-12.50');
});

test('splitByWeights sums exactly and is deterministic', () => {
  assert.deepEqual(splitByWeights(100, [1, 1, 1]), [34, 33, 33]);
  assert.deepEqual(splitByWeights(1, [1, 1, 1]), [1, 0, 0]);
  assert.equal(splitByWeights(1001, [3, 7, 11]).reduce((a, b) => a + b), 1001);
  assert.throws(() => splitByWeights(100, []), /nothing to split/);
});

test('equal split balances', () => {
  const b = bal('Alice paid 60 dinner: Alice Bob Carol');
  assert.equal(b.get('Alice'), 4000);
  assert.equal(b.get('Bob'), -2000);
  assert.equal(b.get('Carol'), -2000);
});

test('weights, exact amounts and payments', () => {
  const b = bal('Bob paid 90 rent: Alice*2 Bob Carol\nAlice paid 30 taxi: Alice=10 Bob=20\nCarol sent Bob 5');
  assert.equal(b.get('Alice'), -2500);
  assert.equal(b.get('Bob'), 4250);
  assert.equal(b.get('Carol'), -1750);
  let total = 0;
  for (const v of b.values()) total += v;
  assert.equal(total, 0);
});

test('exact amounts plus remainder shared by others', () => {
  const b = bal('Alice paid 50: Alice=10 Bob Carol');
  assert.equal(b.get('Bob'), -2000);
  assert.equal(b.get('Carol'), -2000);
  assert.equal(b.get('Alice'), 4000);
});

test('comments, blanks, BOM, CRLF', () => {
  const items = parseExpenses('﻿# hi\r\n\r\nAlice paid 10 x: Alice Bob # trailing\r\n');
  assert.equal(items.length, 1);
  assert.equal(items[0].desc, 'x');
});

test('description is optional and may contain spaces', () => {
  assert.equal(parseExpenses('Alice paid 10: Alice Bob')[0].desc, '');
  assert.equal(parseExpenses('Alice paid 10 big night out: Alice Bob')[0].desc, 'big night out');
});

test('unicode names and commas between names', () => {
  const items = parseExpenses('Zoë paid 10 café: Zoë, Renée');
  assert.deepEqual(items[0].people.map((p) => p.name), ['Zoë', 'Renée']);
});

test('invalid lines give line numbers', () => {
  assert.throws(() => parseExpenses('Alice paid 10 x'), /line 1: missing ":"/);
  assert.throws(() => parseExpenses('\nhello world'), /line 2: cannot understand/);
  assert.throws(() => parseExpenses('Alice paid 0 x: Bob'), /more than zero/);
  assert.throws(() => parseExpenses('Alice paid 10 x:'), /no one listed/);
  assert.throws(() => parseExpenses('Alice paid 10 x: Bob Bob'), /listed twice/);
  assert.throws(() => parseExpenses('Alice paid 10 x: Bob*0'), /weight/);
  assert.throws(() => parseExpenses('Alice paid 10 x: Bob=abc'), /invalid amount/);
  assert.throws(() => parseExpenses('Alice sent Alice 5'), /themselves/);
  assert.throws(() => parseExpenses('Alice paid 10 x: B@b'), /invalid name/);
});

test('exact amounts exceeding or not covering total are rejected', () => {
  assert.throws(() => bal('A paid 10 x: A=6 B=6'), /more than the total/);
  assert.throws(() => bal('A paid 10 x: A=6 B=3'), /unassigned/);
});

test('settle: simple chain collapses', () => {
  const r = settle(new Map([['A', 10], ['B', 0], ['C', -10]]));
  assert.deepEqual(r.transfers, [{ from: 'C', to: 'A', cents: 10 }]);
});

test('settle: finds independent zero-sum groups (fewer than greedy)', () => {
  // A+B... two pairs that net separately: 2 payments, a naive single pass could need 3.
  const r = settle(new Map([['A', 5], ['B', -5], ['C', 7], ['D', -7]]));
  assert.equal(r.transfers.length, 2);
  assert.equal(r.exact, true);
});

test('settle: transfers actually clear every balance', () => {
  const b = new Map([['A', 1234], ['B', -34], ['C', -500], ['D', -700], ['E', 100], ['F', -100]]);
  const r = settle(b);
  const left = new Map(b);
  for (const t of r.transfers) {
    left.set(t.from, left.get(t.from) + t.cents);
    left.set(t.to, left.get(t.to) - t.cents);
    assert.ok(t.cents > 0);
  }
  for (const v of left.values()) assert.equal(v, 0);
});

test('settle: empty and all-zero', () => {
  assert.deepEqual(settle(new Map()).transfers, []);
  assert.deepEqual(settle(new Map([['A', 0]])).transfers, []);
});

test('settle: non-zero total throws', () => {
  assert.throws(() => settle(new Map([['A', 5]])), /do not sum to zero/);
});

test('settle: more than 18 people falls back to greedy and still clears balances', () => {
  const m = new Map();
  for (let i = 0; i < 20; i++) m.set('P' + String(i).padStart(2, '0'), i % 2 ? -100 - i : 100 + i - 1);
  let tot = 0; for (const v of m.values()) tot += v;
  m.set('Z', -tot);
  const r = settle(m);
  assert.equal(r.exact, false);
  const left = new Map(m);
  for (const t of r.transfers) { left.set(t.from, left.get(t.from) + t.cents); left.set(t.to, left.get(t.to) - t.cents); }
  for (const v of left.values()) assert.equal(v, 0);
});

test('cli: example flow', () => {
  const r = run(['x.txt', '--balances'], () => 'Alice paid 60 dinner: Alice Bob Carol\n');
  assert.equal(r.code, 0);
  assert.match(r.out, /Alice\s+\+40.00/);
  assert.match(r.out, /2 payments/);
  assert.match(r.out, /Bob pays Alice 20.00/);
});

test('cli: already settled', () => {
  const r = run(['x'], () => 'A paid 10 x: B\nB sent A 10\n');
  assert.match(r.out, /Everyone is settled up/);
});

test('cli: json output', () => {
  const r = run(['x', '--json'], () => 'A paid 10 x: A B');
  const j = JSON.parse(r.out);
  assert.deepEqual(j.transfers, [{ from: 'B', to: 'A', amount: 5 }]);
  assert.equal(j.balances.A, 5);
});

test('cli: errors and usage', () => {
  assert.equal(run([], () => '').code, 2);
  assert.equal(run(['a', 'b'], () => '').code, 2);
  assert.equal(run(['a', '--nope'], () => '').code, 2);
  assert.equal(run(['--help'], () => '').code, 0);
  assert.equal(run(['x'], () => '').code, 1);
  assert.equal(run(['x'], () => '# only a comment\n').code, 1);
  assert.match(run(['x'], () => 'garbage').err, /line 1/);
  const missing = run(['nope.txt'], () => { const e = new Error('x'); e.code = 'ENOENT'; throw e; });
  assert.equal(missing.code, 1);
  assert.match(missing.err, /no such file/);
});
