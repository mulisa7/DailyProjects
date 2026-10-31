# dirdiff

## Problem

After copying a folder to a backup drive, restoring a backup, or tidying a photo library, it is hard to tell whether the two copies really match. Comparing by file name and modification time misses silent corruption, and it reports a renamed or moved file as one deletion plus one new file, which buries the real differences in noise.

## Solution

`dirdiff` compares two folders by file content (SHA-256) and sorts every file into one of: identical, changed (same path, different content), moved or renamed (same content, different path), only in A, or only in B. The exit code says whether the folders match, so it can be used in scripts.

## Features

- Content comparison, not timestamps
- Detects moves and renames by matching content between the "only in A" and "only in B" lists
- Files at the same path are hashed only when their sizes are equal; move detection only hashes files whose size appears on both sides, so most unrelated files are never read
- Plain text or `--json` output
- `--ignore NAME` to skip files or folders such as `.git` or `Thumbs.db` at any depth
- Symlinks are counted and skipped, never followed
- Read-only: it never modifies either folder
- No dependencies; SHA-256 is implemented in the project and checked against the standard test vectors

## Install

Requires a Rust toolchain (tested with cargo 1.97).

    cd dirdiff
    cargo build --release
    # binary: target/release/dirdiff

## Usage

    dirdiff [--json] [--ignore NAME]... <folder-a> <folder-b>

Example output:

    Changed (same path, different content) (1):
      docs/report.txt
    Moved or renamed (A -> B) (1):
      photos/img1.jpg -> archive/2020/img1.jpg
    Only in A (1):
      old-notes.txt
    Summary: 41 identical, 1 changed, 1 moved, 1 only in A, 0 only in B

Exit codes: 0 the folders match, 1 differences found, 2 error (bad arguments, missing folder, unreadable file).

## Configuration

None. There are no environment variables or config files.

## Project structure

    src/sha256.rs   streaming SHA-256
    src/lib.rs      scanning, comparison, text and JSON rendering
    src/main.rs     argument parsing and exit codes
    tests/cli.rs    tests that run the built binary

## Tests

    cd dirdiff
    cargo test

26 tests: SHA-256 vectors (empty, "abc", two-block message, one million "a" fed in odd chunk sizes, padding edge lengths), identical and empty folders, changed content with equal and unequal size, moves, same-size non-moves, duplicate files, empty files, ignore rules, symlink loops, Unicode names, JSON escaping, and the CLI exit codes for bad usage, missing folders and a file given instead of a folder.

## Limitations

- Only tested on Linux. Windows path handling is written to be portable but was not run.
- File contents only. Permissions, ownership, timestamps and extended attributes are not compared.
- Empty directories are not reported, since only files are tracked.
- If one content exists several times on one side, copies are paired one-to-one in path order, so which duplicate counts as the "moved" one is arbitrary.
- Files are hashed one at a time; very large trees on slow disks will be slow.
- Files that change while the program runs may give inconsistent results.
- File names that are not valid UTF-8 are shown with replacement characters.
- Unreadable files make the run exit with 2 and are listed under Errors; the rest of the comparison is still printed.

## Future improvements

- Parallel hashing
- Optional comparison of modification times and permissions
- A `--summary` mode and an option to print only one category
- Optionally follow symlinks
