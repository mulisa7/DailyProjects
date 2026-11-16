// Money is handled as integer cents everywhere to avoid float drift.

export function parseAmount(text) {
  const t = String(text).trim().replace(/^[$€£]/, '');
  if (!/^\d+(\.\d{1,2})?$/.test(t)) {
    throw new Error(`invalid amount "${text}" (use digits with at most 2 decimals, e.g. 12 or 12.50)`);
  }
  const [whole, frac = ''] = t.split('.');
  return Number(whole) * 100 + Number((frac + '00').slice(0, 2));
}

export function formatCents(cents) {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

// Split `total` cents by integer weights using the largest remainder method.
// Ties are broken by input order, so the result is deterministic and sums exactly to total.
export function splitByWeights(total, weights) {
  const sum = weights.reduce((a, b) => a + b, 0);
  if (weights.length === 0 || sum <= 0) throw new Error('nothing to split between');
  const shares = weights.map((w) => Math.floor((total * w) / sum));
  let left = total - shares.reduce((a, b) => a + b, 0);
  const order = weights
    .map((w, i) => ({ i, rem: (total * w) % sum }))
    .sort((a, b) => b.rem - a.rem || a.i - b.i);
  for (let k = 0; left > 0; k++, left--) shares[order[k].i] += 1;
  return shares;
}
