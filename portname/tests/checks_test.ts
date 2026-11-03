import { assert, assertEquals, assertThrows } from "./assert.ts";
import { analyze, checkName, type Options, parseTargets, sanitize, type Target } from "../src/checks.ts";

function opts(targets: Target[] = ["windows", "macos"], extra: Partial<Options> = {}): Options {
  return { targets: new Set(targets), maxPath: 260, ...extra };
}

const kinds = (name: string, o = opts()) => checkName(name, o).map((h) => h.kind);

Deno.test("clean names produce nothing", () => {
  for (const n of ["report.pdf", "my photo (1).jpg", ".gitignore", "naïve café.txt", "a", "日本語.txt"]) {
    assertEquals(kinds(n), [], n);
  }
});

Deno.test("illegal characters are listed once each with the targets that reject them", () => {
  const hits = checkName('what?.txt', opts(["windows"]));
  assertEquals(hits.length, 1);
  assertEquals(hits[0].kind, "illegal-char");
  assert(hits[0].detail.includes('"?" (windows)'));

  const two = checkName("a<b>b<.txt", opts(["windows"]));
  assertEquals(two[0].detail, 'contains "<" (windows), ">" (windows)');
});

Deno.test("colon is rejected by macos and windows, but not when only linux-style rules would apply", () => {
  assert(kinds("12:30.txt", opts(["macos"])).includes("illegal-char"));
  assert(kinds("12:30.txt", opts(["windows"])).includes("illegal-char"));
  assertEquals(kinds("a b?.txt", opts(["macos"])), []);
});

Deno.test("control characters only matter on windows and onedrive", () => {
  assertEquals(kinds("a\tb", opts(["windows"])), ["control-char"]);
  assertEquals(kinds("a\tb", opts(["macos"])), []);
});

Deno.test("reserved device names match with and without extensions, any case", () => {
  for (const n of ["CON", "con", "Nul.txt", "aux.tar.gz", "COM1", "lpt9.log", "COM\u00b9", "CON .txt", "conin$"]) {
    assert(kinds(n, opts(["windows"])).includes("reserved-name"), n);
  }
  for (const n of ["console", "COM10", "COM0", "lpt", "xcon.txt", "con-1"]) {
    assert(!kinds(n, opts(["windows"])).includes("reserved-name"), n);
  }
  assertEquals(kinds("con", opts(["macos"])), []);
});

Deno.test("trailing dot or space is a windows problem", () => {
  assertEquals(kinds("notes.", opts(["windows"])), ["trailing-dot-or-space"]);
  assertEquals(kinds("notes ", opts(["windows"])), ["trailing-dot-or-space"]);
  assertEquals(kinds("notes.", opts(["macos"])), []);
});

Deno.test("onedrive adds leading space and forbidden names", () => {
  const od = opts(["onedrive"]);
  assert(kinds(" lead.txt", od).includes("leading-space"));
  assertEquals(kinds(" lead.txt", opts(["windows"])), []);
  assertEquals(kinds("desktop.ini", od), ["forbidden-name"]);
  assertEquals(kinds(".LOCK", od), ["forbidden-name"]);
  assertEquals(kinds("~$budget.xlsx", od), ["forbidden-name"]);
  assertEquals(kinds("a_vti_b", od), ["forbidden-name"]);
  assertEquals(kinds("desktop.ini", opts(["windows"])), []);
});

Deno.test("name length is UTF-16 units on windows and UTF-8 bytes on macos", () => {
  const accents = "\u00e9".repeat(200);
  assertEquals(kinds(accents, opts(["windows"])), []);
  assertEquals(kinds(accents, opts(["macos"])), ["name-too-long"]);
  assertEquals(kinds("a".repeat(255), opts(["windows", "macos"])), []);
  assertEquals(kinds("a".repeat(256), opts(["windows"])), ["name-too-long"]);
});

Deno.test("sanitize returns null for good names and fixes bad ones", () => {
  const o = opts(["windows", "macos", "onedrive"]);
  assertEquals(sanitize("fine.txt", o), null);
  assertEquals(sanitize("what?.txt", o), "what_.txt");
  assertEquals(sanitize("notes. ", o), "notes");
  assertEquals(sanitize("CON.txt", o), "_CON.txt");
  assertEquals(sanitize(" x.txt", o), "x.txt");
  assertEquals(sanitize("~$a.docx", o), "_a.docx");
  assertEquals(sanitize("...", o), "_");
  assertEquals(sanitize("a\tb", o), "a_b");
});

Deno.test("sanitize shortens long names but keeps the extension", () => {
  const fixed = sanitize("x".repeat(300) + ".pdf", opts(["windows"]))!;
  assertEquals(fixed.length, 255);
  assert(fixed.endsWith(".pdf"));
  assertEquals(checkName(fixed, opts(["windows"])), []);
  const mac = sanitize("\u00e9".repeat(200) + ".txt", opts(["macos"]))!;
  assertEquals(checkName(mac, opts(["macos"])), []);
});

