import {
  analyze,
  countPaths,
  DEFAULT_MAX_PATH,
  DEFAULT_TARGETS,
  type Issue,
  type Options,
  parseTargets,
  type Target,
} from "./checks.ts";
import { listTree } from "./walk.ts";

export interface IO {
  out: (text: string) => void;
  err: (text: string) => void;
  readStdin: () => Promise<string>;
}

export const USAGE = `usage: portname [options] <folder>
       portname [options] --stdin

Checks file names for problems on Windows, macOS and OneDrive.
With --stdin, reads one relative path per line instead of scanning a folder
(for example: git ls-files | portname --stdin).

options:
  -t, --target LIST   windows, macos, onedrive or all, comma separated
                      (default: windows,macos)
      --dest PATH     folder the files will be copied into; its length counts
                      towards the path limit
      --max-path N    Windows path limit (default: ${DEFAULT_MAX_PATH})
      --json          print JSON instead of text
      --stdin         read paths from standard input
  -h, --help          show this help

exit codes: 0 no problems, 1 problems found, 2 bad usage or unreadable input
`;

interface Parsed {
  folder?: string;
  stdin: boolean;
  json: boolean;
  help: boolean;
  targets: Target[];
  maxPath: number;
  dest?: string;
}

class UsageError extends Error {}

function parseArgs(args: string[]): Parsed {
  const p: Parsed = { stdin: false, json: false, help: false, targets: DEFAULT_TARGETS, maxPath: DEFAULT_MAX_PATH };
  const positional: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const value = (): string => {
      const v = args[++i];
      if (v === undefined) throw new UsageError(`${arg} needs a value`);
      return v;
    };
    switch (arg) {
      case "-h":
      case "--help":
        p.help = true;
        break;
      case "--json":
        p.json = true;
        break;
      case "--stdin":
        p.stdin = true;
        break;
      case "-t":
      case "--target":
        try {
          p.targets = parseTargets(value());
        } catch (e) {
          if (e instanceof UsageError) throw e;
          throw new UsageError((e as Error).message);
        }
        break;
      case "--dest":
        p.dest = value();
        break;
      case "--max-path": {
        const raw = value();
        const n = Number(raw);
        if (!/^\d+$/.test(raw) || n < 10) throw new UsageError(`--max-path must be a whole number of at least 10, got "${raw}"`);
        p.maxPath = n;
        break;
      }
      default:
        if (arg.startsWith("-") && arg !== "-") throw new UsageError(`unknown option ${arg}`);
        positional.push(arg);
    }
  }
  if (positional.length > 1) throw new UsageError("only one folder can be checked at a time");
  p.folder = positional[0];
  return p;
}

function formatText(issues: Issue[], scanned: number, targets: Target[]): string {
  const head = `portname: checked ${scanned} path${scanned === 1 ? "" : "s"} for ${targets.join(", ")}`;
  if (issues.length === 0) return `${head} - no problems\n`;
  const lines = [`${head} - ${issues.length} problem${issues.length === 1 ? "" : "s"}`, ""];
  for (const i of issues) {
    lines.push(`${i.kind.padEnd(22)}${i.path}`);
    lines.push(`    ${i.detail}`);
    if (i.suggestion !== null) lines.push(`    suggest: ${i.suggestion}`);
  }
  return lines.join("\n") + "\n";
}

function formatJson(issues: Issue[], scanned: number, targets: Target[]): string {
  return JSON.stringify({ scanned, targets, problems: issues.length, issues }, null, 2) + "\n";
}

export async function run(args: string[], io: IO): Promise<number> {
  let p: Parsed;
  try {
    p = parseArgs(args);
  } catch (e) {
    if (!(e instanceof UsageError)) throw e;
    io.err(`portname: ${e.message}\n\n${USAGE}`);
    return 2;
  }
  if (p.help) {
    io.out(USAGE);
    return 0;
  }
  if (p.stdin === (p.folder !== undefined)) {
    io.err(`portname: give either a folder or --stdin\n\n${USAGE}`);
    return 2;
  }

  let paths: string[];
  let unreadable: string[] = [];
  if (p.stdin) {
    paths = (await io.readStdin()).split("\n");
  } else {
    try {
      const info = await Deno.stat(p.folder!);
      if (!info.isDirectory) throw new Error("not a folder");
    } catch (e) {
      io.err(`portname: cannot use "${p.folder}": ${(e as Error).message}\n`);
      return 2;
    }
    const listing = await listTree(p.folder!);
    paths = listing.paths;
    unreadable = listing.errors;
  }

  const opts: Options = { targets: new Set(p.targets), maxPath: p.maxPath, dest: p.dest };
  const issues = analyze(paths, opts);
  const scanned = countPaths(paths);
  io.out(p.json ? formatJson(issues, scanned, p.targets) : formatText(issues, scanned, p.targets));
  for (const msg of unreadable) io.err(`portname: warning: ${msg}\n`);

  if (issues.length > 0) return 1;
  return unreadable.length > 0 ? 2 : 0;
}
