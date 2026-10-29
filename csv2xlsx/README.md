# csv2xlsx

Convert a CSV to a proper `.xlsx` without Excel mangling the accents or cramming every column into column A.

## Problem

Double-click a CSV and Excel guesses. Save it from a Mac or a script as UTF-8 and `é` turns into `Ã©`. Open a file exported from a system that uses `;` and everything lands in one column, because Excel uses the delimiter of your regional settings (commonly `;` wherever the decimal mark is a comma). Ids like `007` lose their zeros and long numbers turn into `1.23E+15`.

## Solution

`csv2xlsx` works out the encoding and delimiter itself and writes a real Excel workbook, so there is nothing left for Excel to guess. Numbers become numbers; ids with leading zeros and anything over 15 digits stay text.

## Features

- Encoding detection: UTF-8 (with or without BOM), UTF-16, then cp1252, then latin-1
- Delimiter detection for `,` `;` tab and `|`, ignoring commas inside quoted fields
- `--decimal ,` for data like `1,5`
- Bold, frozen header row and sensible column widths (`--no-header-style` to skip)
- Quoted fields, embedded newlines, ragged rows
- Refuses to overwrite an existing file unless `--force`
- Checks Excel's limits (rows, columns, 32,767 chars per cell)
- Standard library only

## Installation

Python 3.8+. Nothing to install:

```bash
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/csv2xlsx
```

## Usage

```bash
python csv2xlsx.py export.csv                       # writes export.xlsx
python csv2xlsx.py export.csv -o report.xlsx
python csv2xlsx.py data.csv --decimal ,             # values like 1,5
python csv2xlsx.py odd.csv --encoding cp1252 --delimiter ";"
```

It prints what it detected so you can check it guessed right:

```
read as cp1252, delimiter ';', 1204 rows x 7 cols -> export.xlsx
```

Exit codes: `0` ok, `1` nothing written (file exists, limits, write failure), `2` bad input.

## Configuration

None. No environment variables, no network.

## Project structure

```
csv2xlsx.py        CLI: decoding, delimiter detection, xlsx writer
test_csv2xlsx.py   unit tests
```

The workbook is written by hand (zip of a few XML parts), which is the part worth reading if you want to see how `.xlsx` is put together.

## Testing

```bash
python -m unittest -v
```

One test reads the output back with `openpyxl` when it is installed and is skipped otherwise. The tests were not run against Excel itself.

## Limitations

- Dates stay as text; there is no date inference.
- Single sheet only. Thousands separators (`1,000.50`) stay text.
- The whole file is read into memory.

## Future improvements

- Optional date detection with a format flag
- Several CSVs into one workbook, one sheet each
- Streaming for very large files

## License

MIT, see the repository root.
