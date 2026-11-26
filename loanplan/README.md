# loanplan

## The problem

Online overpayment calculators tend to hide the schedule, round oddly, or want an email address. Spreadsheet versions break when you add a one-off lump sum, and Goal Seek does not converge on whole monthly payments. The related question, "is this refinance worth the closing costs, and when do I break even?", is usually answered with a rough "costs divided by monthly saving" that ignores the remaining balance.

## The solution

A small command line tool that amortizes a fixed-rate loan month by month in exact decimal arithmetic, shows what extra monthly payments and lump sums save, and works out the refinance break-even month by comparing cash paid plus balance still owed.

## Features

- `plan`: monthly payment, total interest, payoff time, with optional `--extra` every month and any number of `--lump AMOUNT@MONTH` payments. Reports interest saved and time saved.
- `--csv FILE` writes the whole schedule.
- `refi`: compares keeping the current loan with a new one, including closing costs. Prints total cost of each and the first month the new loan is no worse (exit code 1 if that never happens).
- Decimal money, rounded to cents each month; the last payment absorbs rounding.
- Clear errors and exit code 2 for bad input.

## Install and usage

Needs Python 3.8 or newer. No dependencies.

```
cd loanplan
python3 loanplan.py plan --principal 200000 --rate 6.5 --years 30 --extra 200 --lump 5000@12
python3 loanplan.py plan --principal 15000 --rate 7 --months 48 --csv schedule.csv
python3 loanplan.py refi --balance 200000 --old-rate 7.5 --old-months-left 300 \
    --new-rate 5.5 --new-months 300 --costs 4000
```

Sample output of the first `refi` example:

```
Current loan: payment 1,477.98, 25 years left, total still to pay 443,396.34
New loan:     payment 1,228.17, 25 years, total to pay 372,454.14 (including 4,000.00 closing costs)
Over the full terms the new loan costs 70,942.20 less
Break-even: month 13 (1 year 1 month). ...
```

Exit codes: 0 success, 1 refinance never breaks even, 2 invalid input.

## Configuration

None. No environment variables or files are read.

## Project structure

```
loanplan.py        calculation functions and CLI
test_loanplan.py   unittest suite
```

## Tests

```
cd loanplan
python3 -m unittest -v
```

34 tests cover a known payment value, zero-rate loans, one-month loans, oversized extra payments, lump sums, refinance with and without a break-even, number parsing (commas, dollar signs, nan, negatives), CLI errors and CSV output.

## Limitations

- Fixed-rate, monthly-payment loans only. No adjustable rates, interest-only periods, daily-accrual interest or payment holidays.
- Extra payments are assumed to go entirely to principal and take effect in the month paid. Real lenders may apply them differently or charge prepayment penalties; check yours.
- The refinance comparison ignores taxes, insurance, what you could earn by investing the difference, and escrow.
- The monthly payment is checked against one published value (200,000 at 6.5% over 30 years is 1,264.14) and against internal consistency (balance reaches zero), not against a lender's statement. Lenders can differ by a few cents because of rounding rules.
- Only tested on Linux with Python 3.11.

## Future improvements

- Bi-weekly payment mode.
- Extra payments that start or stop at given months.
- Optional prepayment penalty.
- Compare several scenarios side by side.
