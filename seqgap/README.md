# seqgap

## The problem

Invoice, credit note and cheque numbers are supposed to run without holes. Accountants and tax auditors ask about missing numbers, and duplicates usually mean a mistake. Checking this by hand in a spreadsheet is slow once a year has a few thousand rows, and it gets harder when there are several series mixed together (INV-2023-..., INV-2024-..., CN-...).

## The solution

`seqgap` reads a list of identifiers, splits each one around its last run of digits, groups identifiers that share the same text around the number into a series, and reports for each series the missing numbers, duplicates, numbers that appear out of order, and inconsistent zero padding.

## Features

- Plain list (one identifier per line) or one column of a CSV/TSV file, selected by position or header name
- Several series at once: `INV-2023-0001` and `INV-2024-0001` are tracked separately
- Missing numbers shown as ranges, so a gap of a million numbers is one line
- Duplicates with the line numbers where they appear
- Numbers lower than the one before them in the file (off by default with `-no-order`)
- Zero padding that changes between numbers of the same length (`A-001` next to `A-03`)
- `-json` output; exit code 0 for clean, 1 for findings, 2 for bad input or usage
- No dependencies beyond the Go standard library

## Install

Needs Go 1.21 or newer.

```
cd seqgap
go build -o seqgap .
```

## Usage

```
seqgap [flags] [file]
```

If `file` is omitted or is `-`, standard input is read.

```
# one identifier per line
seqgap invoices.txt

# column 2 of a CSV with a header row, by name
seqgap -header -column number export.csv

# semicolon or tab separated
seqgap -column 1 -delimiter ';' export.csv
seqgap -header -column id -delimiter '\t' export.tsv

# pipe from another tool
cut -d, -f3 ledger.csv | seqgap -no-order
```

Example output:

```
INV-#  5 entries, 1 to 5
  missing 3
  duplicate 5 on lines 3, 4
  out of order: line 5 (INV-0004) comes after 5
```

`INV-#` means the text before the number is `INV-` and nothing follows it. Line numbers are lines of the file; with a CSV they count the header row, so they match the row numbers in a spreadsheet.

## Flags

| Flag | Meaning |
|------|---------|
| `-column` | CSV column: a 1-based number, or a header name (needs `-header`) |
| `-header` | first CSV row is a header |
| `-delimiter` | CSV delimiter, default `,`; use `\t` for tab |
| `-ignore-case` | treat `INV-1` and `inv-1` as one series |
| `-no-order` | skip the out-of-order check (useful for sorted exports where order is meaningless) |
| `-json` | machine readable output |

No environment variables or configuration files are used.

## Project structure

```
seqgap/
  main.go         flags, exit codes, text output
  seqgap.go       parsing, CSV reading, series analysis
  seqgap_test.go  tests
  go.mod
```

## Tests

```
cd seqgap
go test ./...
```

The tests cover parsing, gaps and ranges, duplicates, ordering, separate series, case handling, padding, CSV columns by name and number, short and empty rows, other delimiters, a very large gap, and the command-line exit codes and JSON output.

## Limitations

- Only the last run of digits in an identifier is treated as the number. `2024-INV-5` is read as prefix `2024-INV-`, number 5. A date embedded after the number, such as `INV-5-2024`, makes `2024` the number.
- Numbers must fit in an unsigned 64-bit integer; longer ones are skipped with a warning.
- A series that legitimately restarts (for example each month) will show a large gap or duplicates; split the input by period first.
- Gaps are only found between the lowest and highest number present. Numbers missing before the first or after the last cannot be known.
- Input is read fully into memory. Not tested on files of many millions of rows.
- Not tested with encodings other than UTF-8 (a leading BOM is handled).

## Possible improvements

- An option to give the expected start and end of a series
- Optional gaps allowed by step (cheque books issued in blocks)
- Reading `.xlsx` directly