Deno.test("sanitized names always pass the same checks", () => {
  const o = opts(["windows", "macos", "onedrive"]);
  const nasty = ["a:b", "CON", "x.", " y ", "~$z", "p|q*r", "\u0001\u0002", "COM3.txt", "desktop.ini", "?", "a_vti_b", ".lock"];
  for (const n of nasty) {
    const fixed = sanitize(n, o) ?? n;
    assertEquals(checkName(fixed, o), [], `${JSON.stringify(n)} -> ${JSON.stringify(fixed)}`);
  }
});

Deno.test("bad parent folders are reported once, not per file", () => {
  const issues = analyze(["bad?/a.txt", "bad?/b.txt", "bad?/sub/c.txt"], opts(["windows"]));
  assertEquals(issues.length, 1);
  assertEquals(issues[0].path, "bad?");
  assertEquals(issues[0].suggestion, "bad_");
});

Deno.test("suggestion keeps the parent path as it is", () => {
  const issues = analyze(["docs/CON.txt"], opts(["windows"]));
  assertEquals(issues[0].suggestion, "docs/_CON.txt");
});

Deno.test("case collisions among siblings", () => {
  const issues = analyze(["src/Readme.md", "src/README.md", "src/other.md"], opts());
  assertEquals(issues.map((i) => i.path), ["src/README.md", "src/Readme.md"]);
  assertEquals(issues[0].kind, "case-collision");
  assert(issues[0].detail.includes("letter case"));
});

Deno.test("same name in different folders is not a collision", () => {
  assertEquals(analyze(["a/File.txt", "b/file.txt"], opts()), []);
});

Deno.test("colliding folders are reported at the folder level", () => {
  const issues = analyze(["Docs/a.txt", "docs/a.txt"], opts());
  assertEquals(issues.map((i) => i.path), ["Docs", "docs"]);
});

Deno.test("unicode normalization collisions are only a macos concern", () => {
  const nfc = "caf\u00e9.txt";
  const nfd = "cafe\u0301.txt";
  assertEquals(analyze([nfc, nfd], opts(["windows"])), []);
  const mac = analyze([nfc, nfd], opts(["macos"]));
  assertEquals(mac.length, 2);
  assert(mac[0].detail.includes("normalization"));
});

Deno.test("path length counts the destination folder", () => {
  const rel = "a/".repeat(10) + "file.txt"; // 28 characters
  assertEquals(analyze([rel], opts(["windows"])), []);
  const withDest = analyze([rel], opts(["windows"], { dest: "C:\\" + "d".repeat(240) }));
  assertEquals(withDest.filter((i) => i.kind === "path-too-long").length, 1);
  assert(withDest[0].detail.includes("--dest"));
});

Deno.test("path limit is exactly max-path characters including the terminator", () => {
  const o = opts(["windows"], { maxPath: 20 });
  assertEquals(analyze(["a".repeat(19)], o), []);
  assertEquals(analyze(["a".repeat(20)], o).map((i) => i.kind), ["path-too-long"]);
});

Deno.test("only the shallowest too-long path is reported", () => {
  const o = opts(["windows"], { maxPath: 20 });
  const issues = analyze(["abcdefghijklmnopqr/stuvwxyz/more.txt", "short.txt"], o);
  assertEquals(issues.map((i) => i.path), ["abcdefghijklmnopqr/stuvwxyz"]);
});

Deno.test("onedrive path limit is 400", () => {
  const o = opts(["onedrive"]);
  assertEquals(analyze(["a".repeat(200) + "/" + "b".repeat(199)], o), []); // 400 characters
  assertEquals(analyze(["a".repeat(200) + "/" + "b".repeat(200)], o).map((i) => i.kind), ["path-too-long"]);
});

Deno.test("empty input, blank lines and dot paths are ignored", () => {
  assertEquals(analyze([], opts()), []);
  assertEquals(analyze(["", "  ".trim(), ".", "./"], opts()), []);
});

Deno.test("leading ./, trailing slash and CRLF are normalised", () => {
  const issues = analyze(["./bad?/\r", "bad?/x.txt"], opts(["windows"]));
  assertEquals(issues.map((i) => i.path), ["bad?"]);
});

Deno.test("backslash in a path component is an illegal character, not a separator", () => {
  const issues = analyze(["dir/a\\b.txt"], opts(["windows"]));
  assertEquals(issues.map((i) => i.path), ["dir/a\\b.txt"]);
  assertEquals(issues[0].kind, "illegal-char");
});

Deno.test("one name can have several problems", () => {
  const issues = analyze(["CON.a?."], opts(["windows"]));
  assertEquals(issues.map((i) => i.kind).sort(), ["illegal-char", "reserved-name", "trailing-dot-or-space"]);
});

Deno.test("parseTargets", () => {
  assertEquals(parseTargets("windows"), ["windows"]);
  assertEquals(parseTargets("macos, windows"), ["windows", "macos"]);
  assertEquals(parseTargets("ALL"), ["windows", "macos", "onedrive"]);
  assertEquals(parseTargets("windows,windows"), ["windows"]);
  assertThrows(() => parseTargets("linux"), Error, 'unknown target "linux"');
  assertThrows(() => parseTargets(""), Error, "unknown target");
});
