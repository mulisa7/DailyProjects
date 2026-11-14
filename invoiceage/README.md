# invoiceage

## Problem
Freelancers and small shops often track invoices in a spreadsheet. Working out who is overdue, by how long, and writing the "gentle nudge" email each time is tedious, so reminders get put off. Full accounting software feels like too much for a handful of invoices.

## Solution
A small command line tool. Point it at a CSV of invoices and it prints an aging report (not due, 1-30, 31-60, 61-90, 90+ days late), overdue totals per client, and optionally plain-text reminder drafts whose tone gets firmer the later the invoice is.

## Features
- Aging buckets with counts and totals, using exact decimal arithmetic
- Overdue breakdown by client, largest first, with days late per invoice
- Reminder drafts grouped per client (friendly up to 14 days, firm up to 45, final after that)
- Paid invoices (any value in the paid column) are ignored
- Flexible column names (`Customer`, `Total`, `due_date`, ...), UTF-8 BOM, `$ € £`, thousands commas, `(50.00)` negatives, `YYYY-MM-DD` and `DD/MM/YYYY` dates
- Bad rows are skipped with a warning on stderr and a line number
- Reads from a file or stdin (`-`)

## Install
Needs Python 3.8 or newer. No dependencies.

    git clone https://github.com/mulisa7/DailyProjects
    cd DailyProjects/invoiceage

## Usage
    python3 invoiceage.py examples/invoices.csv
    python3 invoiceage.py examples/invoices.csv --today 2026-11-14
    python3 invoiceage.py invoices.csv --reminders --sender "Sam"
    cat invoices.csv | python3 invoiceage.py -

Required columns: invoice, client, amount, due. Optional: paid.

Exit codes: 0 nothing overdue, 1 something overdue, 2 unreadable input or bad arguments, 3 nothing overdue but some rows were skipped.

## Configuration
None. The bucket edges and tone thresholds are constants in `invoiceage.py` (`BUCKETS` and `tone`).

## Project structure
    invoiceage.py            the whole tool
    tests/test_invoiceage.py unit tests
    examples/invoices.csv    invented sample data

## Tests
    python3 -m unittest discover -s tests

## Limitations
- Amounts are summed per number as written; there is no currency handling, so mixed currencies are added together.
- Dates are `YYYY-MM-DD` or `DD/MM/YYYY` only; `MM/DD/YYYY` is not supported.
- Reminders are only printed. Nothing is emailed.
- Partial payments are not modelled; put the remaining balance in the amount column.
- Tested with the unit tests and the sample file only, not with real exports from accounting tools.

## Future improvements
- Configurable buckets and reminder wording from a template file
- Per-currency totals
- Optional CSV or JSON output
