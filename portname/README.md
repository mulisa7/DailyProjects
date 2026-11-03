# portname

Checks a folder, or a list of paths, for file names that will break when the files move to Windows, macOS or OneDrive.

## The problem

A tree that works fine on Linux can fail the moment it is copied somewhere else. Typical cases:

- a file called `report?.docx`, `12:30.txt` or `notes.` that Windows refuses or quietly renames
- a file called `con.txt` or `aux.log`, which Windows treats as a device, so Explorer cannot open or delete it
- `README.md` and `Readme.md` in the same folder, which collapse into one file on a default macOS or Windows disk
- a path that is fine on its own but passes 260 characters once it sits under `C:\Users\you\OneDrive\...`
- OneDrive sync stopping on `~$budget.xlsx`, `desktop.ini` or a leading space

The usual symptom is a sync client or an archive extractor failing halfway, with an error that names one file at a time.

## What it does

portname lists every name in a tree that would fail on the targets you pick, says why, and suggests a safe replacement. It reads names only. It never renames, moves or opens a file.

Checks, by target:

| Check | windows | macos | onedrive |
|-------|:-------:|:-----:|:--------:|
| illegal characters (`< > : " \ \| ? *`) | yes | `:` only | yes |
| control characters | yes | | yes |
| reserved device names (`CON`, `NUL`, `COM1`...) | yes | | yes |
| trailing dot or space | yes | | yes |
| leading space | | | yes |
| `desktop.ini`, `.lock`, `~$...`, `_vti_` | | | yes |
| name longer than 255 | UTF-16 units | UTF-8 bytes | UTF-16 units |
| path length | 260 (configurable) | | 400 |
| siblings that differ only by case | yes | yes | yes |
| siblings that differ only by Unicode normalization | | yes | |

A bad folder name is reported once, not once per file inside it.

## Install

Needs [Deno](https://deno.com) 2.x. There are no other dependencies and nothing to build.

```
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/portname
```

## Usage

Scan a folder:

```
deno run --allow-read main.ts ~/photos
deno run --allow-read main.ts ~/photos --target all
deno run --allow-read main.ts ~/photos --target windows --dest "C:\Users\sam\OneDrive\Archive"
```

Check a list of paths from stdin, for example the files in a git repo or an archive:

```
git -c core.quotepath=off ls-files | deno run --allow-read main.ts --stdin
unzip -Z1 bundle.zip | deno run --allow-read main.ts --stdin --target all
```

Example output:

```
portname: checked 5 paths for windows, macos, onedrive - 5 problems

reserved-name         docs/CON.txt
    "CON" is a reserved device name on windows/onedrive, with or without an extension
    suggest: docs/_CON.txt
illegal-char          reports/Q3: final.xlsx
    contains ":" (windows/onedrive, macos)
    suggest: reports/Q3_ final.xlsx
case-collision        src/Main.c
    "main.c" differs only by letter case, so they are the same name on case-insensitive file systems
```

Options:

| Option | Meaning |
|--------|---------|
| `-t`, `--target LIST` | `windows`, `macos`, `onedrive` or `all`, comma separated. Default `windows,macos`. |
| `--dest PATH` | Folder the files will be copied into. Its length is added to every path before the length check. |
| `--max-path N` | Windows path limit. Default 260. A path of N characters or more is flagged. |
| `--json` | JSON output with `scanned`, `targets`, `problems` and `issues`. |
| `--stdin` | Read relative paths, one per line, instead of scanning a folder. |
| `-h`, `--help` | Usage. |

Exit codes: `0` nothing found, `1` problems found, `2` bad usage, or a folder could not be read and no problems were found.

## Configuration

None. There are no environment variables or config files.

## Project structure

```
portname/
  main.ts            entry point, wires stdin/stdout to the CLI
  deno.json          test task
  src/checks.ts      the rules, suggestions and collision detection (pure functions)
  src/cli.ts         argument parsing, output formatting, exit codes
  src/walk.ts        folder listing (symlinks are listed, not followed)
  tests/             checks_test.ts, cli_test.ts, assert.ts
```

## Tests

```
cd portname
deno task test
```

41 tests cover each rule on both sides of its boundary, suggestions re-checked against the rules, collisions, path length with and without `--dest`, empty and malformed input, every usage error, scanning real temp folders, and one run of the real binary with piped stdin. The assertions are a small local file so the tests need no network.

## Limitations

- It checks names against rules written down from documentation. It does not ask a real Windows, macOS or OneDrive installation, so a rule can be missing or out of date. OneDrive's rules in particular change over time.
- Case and normalization collisions assume a case-insensitive disk. A macOS volume formatted case-sensitive does not have that problem.
- Normalization checking uses the JavaScript runtime's NFD form, which follows current Unicode, not the older table HFS+ used.
- The 260-character check counts characters, not bytes. The Windows 10+ long path setting lifts the limit for programs that opt in; portname does not know whether yours do.
- Suggestions only fix the last part of a path. If a parent folder is also renamed, the suggested path is stale. Two suggestions can also end up equal, for example `a?` and `a*` both become `a_`.
- File names that are not valid UTF-8 on Linux are not handled specially; what you see depends on how the runtime decodes them.
- Tests ran on Windows 11 only. Because Windows cannot create files named `CON` or `a?`, the bad-name cases are tested through `--stdin` and the pure functions, and folder scanning is tested with legal names. Scanning a tree that really contains such files on Linux was not tested.
- The unreadable-folder path (permission denied) is implemented but has no automated test.

## Future improvements

- An opt-in `--apply` that renames, with a dry run first and collision-safe suffixes.
- Linux and FAT32/exFAT as targets.
- Read `.zip` and `.tar` listings directly instead of through `unzip -Z1`.
- Show the deepest too-long paths as well as the shallowest.
