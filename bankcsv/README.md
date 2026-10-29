# bankcsv

Turn CSV exports from different banks into one tidy layout, tag spending with your own rules, and see where the money went each month.

## Problem

Every bank exports statements differently. One has a single signed `Amount` column, another has separate `Debit` and `Credit` columns. Dates are `13/04/2025` in one file and `2025-04-13` in another, amounts come as `1 234,50`, `(45.00)` or `45.00-`, and some files start with a few lines of account details before the header. If you hold accounts at more than one bank, adding it all up in a spreadsheet means a lot of manual clean-up every month.

## Solution

`bankcsv` finds the header row, works out which columns are the date, description, amount (or debit and credit) and balance, parses the numbers and dates, and writes one consistent CSV. A small rules file assigns categories, and `summary` prints monthly money in, money out and spending by category. Everything runs locally; your statements are never uploaded.

## Features

- Detects delimiter (`,` `;` tab `|`) and encoding (UTF-8 or Windows cp1252)
- Skips preamble lines and finds the header by common column names
- Single amount column, or debit and credit columns
- Amount formats: `1,234.50`, `1.234,50`, `1 234,50`, `R1 234.50`, `(45.00)`, `45.00-`, `45.00 DR`, `45.00 CR`
- Day-first or month-first dates, inferred from the data when possible, with a warning when it can't tell
- Category rules in a plain text file, first match wins
- Monthly summary plus the biggest uncategorised spending, so you know which rules to add next
- `--map date=0,description=2,amount=3` for files whose headers it does not recognise
- Money is handled with `Decimal`, never floats
- Standard library only

## Installation

Python 3.8+. Nothing to install:

```bash
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/bankcsv
```

## Usage

```bash
# one tidy file from several banks
python bankcsv.py normalize sample/bank_a.csv sample/bank_b.csv --rules sample/rules.txt -o all.csv

# monthly summary
python bankcsv.py summary sample/bank_a.csv sample/bank_b.csv --rules sample/rules.txt
```

Output of the second command on the included (made-up) sample files:

```
2025-04   in    20,000.00   out     2,001.55   net    17,998.45
    Groceries                  842.15
    Transport                  650.00
    Uncategorised              310.40
    Subscriptions              199.00
2025-05   in    20,000.00   out       597.90   net    19,402.10
    Groceries                  412.60
    Transport                  185.30

Biggest uncategorised spending (add rules for these):
          310.40  MYSTERY SHOP 22
```

Options for both commands:

| Option | Meaning |
|--------|---------|
| `--rules FILE` | category rules |
| `--map SPEC` | manual column numbers, counting from 0 |
| `--dayfirst` / `--monthfirst` | force how `03/04/2025` is read |
| `--invert` | flip signs, for exports that show spending as positive (some card statements) |
| `-o FILE` | (normalize) write to a file instead of the terminal |

Rules file format, one category per line:

```
# category: keyword, keyword
Groceries: checkers, pick n pay
Transport: engen, uber
```

Matching ignores case and looks anywhere in the description.

Exit codes: `0` ok, `2` bad input or a column mapping that doesn't fit the data. Rows that can't be read (for example a "Total" line at the bottom) are skipped with a warning on stderr; if more than half the rows fail, it stops instead of producing nonsense.

## Configuration

None. No environment variables, no network.

## Project structure

```
bankcsv.py         the tool
test_bankcsv.py    unit tests
sample/            made-up statements and rules for trying it out
```

## Testing

```bash
python -m unittest -v
```

The sample files and test fixtures are invented. The tool has not been checked against real exports from any particular bank, so expect to need `--map` or an extra header alias for some.

## Limitations

- `1,234` is read as one thousand two hundred and thirty-four, and `12,5` as 12.5; a single comma followed by exactly three digits is always treated as a thousands separator.
- No duplicate detection if two statements overlap. Identical transactions on the same day are legitimate, so it never guesses.
- No PDF support.

## Future improvements

- Optional duplicate removal for overlapping statement periods
- Export the summary as CSV
- Budget limits per category with a warning when exceeded

## License

MIT, see the repository root.
