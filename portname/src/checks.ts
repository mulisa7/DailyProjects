// Rules for file names that do not survive a move between file systems.
// Everything here is pure: strings in, issues out.

export type Target = "windows" | "macos" | "onedrive";

export type Kind =
  | "illegal-char"
  | "control-char"
  | "reserved-name"
  | "trailing-dot-or-space"
  | "leading-space"
  | "forbidden-name"
  | "name-too-long"
  | "path-too-long"
  | "case-collision";

export interface Options {
  targets: Set<Target>;
  /** Windows MAX_PATH. A path of this many characters or more is flagged. */
  maxPath: number;
  /** Folder the tree will be copied into; counts towards path length. */
  dest?: string;
}

export interface Issue {
  path: string;
  kind: Kind;
  detail: string;
  suggestion: string | null;
}

const ALL_TARGETS: Target[] = ["windows", "macos", "onedrive"];
export const DEFAULT_TARGETS: Target[] = ["windows", "macos"];
export const DEFAULT_MAX_PATH = 260;
const ONEDRIVE_MAX_PATH = 400;
const MAX_NAME = 255;

const WIN_ILLEGAL = '<>:"\\|?*';
const RESERVED = /^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])$/i;
const ONEDRIVE_NAMES = /^(\.lock|desktop\.ini)$/i;

export function parseTargets(text: string): Target[] {
  const out = new Set<Target>();
  for (const raw of text.split(",")) {
    const word = raw.trim().toLowerCase();
    if (word === "all") ALL_TARGETS.forEach((t) => out.add(t));
    else if ((ALL_TARGETS as string[]).includes(word)) out.add(word as Target);
    else throw new Error(`unknown target "${raw.trim()}" (use windows, macos, onedrive or all)`);
  }
  return ALL_TARGETS.filter((t) => out.has(t));
}

function winLike(o: Options): boolean {
  return o.targets.has("windows") || o.targets.has("onedrive");
}

function winWho(o: Options): string {
  return (["windows", "onedrive"] as Target[]).filter((t) => o.targets.has(t)).join("/");
}

function show(ch: string): string {
  return `"${ch}"`;
}

function charTargets(ch: string, o: Options): string[] {
  const who: string[] = [];
  if (WIN_ILLEGAL.includes(ch) && winLike(o)) who.push(winWho(o));
  if (ch === ":" && o.targets.has("macos")) who.push("macos");
  return who;
}

function badChars(o: Options): Set<string> {
  const bad = new Set<string>();
  if (winLike(o)) for (const c of WIN_ILLEGAL) bad.add(c);
  if (o.targets.has("macos")) bad.add(":");
  return bad;
}

/** Part of the name before the first dot, which is what Windows matches against device names. */
function reservedStem(name: string): string {
  const dot = name.indexOf(".");
  return (dot === -1 ? name : name.slice(0, dot)).replace(/ +$/, "");
}

function utf8Len(s: string): number {
  return new TextEncoder().encode(s).length;
}

function isTooLong(name: string, o: Options): boolean {
  if (winLike(o) && name.length > MAX_NAME) return true;
  return o.targets.has("macos") && utf8Len(name) > MAX_NAME;
}

export function checkName(name: string, o: Options): { kind: Kind; detail: string }[] {
  const out: { kind: Kind; detail: string }[] = [];
  const win = winLike(o);

  const found = [...new Set(Array.from(name).filter((c) => badChars(o).has(c)))];
  if (found.length > 0) {
    const parts = found.map((c) => `${show(c)} (${charTargets(c, o).join(", ")})`);
    out.push({ kind: "illegal-char", detail: `contains ${parts.join(", ")}` });
  }

  if (win) {
    const ctrl = Array.from(name).filter((c) => c.charCodeAt(0) < 32);
    if (ctrl.length > 0) {
      const codes = [...new Set(ctrl.map((c) => "U+" + c.charCodeAt(0).toString(16).padStart(4, "0").toUpperCase()))];
      out.push({ kind: "control-char", detail: `contains control character ${codes.join(", ")} (${winWho(o)})` });
    }
    const stem = reservedStem(name);
    if (RESERVED.test(stem)) {
      out.push({ kind: "reserved-name", detail: `"${stem}" is a reserved device name on ${winWho(o)}, with or without an extension` });
    }
    if (/[. ]$/.test(name)) {
      out.push({ kind: "trailing-dot-or-space", detail: `ends with a dot or space, which ${winWho(o)} silently strips or rejects` });
    }
  }

  if (o.targets.has("onedrive")) {
    if (name.startsWith(" ")) {
      out.push({ kind: "leading-space", detail: "starts with a space (onedrive)" });
    }
    if (ONEDRIVE_NAMES.test(name)) {
      out.push({ kind: "forbidden-name", detail: `"${name}" is not allowed by onedrive` });
    } else if (name.startsWith("~$")) {
      out.push({ kind: "forbidden-name", detail: 'names starting with "~$" are not allowed by onedrive' });
    } else if (name.includes("_vti_")) {
      out.push({ kind: "forbidden-name", detail: 'names containing "_vti_" are not allowed by onedrive' });
    }
  }

  if (isTooLong(name, o)) {
    const parts: string[] = [];
    if (win && name.length > MAX_NAME) parts.push(`${name.length} UTF-16 units on ${winWho(o)}`);
    if (o.targets.has("macos") && utf8Len(name) > MAX_NAME) parts.push(`${utf8Len(name)} UTF-8 bytes on macos`);
    out.push({ kind: "name-too-long", detail: `longer than ${MAX_NAME}: ${parts.join(", ")}` });
  }
  return out;
}

