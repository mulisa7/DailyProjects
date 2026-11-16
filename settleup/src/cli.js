#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { parseExpenses } from './parse.js';
import { computeBalances, settle } from './settle.js';
import { formatCents } from './money.js';

const HELP = `settleup - who owes whom, with the fewest payments

Usage: settleup <file|-> [--balances] [--json]

  <file>       text file of expenses, or - to read standard input
  --balances   also print each person's net balance
  --json       machine readable output

Line formats:
  Alice paid 60 dinner: Alice Bob Carol         equal split
  Bob paid 90 rent: Alice*2 Bob Carol           weighted shares
  Alice paid 30 taxi: Alice=10 Bob=20           exact amounts
  Bob sent Alice 20                             a payment already made
  # comments and blank lines are ignored

Exit codes: 0 ok, 1 invalid input or file, 2 bad usage.`;

export function run(argv, readInput) {
  const args = argv.filter((a) => !a.startsWith('--') || a === '-');
  const flags = new Set(argv.filter((a) => a.startsWith('--')));
  if (flags.has('--help') || argv.includes('-h')) return { code: 0, out: HELP + '\n' };
  for (const f of flags) {
    if (!['--balances', '--json'].includes(f)) return { code: 2, err: `unknown option ${f}\n\n${HELP}\n` };
  }
  if (args.length !== 1) return { code: 2, err: `expected exactly one input file\n\n${HELP}\n` };
  let text;
  try { text = readInput(args[0]); } catch (e) { return { code: 1, err: `cannot read ${args[0]}: ${e.code === 'ENOENT' ? 'no such file' : e.message}\n` }; }
  let items, balances, result;
  try {
    items = parseExpenses(text);
    if (items.length === 0) return { code: 1, err: 'no expenses found in input\n' };
    balances = computeBalances(items);
    result = settle(balances);
  } catch (e) {
    return { code: 1, err: `${e.message}\n` };
  }
  const bal = [...balances].sort((a, b) => a[0].localeCompare(b[0]));
  if (flags.has('--json')) {
    return { code: 0, out: JSON.stringify({
      balances: Object.fromEntries(bal.map(([n, c]) => [n, c / 100])),
      transfers: result.transfers.map((t) => ({ from: t.from, to: t.to, amount: t.cents / 100 })),
      minimal: result.exact,
    }, null, 2) + '\n' };
  }
  let out = '';
  if (flags.has('--balances')) {
    out += 'Balances (+ is owed, - owes):\n';
    for (const [n, c] of bal) out += `  ${n.padEnd(12)} ${(c > 0 ? '+' : '') + formatCents(c)}\n`;
    out += '\n';
  }
  if (result.transfers.length === 0) {
    out += 'Everyone is settled up.\n';
  } else {
    out += `${result.transfers.length} payment${result.transfers.length === 1 ? '' : 's'} to settle up:\n`;
    for (const t of result.transfers) out += `  ${t.from} pays ${t.to} ${formatCents(t.cents)}\n`;
    if (!result.exact) out += '(more than 18 people with a balance: payments are not guaranteed to be the fewest possible)\n';
  }
  return { code: 0, out };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const r = run(process.argv.slice(2), (p) => readFileSync(p === '-' ? 0 : p, 'utf8'));
  if (r.out) process.stdout.write(r.out);
  if (r.err) process.stderr.write(r.err);
  process.exit(r.code);
}
