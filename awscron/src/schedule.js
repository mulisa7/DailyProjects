'use strict';

const DAY_MS = 86400000;

function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate(); // m is 1-12
}

// Nearest weekday to day d of the month, without leaving the month.
function nearestWeekday(y, m, d) {
  const dim = daysInMonth(y, m);
  if (d > dim) return null; // AWS skips the month when the day does not exist
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  if (dow >= 1 && dow <= 5) return d;
  if (dow === 6) return d === 1 ? 3 : d - 1;
  return d === dim ? d - 2 : d + 1;
}

function dayMatches(f, y, m, d) {
  const dim = daysInMonth(y, m);
  const [, , dom, , dow] = f;
  if (!dom.noSpec) {
    if (dom.any) return true;
    if (dom.values.has(d)) return true;
    if (dom.last && d === dim) return true;
    return dom.weekdays.some((w) => nearestWeekday(y, m, w) === d);
  }
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 1; // 1 = Sunday
  if (dow.any) return true;
  if (dow.values.has(wd)) return true;
  if (dow.lastDow && dow.lastDow.some((x) => x === wd && d + 7 > dim)) return true;
  return dow.nth.some(([x, n]) => x === wd && Math.ceil(d / 7) === n);
}

function sorted(set) {
  return [...set].sort((a, b) => a - b);
}

// Next `count` run times strictly after `from`, in UTC. Looks at most `horizonYears` ahead.
function nextRuns(parsed, from, count, horizonYears = 20) {
  const out = [];
  if (parsed.kind === 'rate') {
    for (let i = 1; i <= count; i++) out.push(new Date(from.getTime() + i * parsed.intervalMs));
    return out;
  }
  const [min, hr, , mon, , yr] = parsed.fields;
  const minutes = sorted(min.values);
  const hours = sorted(hr.values);
  const limit = Date.UTC(from.getUTCFullYear() + horizonYears, 0, 1);
  let day = Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate());
  while (out.length < count && day < limit) {
    const dt = new Date(day);
    const y = dt.getUTCFullYear();
    const m = dt.getUTCMonth() + 1;
    const d = dt.getUTCDate();
    if (yr.values.has(y) && mon.values.has(m) && dayMatches(parsed.fields, y, m, d)) {
      for (const h of hours) {
        for (const mi of minutes) {
          const t = Date.UTC(y, m - 1, d, h, mi);
          if (t > from.getTime()) {
            out.push(new Date(t));
            if (out.length === count) return out;
          }
        }
      }
    }
    day += DAY_MS;
  }
  return out;
}

module.exports = { nextRuns, nearestWeekday, dayMatches };
