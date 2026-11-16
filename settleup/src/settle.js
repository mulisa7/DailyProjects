import { splitByWeights } from './money.js';

// Turns parsed items into net balances in cents. Positive = is owed money, negative = owes.
export function computeBalances(items) {
  const bal = new Map();
  const add = (n, c) => bal.set(n, (bal.get(n) || 0) + c);
  for (const it of items) {
    if (it.type === 'payment') {
      add(it.from, it.cents);
      add(it.to, -it.cents);
      continue;
    }
    const exact = it.people.filter((p) => p.kind === 'exact');
    const weighted = it.people.filter((p) => p.kind === 'weight');
    const exactSum = exact.reduce((a, p) => a + p.cents, 0);
    if (exactSum > it.cents) {
      throw new Error(`line ${it.line}: exact amounts add up to more than the total`);
    }
    const rest = it.cents - exactSum;
    if (weighted.length === 0 && rest !== 0) {
      throw new Error(`line ${it.line}: exact amounts leave ${rest} cents unassigned; add a person without an amount to take the rest`);
    }
    const owed = new Map();
    for (const p of exact) owed.set(p.name, p.cents);
    if (weighted.length) {
      const parts = splitByWeights(rest, weighted.map((p) => p.weight));
      weighted.forEach((p, i) => owed.set(p.name, parts[i]));
    }
    add(it.payer, it.cents);
    for (const [n, c] of owed) add(n, -c);
  }
  return bal;
}

function greedyGroup(members) {
  // members: [{name, cents}] summing to zero. Returns at most members.length-1 transfers.
  const debtors = members.filter((m) => m.cents < 0).map((m) => ({ ...m })).sort((a, b) => a.cents - b.cents || a.name.localeCompare(b.name));
  const creditors = members.filter((m) => m.cents > 0).map((m) => ({ ...m })).sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
  const out = [];
  let i = 0, j = 0;
  while (i < debtors.length && j < creditors.length) {
    const amt = Math.min(-debtors[i].cents, creditors[j].cents);
    out.push({ from: debtors[i].name, to: creditors[j].name, cents: amt });
    debtors[i].cents += amt;
    creditors[j].cents -= amt;
    if (debtors[i].cents === 0) i++;
    if (creditors[j].cents === 0) j++;
  }
  return out;
}

export const EXACT_LIMIT = 18;

// Fewest transfers: split the people with non-zero balances into the maximum number of
// groups that each sum to zero; a group of k people needs k-1 payments.
// Exact for up to EXACT_LIMIT people, otherwise one greedy pass over everyone.
export function settle(balances) {
  const people = [...balances].filter(([, c]) => c !== 0).map(([name, cents]) => ({ name, cents }));
  const total = people.reduce((a, p) => a + p.cents, 0);
  if (total !== 0) throw new Error(`balances do not sum to zero (${total} cents off)`);
  if (people.length === 0) return { transfers: [], exact: true };
  people.sort((a, b) => a.name.localeCompare(b.name));
  if (people.length > EXACT_LIMIT) return { transfers: greedyGroup(people), exact: false };

  const n = people.length;
  const full = (1 << n) - 1;
  const sum = new Int32Array(1 << n);
  for (let m = 1; m <= full; m++) {
    const low = m & -m;
    sum[m] = sum[m ^ low] + people[31 - Math.clz32(low)].cents;
  }
  // best[m] = max number of zero-sum groups that partition subset m (only meaningful if sum[m]==0)
  const best = new Int8Array(1 << n);
  const pick = new Int32Array(1 << n);
  for (let m = 1; m <= full; m++) {
    if (sum[m] !== 0) continue;
    const low = m & -m; // the group containing the lowest member
    let bestCount = 1, bestSub = m;
    for (let s = (m - 1) & m; s > 0; s = (s - 1) & m) {
      if (!(s & low) || sum[s] !== 0) continue;
      const c = 1 + best[m ^ s];
      if (c > bestCount) { bestCount = c; bestSub = s; }
    }
    best[m] = bestCount;
    pick[m] = bestSub;
  }
  const transfers = [];
  let m = full;
  while (m) {
    const s = pick[m];
    const members = [];
    for (let k = 0; k < n; k++) if (s & (1 << k)) members.push(people[k]);
    transfers.push(...greedyGroup(members));
    m ^= s;
  }
  transfers.sort((a, b) => a.from.localeCompare(b.from) || a.to.localeCompare(b.to));
  return { transfers, exact: true };
}
