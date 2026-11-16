import { parseAmount } from './money.js';

const NAME = /^[\p{L}\p{N}_.'-]+$/u;

function checkName(name, lineNo) {
  if (!NAME.test(name)) throw new Error(`line ${lineNo}: invalid name "${name}"`);
}

// Parses one participant token: "Bob", "Bob*2" (weight) or "Bob=12.50" (exact amount).
function parseParticipant(tok, lineNo) {
  let m;
  if ((m = tok.match(/^(.+?)=(.+)$/))) {
    checkName(m[1], lineNo);
    try {
      return { name: m[1], kind: 'exact', cents: parseAmount(m[2]) };
    } catch (e) {
      throw new Error(`line ${lineNo}: ${e.message}`);
    }
  }
  if ((m = tok.match(/^(.+?)\*(.+)$/))) {
    checkName(m[1], lineNo);
    if (!/^\d+$/.test(m[2]) || Number(m[2]) < 1) {
      throw new Error(`line ${lineNo}: share weight for ${m[1]} must be a whole number of 1 or more, got "${m[2]}"`);
    }
    return { name: m[1], kind: 'weight', weight: Number(m[2]) };
  }
  checkName(tok, lineNo);
  return { name: tok, kind: 'weight', weight: 1 };
}

// Line formats:
//   <payer> paid <amount> [description] : <participant> <participant> ...
//   <from> sent <to> <amount>
// Blank lines and lines starting with # are ignored.
export function parseExpenses(text) {
  const items = [];
  const lines = String(text).replace(/^﻿/, '').split(/\r?\n/);
  lines.forEach((raw, idx) => {
    const lineNo = idx + 1;
    const line = raw.replace(/\s+#.*$/, '').trim();
    if (!line || line.startsWith('#')) return;

    let m = line.match(/^(\S+)\s+sent\s+(\S+)\s+(\S+)$/i);
    if (m) {
      checkName(m[1], lineNo);
      checkName(m[2], lineNo);
      if (m[1] === m[2]) throw new Error(`line ${lineNo}: ${m[1]} cannot send money to themselves`);
      let cents;
      try { cents = parseAmount(m[3]); } catch (e) { throw new Error(`line ${lineNo}: ${e.message}`); }
      if (cents === 0) throw new Error(`line ${lineNo}: amount must be more than zero`);
      items.push({ type: 'payment', from: m[1], to: m[2], cents, line: lineNo });
      return;
    }

    m = line.match(/^(\S+)\s+paid\s+(\S+)(?:\s+([^:]*?))?\s*:\s*(.*)$/i);
    if (!m) {
      if (/\bpaid\b/i.test(line) && !line.includes(':')) {
        throw new Error(`line ${lineNo}: missing ":" and the list of people who share the cost`);
      }
      throw new Error(`line ${lineNo}: cannot understand "${line}" (expected "Name paid 12.50 what for: Name Name")`);
    }
    checkName(m[1], lineNo);
    let cents;
    try { cents = parseAmount(m[2]); } catch (e) { throw new Error(`line ${lineNo}: ${e.message}`); }
    if (cents === 0) throw new Error(`line ${lineNo}: amount must be more than zero`);
    const toks = m[4].split(/[\s,]+/).filter(Boolean);
    if (toks.length === 0) throw new Error(`line ${lineNo}: no one listed after ":"`);
    const people = toks.map((t) => parseParticipant(t, lineNo));
    const seen = new Set();
    for (const p of people) {
      if (seen.has(p.name)) throw new Error(`line ${lineNo}: ${p.name} is listed twice`);
      seen.add(p.name);
    }
    items.push({ type: 'expense', payer: m[1], cents, desc: (m[3] || '').trim(), people, line: lineNo });
  });
  return items;
}