function shrink(s: string, o: Options): string {
  while (isTooLong(s, o)) {
    const dot = s.lastIndexOf(".");
    const cut = dot > 0 ? dot : s.length;
    const stem = Array.from(s.slice(0, cut));
    if (stem.length > 1) {
      stem.pop();
      s = stem.join("") + s.slice(cut);
    } else {
      s = Array.from(s).slice(0, -1).join("");
    }
  }
  return s;
}

/** A safe replacement for one name, or null if the name needs no change. */
export function sanitize(name: string, o: Options): string | null {
  const win = winLike(o);
  const bad = badChars(o);
  let s = Array.from(name, (c) => (bad.has(c) || (win && c.charCodeAt(0) < 32) ? "_" : c)).join("");
  if (o.targets.has("onedrive")) {
    s = s.replace(/^ +/, "").replace(/^~\$/, "_").replaceAll("_vti_", "_vti-");
    if (ONEDRIVE_NAMES.test(s)) s = "_" + s;
  }
  s = shrink(s, o);
  if (win) {
    s = s.replace(/[. ]+$/, "");
    if (s === "") s = "_";
    if (RESERVED.test(reservedStem(s))) s = "_" + s;
  }
  return s === name ? null : s;
}

function joinPath(parent: string, name: string): string {
  return parent === "" ? name : parent + "/" + name;
}

function fullLength(rel: string, o: Options): number {
  if (o.dest === undefined) return rel.length;
  return o.dest.replace(/[\\/]+$/, "").length + 1 + rel.length;
}

function pathLimitIssue(rel: string, o: Options): string | null {
  const len = fullLength(rel, o);
  const parts: string[] = [];
  if (o.targets.has("windows") && len >= o.maxPath) parts.push(`${len} characters, windows limit is ${o.maxPath - 1}`);
  if (o.targets.has("onedrive") && len > ONEDRIVE_MAX_PATH) parts.push(`${len} characters, onedrive limit is ${ONEDRIVE_MAX_PATH}`);
  if (parts.length === 0) return null;
  const base = o.dest === undefined ? "relative path" : "path including --dest";
  return `${base} is ${parts.join("; ")}`;
}

function normalizeInput(line: string): string {
  let p = line.replace(/\r$/, "");
  while (p.startsWith("./")) p = p.slice(2);
  p = p.replace(/\/+$/, "");
  return p === "." ? "" : p;
}

function collisionKey(name: string, o: Options): string {
  const base = o.targets.has("macos") ? name.normalize("NFD") : name;
  return base.toLowerCase();
}

/** Check a list of "/"-separated relative paths. Every parent folder is checked once. */
export function analyze(inputs: string[], o: Options): Issue[] {
  const entries = new Set<string>();
  for (const raw of inputs) {
    const parts = normalizeInput(raw).split("/").filter((c) => c !== "" && c !== ".");
    let acc = "";
    for (const part of parts) {
      acc = joinPath(acc, part);
      entries.add(acc);
    }
  }

  const issues: Issue[] = [];
  const byParent = new Map<string, Set<string>>();

  for (const path of entries) {
    const slash = path.lastIndexOf("/");
    const parent = slash === -1 ? "" : path.slice(0, slash);
    const name = path.slice(slash + 1);
    if (!byParent.has(parent)) byParent.set(parent, new Set());
    byParent.get(parent)!.add(name);

    const fixed = sanitize(name, o);
    const suggestion = fixed === null ? null : joinPath(parent, fixed);
    for (const hit of checkName(name, o)) {
      issues.push({ path, kind: hit.kind, detail: hit.detail, suggestion });
    }

    const tooLong = pathLimitIssue(path, o);
    if (tooLong !== null && (parent === "" || pathLimitIssue(parent, o) === null)) {
      issues.push({ path, kind: "path-too-long", detail: tooLong, suggestion: null });
    }
  }

  for (const [parent, names] of byParent) {
    const groups = new Map<string, string[]>();
    for (const name of names) {
      const key = collisionKey(name, o);
      groups.set(key, [...(groups.get(key) ?? []), name]);
    }
    for (const members of groups.values()) {
      if (members.length < 2) continue;
      members.sort();
      for (const name of members) {
        const others = members.filter((m) => m !== name);
        const caseOnly = others.every((m) => m.toLowerCase() === name.toLowerCase());
        const why = caseOnly ? "differs only by letter case" : "differs only by case or Unicode normalization";
        issues.push({
          path: joinPath(parent, name),
          kind: "case-collision",
          detail: `${others.map(show).join(", ")} ${why}, so they are the same name on case-insensitive file systems`,
          suggestion: null,
        });
      }
    }
  }

  return issues.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : a.kind < b.kind ? -1 : a.kind > b.kind ? 1 : 0));
}

export function countPaths(inputs: string[]): number {
  return new Set(inputs.map(normalizeInput).filter((p) => p !== "")).size;
}
