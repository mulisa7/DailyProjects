import { assert, assertEquals } from "./assert.ts";
import { run } from "../src/cli.ts";

interface Result {
  code: number;
  out: string;
  err: string;
}

async function cli(args: string[], stdin = ""): Promise<Result> {
  let out = "";
  let err = "";
  const code = await run(args, {
    out: (t) => (out += t),
    err: (t) => (err += t),
    readStdin: () => Promise.resolve(stdin),
  });
  return { code, out, err };
}

async function withTree(files: string[], fn: (root: string) => Promise<void>): Promise<void> {
  const root = await Deno.makeTempDir({ prefix: "portname-" });
  try {
    for (const f of files) {
      const full = root + "/" + f;
      if (f.endsWith("/")) await Deno.mkdir(full, { recursive: true });
      else {
        await Deno.mkdir(full.slice(0, full.lastIndexOf("/")), { recursive: true });
        await Deno.writeTextFile(full, "x");
      }
    }
    await fn(root);
  } finally {
    await Deno.remove(root, { recursive: true });
  }
}

Deno.test("stdin: clean list exits 0", async () => {
  const r = await cli(["--stdin"], "a.txt\nsrc/b.ts\n");
  assertEquals(r.code, 0);
  assert(r.out.includes("checked 2 paths"));
  assert(r.out.includes("no problems"));
});

Deno.test("stdin: problems exit 1 with a suggestion", async () => {
  const r = await cli(["--stdin", "-t", "windows"], "docs/what?.txt\r\nok.txt\r\n");
  assertEquals(r.code, 1);
  assert(r.out.includes("illegal-char"));
  assert(r.out.includes("suggest: docs/what_.txt"));
  assert(r.out.includes("1 problem\n"));
});

Deno.test("stdin: empty input is a clean empty result", async () => {
  for (const input of ["", "\n\n", "\r\n"]) {
    const r = await cli(["--stdin"], input);
    assertEquals(r.code, 0);
    assert(r.out.includes("checked 0 paths"));
  }
});

Deno.test("json output parses and carries the issue fields", async () => {
  const r = await cli(["--stdin", "--json", "--target", "all"], "~$tmp.docx\n");
  assertEquals(r.code, 1);
  const data = JSON.parse(r.out);
  assertEquals(data.scanned, 1);
  assertEquals(data.targets, ["windows", "macos", "onedrive"]);
  assertEquals(data.issues[0].kind, "forbidden-name");
  assertEquals(data.issues[0].suggestion, "_tmp.docx");
});

Deno.test("json output for a clean list has an empty issues array", async () => {
  const data = JSON.parse((await cli(["--stdin", "--json"], "a\n")).out);
  assertEquals(data.issues, []);
  assertEquals(data.problems, 0);
});

Deno.test("--dest and --max-path trigger the path length check", async () => {
  const r = await cli(["--stdin", "-t", "windows", "--dest", "C:\\Users\\me\\OneDrive", "--max-path", "30"], "folder/file.txt\n");
  assertEquals(r.code, 1);
  assert(r.out.includes("path-too-long"));
});

Deno.test("scans a real folder", async () => {
  await withTree(["a.txt", "sub/b.txt", "sub/deep/c.txt", "empty/"], async (root) => {
    const r = await cli([root]);
    assertEquals(r.code, 0);
    assert(r.out.includes("checked 6 paths"), r.out);
  });
});

Deno.test("scanning a folder finds real problems", async () => {
  await withTree(["ok.txt", "~$lock.docx", "dir/x.txt"], async (root) => {
    const r = await cli([root, "-t", "onedrive"]);
    assertEquals(r.code, 1);
    assert(r.out.includes("~$lock.docx"));
    assert(!r.out.includes("dir/x.txt"));
  });
});

Deno.test("scanning an empty folder is clean", async () => {
  await withTree([], async (root) => {
    const r = await cli([root]);
    assertEquals(r.code, 0);
    assert(r.out.includes("checked 0 paths"));
  });
});

Deno.test("missing folder exits 2", async () => {
  const r = await cli(["definitely-not-here-123"]);
  assertEquals(r.code, 2);
  assert(r.err.includes("cannot use"));
});

Deno.test("a file instead of a folder exits 2", async () => {
  await withTree(["f.txt"], async (root) => {
    const r = await cli([root + "/f.txt"]);
    assertEquals(r.code, 2);
    assert(r.err.includes("not a folder"));
  });
});

Deno.test("usage errors exit 2 and print usage", async () => {
  const cases: string[][] = [
    [],
    ["a", "b"],
    ["--stdin", "somefolder"],
    ["--bogus"],
    ["--target"],
    ["--stdin", "--target", "linux"],
    ["--stdin", "--max-path", "abc"],
    ["--stdin", "--max-path", "5"],
    ["--stdin", "--max-path", "-1"],
    ["--stdin", "--dest"],
  ];
  for (const args of cases) {
    const r = await cli(args);
    assertEquals(r.code, 2, JSON.stringify(args));
    assert(r.err.includes("usage:"), JSON.stringify(args));
    assertEquals(r.out, "", JSON.stringify(args));
  }
});

Deno.test("--help prints usage and exits 0", async () => {
  const r = await cli(["--help"]);
  assertEquals(r.code, 0);
  assert(r.out.startsWith("usage:"));
});

Deno.test("unexpected input: very long line and odd characters do not crash", async () => {
  const r = await cli(["--stdin", "-t", "all"], "x".repeat(5000) + "\n\u0000\u202e.txt\n\ud83d\ude00.txt\n");
  assertEquals(r.code, 1);
  assert(r.out.includes("name-too-long"));
  assert(r.out.includes("control-char"));
});

Deno.test("binary: real process, stdin pipe and exit code", async () => {
  const main = new URL("../main.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
  const child = new Deno.Command(Deno.execPath(), {
    args: ["run", "--allow-read", main, "--stdin", "-t", "windows"],
    stdin: "piped",
    stdout: "piped",
    stderr: "piped",
  }).spawn();
  const w = child.stdin.getWriter();
  await w.write(new TextEncoder().encode("good.txt\nbad|name.txt\n"));
  await w.close();
  const res = await child.output();
  assertEquals(res.code, 1);
  assert(new TextDecoder().decode(res.stdout).includes("bad|name.txt"));
});
