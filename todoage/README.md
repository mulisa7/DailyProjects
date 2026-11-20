# todoage

List the TODO, FIXME, HACK and XXX comments in a git repository, oldest first, with how long each one has been sitting there.

## The problem

Every codebase collects "TODO" comments. Grep finds them, but it cannot tell you whether a TODO was written last week or four years ago, and the old ones are the ones worth deciding about: do it, or delete the comment. `git blame` has the dates, but combining the two by hand for a whole repo is tedious.

## The solution

`todoage` finds the tagged comments in every non-ignored text file, runs `git blame` on the files that have hits, and prints each item with its age and the author of the line. Nothing else is installed or contacted; it only calls your local `git`.

## Features

- Age of each item from the commit that last touched that line
- `--older-than 6m` to show only stale items, `--fail` to exit 1 if any exist (usable as a CI check)
- Sort by age (default) or by file and line
- Custom tags with `--tags`
- JSON output with `--json`
- Respects `.gitignore`, includes untracked files, skips binary and non-UTF-8 files
- Uncommitted lines are shown as `new`

## Install

Needs Rust (2021 edition, tested with 1.97) and git.

```
cd todoage
cargo build --release
# binary: target/release/todoage
```

## Usage

```
todoage [PATH] [options]

  --older-than AGE   only show items at least AGE old (90d, 12w, 6m, 2y, or bare days)
  --tags A,B,C       tags to look for (default TODO,FIXME,HACK,XXX)
  --sort age|file    oldest first (default) or by file and line
  --json             machine-readable output
  --fail             exit 1 if any item is shown
  --now UNIXTIME     override the current time (used by the tests)
```

Example:

```
$ todoage ~/src/myapp --older-than 1y
  2.3y  TODO   src/db.rs:41  retry on deadlock  [Sam Ortiz]
   14m  FIXME  src/api.rs:9  handle empty body  [Priya N]
2 item(s)
```

Months are counted as 30 days and years as 365. Exit codes: 0 normal, 1 items found with `--fail`, 2 for bad arguments or when PATH is not in a git repository.

## Configuration

None. There are no environment variables or config files.

## Project structure

```
src/lib.rs      tag detection, blame parsing, age maths, output formatting (unit tested)
src/main.rs     argument parsing, calls to git, sorting and exit codes
tests/cli.rs    end-to-end tests that build small git repos with fixed commit dates
```

## Tests

```
cd todoage
cargo test
```

The unit tests cover duration parsing (including bad and overflowing values), tag matching, blame parsing and JSON escaping. The integration tests create temporary repositories with backdated commits and check ages, filters, exit codes, uncommitted and untracked files, an empty repository, a binary file, and error cases.

## Limitations

- A tag counts only if it is upper case and appears after a comment marker on the same line. Multi-line block comments where the tag is on a line without a marker are missed unless that line starts with `*`.
- Comment markers inside string literals are not recognised, so `"# TODO"` in a string is reported.
- Age is the date of the last commit that changed the line. Reformatting or moving a line resets it. `git blame` options such as `-w` or `-M` are not used.
- Files are blamed one at a time, so very large repositories with thousands of hits will be slow.
- Only tested on Linux with git 2.43. Windows and macOS were not tried. Non-UTF-8 text files are skipped.

## Future improvements

- Optional `-w -M -C` blame flags
- Group the output by author or directory
- Read issue references like `TODO(#123)` and flag items with no reference
- An ignore list of paths
