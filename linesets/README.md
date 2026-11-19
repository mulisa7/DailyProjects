# linesets

Set operations on the lines of text files: which lines are in every file, which are in only one, which are in the first file but nowhere else.

## The problem

Comparing lists (email lists, hostnames, SKUs, usernames) is a daily chore. `comm` handles two files but needs both sorted and works on exactly two. `sort | uniq -d` works for several files only if no file has internal duplicates, otherwise a line repeated in one file looks like it is in two. Case and stray whitespace make equal entries look different, and none of these tools tell you which file a line came from.

## The solution

A small Go command that reads any number of files (or stdin), treats each file as a set of lines, and prints the lines that match one of five operations. Input does not need to be sorted, duplicates inside one file count once, and output keeps first-seen order unless you ask for sorting.

## Features

- `union`, `common`, `only`, `diff`, `min` operations over 1 to N files
- `-i` ignore case, `-t` trim and collapse whitespace (output shows the first spelling seen)
- `-c` prefix the number of files containing each line, `-w` append which files (1-based)
- `-s` sort output, `-b` keep blank lines (skipped by default)
- Handles CRLF, a UTF-8 BOM at the start of a file, a missing final newline, and very long lines
- `-` reads stdin (once)
- Exit codes: 0 output produced, 1 no matching lines, 2 usage or file error

## Install

Needs Go 1.21 or newer.

```
cd linesets
go build -o linesets .
```

## Usage

```
linesets [flags] <op> FILE [FILE...]
```

Flags can go before or after the operation.

| op | prints |
|----|--------|
| union | lines in any file |
| common | lines in every file |
| only | lines in exactly one file (`-f N` limits to file N) |
| diff | lines in the first file and no other |
| min | lines in at least `-k` files (default 2) |

Examples:

```
linesets -i -t common signups.txt paid.txt        # signed up and paid
linesets -i diff current.txt old.txt               # new since last time
linesets -c -w min -k 2 a.txt b.txt c.txt          # in at least two of three
cat hosts.txt | linesets only -f 2 prod.txt -      # only in stdin
```

`common`, `only` and `diff` need at least two files; `union` and `min` accept one.

## Configuration

None. No environment variables or config files.

## Project structure

```
main.go            CLI: flags, file loading, output, exit codes
main_test.go       CLI tests (run() with temp files and fake stdin)
sets/sets.go       Reading, normalising, building and filtering entries
sets/sets_test.go  Unit tests for the logic
```

## Tests

```
go test ./...
```

The tests cover each operation, unsorted input, repeats within a file, case and whitespace normalisation, blank lines, CRLF, BOM, empty files, a 200 KB line, unknown operations, bad flags, missing files, out-of-range `-f`/`-k`, and stdin use.

## Limitations

- Whole files are held in memory; fine for lists with millions of lines, not for huge logs.
- Matching is exact after the optional normalisation. There is no fuzzy matching, so "Jon Smith" and "John Smith" are different.
- Case folding uses Go's `strings.ToLower`, so locale-specific rules (Turkish dotless i) are not applied.
- Only lines are compared; there is no column or CSV field mode.
- Tested on Linux only. Windows paths and terminals were not tried.

## Future improvements

- Compare on a chosen CSV column or regex capture group
- Optional fuzzy matching with an edit-distance threshold
- Streaming mode for very large inputs
