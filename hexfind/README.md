# hexfind

A command-line tool for searching binary files by structure rather than by a fixed byte string.

## The problem

Hex editors and `grep -P` can find a magic number, but they are awkward when what you want is "this header, followed by a 16-bit length field that is under 4096". People on Hacker News asked for a hex editor with "fuzzy" search over header fields, and it is a common need when poking at file formats, firmware dumps or network captures: the magic bytes show up many times by chance and only some of those hits have sensible field values.

## The solution

`hexfind` takes a pattern made of literal bytes, wildcards and typed integer fields with constraints, and prints every offset where the whole pattern matches, along with the decoded field values. Standard library only.

## Features

- Literal bytes (`50 4B 03 04` or `504B0304`) and ASCII text (`str(PK)`).
- Wildcards: `??` for one byte, `*N` for N bytes.
- Integer fields `u8 u16 u32 u64 i8 i16 i32 i64`, with `le` or `be` for anything wider than a byte.
- Constraints on fields: `==`, `=`, `!=`, `<`, `<=`, `>`, `>=`, a range `=5..10`, or a list `=1|20`. Numbers can be decimal or `0x` hex.
- Names for fields and wildcards (`size:u16le<4096`) so the values appear in the output.
- Options for alignment, start and end offsets, maximum matches, non-overlapping matches, count only, offsets only, and JSON output.
- Several files per run; filenames are prefixed to each line when there is more than one.
- Files are memory mapped, so large files are not read into memory up front.

## Install and use

Requires Python 3.8 or newer. No dependencies.

```
cd hexfind
python hexfind.py 'PATTERN' file [file ...]
```

Examples:

```
# ZIP local file headers where the file name length field is at least 1
python hexfind.py '50 4B 03 04 *2 *20 fn:u16le>=1 extra:u16le' archive.zip

# every PNG signature, offsets only
python hexfind.py -o '89 str(PNG) 0D 0A 1A 0A' dump.bin

# 4-byte aligned length-prefixed records whose length is 8 to 64
python hexfind.py --align 4 'len:u32be=8..64 str(REC)' firmware.img
```

Output is one line per match: offset, the matched bytes (first 24 shown), then `name=value` for each integer field or named element. Wildcard values print as hex.

Quote the pattern so the shell passes it as one argument. Offsets are zero-based from the start of the file.

Exit codes: 0 if anything matched, 1 if nothing matched, 2 for a bad pattern, bad option or unreadable file.

## Configuration

None. No environment variables.

## Project structure

- `hexfind.py` - pattern parser, matcher and command-line entry point
- `tests/test_hexfind.py` - unit and CLI tests

## Tests

```
cd hexfind
python -m unittest discover -s tests
```

32 tests cover pattern parsing and its error cases, both endiannesses, signed fields, ranges and lists, overlapping matches, matches at the very end of the data, patterns longer than the data, empty files, missing files, directories, alignment, start and end limits, multiple files with one unreadable, JSON output and exit codes.

## Limitations

- Patterns have a fixed length. There is no "zero or more" or variable-length field, so a length field cannot be used to jump to the next element.
- No floating point fields, bit fields, or comparisons between two fields.
- Constraints compare a field to constants only.
- With a pattern that starts with a wildcard or a field, every offset is tried, which is slow on multi-gigabyte files. A pattern that starts with literal bytes uses a fast scan for the first literal.
- Tested on Windows with Python 3.15 only. Not tested on files over a few megabytes, or on Linux and macOS.

## Future improvements

- Variable-length elements driven by an earlier length field.
- Field-to-field comparisons (`end >= start`).
- A hex dump with context around each match.
