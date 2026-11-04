# jsonshape

## Problem
You get a large JSON or NDJSON export (an API dump, a log file, a database export) and want to know what is in it before writing any code: which keys exist, which are sometimes missing, which have mixed types, how big the numbers get. `jq` can answer each of those, but only if you already know the question to ask.

## Solution
`jsonshape` reads the file and prints one line per key path with the types seen, how often the key is present, number ranges, string lengths and an example value.

## Features
- Reads a single JSON document or NDJSON (one record per line); format is auto-detected.
- Reads from a file or stdin.
- Reports mixed types (`integer 1 | null 1  (mixed)`), missing keys (`present 1/2 (50%)`), number min/max, string length and array size ranges.
- `--max-depth` to limit how deep it descends.
- `--json` for machine-readable output.
- Exit codes: 0 ok, 1 unreadable or invalid input, 2 bad usage.
- Standard library only.

## Install and usage
Needs Python 3.8 or newer. No install; run the script.

```
python3 jsonshape.py data.json
cat records.ndjson | python3 jsonshape.py -
python3 jsonshape.py data.json --max-depth 3
python3 jsonshape.py data.json --json
```

Example output:

```
2 records
$: object
  id: integer, range 1..2
  tags: array, items 0..2
    []: string, length 1..1, e.g. "a"
  user: object
    name: string, length 2..3, e.g. "Ann"
    age: integer 1 | null 1  (mixed), range 30..30
  note: string, present 1/2 (50%), length 2..2, e.g. "hi"
```

## Configuration
None. No environment variables.

## Project structure
- `jsonshape.py` - the tool (analysis functions plus `main`)
- `test_jsonshape.py` - unit tests

## Tests
```
cd jsonshape
python3 -m unittest -v
```

## Limitations
- The whole file is read into memory, so it is not suited to multi-gigabyte files.
- Arrays are merged: every element contributes to one `[]` entry. Position-specific shapes (tuples) are not distinguished.
- Presence is relative to the parent object. For keys under arrays of objects the percentage is measured against all objects seen at that path.
- Key names containing `.` are indistinguishable from nested keys in the path label.
- A file that is invalid as one document is tried as NDJSON; a pretty-printed concatenation of several documents is not supported.
- Only tested with small hand-written inputs and a few edge cases, not with real large datasets; no performance testing.

## Future improvements
- Streaming mode for large NDJSON.
- Emit a JSON Schema.
- Sample-based mode for huge files.
