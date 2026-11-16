# settleup

Takes a plain text list of shared expenses and prints the smallest set of payments that settles everyone.

## The problem

Housemates, trip groups and clubs share costs that different people pay for. Apps like Splitwise handle this, but they need accounts and a phone, and people regularly ask for something scriptable, local and private. The usual fallback is a spreadsheet with a hand-built "who owes whom" formula, and it falls over with unequal shares or when someone has already paid part of their debt back.

## The solution

You write one line per expense in a text file. settleup works out each person's net balance in whole cents, then finds the fewest payments that clear every balance.

## Features

- Equal splits, weighted shares (`Alice*2`) and exact amounts (`Alice=10`), mixed on one line. Exact amounts are taken off first and the rest is shared among the others.
- Payments already made (`Bob sent Alice 20`) are counted.
- Integer cents throughout. Uneven splits (100.00 between three people) are rounded with the largest remainder method, so the shares always add up exactly.
- Minimal payment count: people with a balance are split into the largest number of groups that each net to zero, and a group of k people needs k-1 payments. This is exact for up to 18 people with a non-zero balance. Above that it falls back to a single greedy pass and says so.
- Errors name the line number. Nothing is printed if any line is invalid.
- `--balances` shows each net balance, `--json` gives machine readable output.
- Names can contain letters in any script, digits, `_ . ' -`.

## Install

Needs Node.js 18 or newer. No dependencies.

```
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/settleup
```

## Usage

```
node src/cli.js examples/trip.txt --balances
cat expenses.txt | node src/cli.js -
```

Input format:

```
# comments and blank lines are ignored
Alice paid 60 dinner: Alice Bob Carol          equal split
Bob paid 90 rent: Alice*2 Bob Carol            Alice has two shares
Alice paid 30 taxi: Alice=10 Bob=20            exact amounts
Bob sent Alice 20                              money already handed over
```

Amounts are digits with up to two decimals; a leading `$`, `€` or `£` is allowed. Names after the colon can be separated by spaces or commas.

Exit codes: 0 success, 1 invalid input or unreadable file, 2 bad command line.

## Configuration

None. There are no environment variables or config files.

## Project structure

```
src/money.js    amount parsing, formatting, remainder-safe splitting
src/parse.js    the line format
src/settle.js   balances and the minimal-payment search
src/cli.js      command line wrapper
test/           node:test unit tests
examples/       sample input with invented names
```

## Tests

```
npm test
```

(or `node --test test/*.test.js`). 21 tests cover amount parsing, rounding, each split type, comment/BOM/CRLF handling, unicode names, every parse error, over- and under-assigned exact amounts, group detection, balances clearing, empty input, the greedy fallback, JSON output and exit codes.

## Limitations

- One currency, two decimal places. No conversion.
- The minimal search is exponential in the number of people with a balance (2^n memory, about 3^n time), which is why it stops at 18. The greedy fallback is correct but not always minimal.
- "Fewest payments" ignores who is friends with whom or who would rather pay whom; it only counts transfers.
- Names are case sensitive: `alice` and `Alice` are different people.
- Tested with unit tests and the sample file only. Not tested against large real-world files, and the 18-person boundary was only checked for correctness of the result, not for timing.

## Future improvements

- A flag to keep payments between specific people (for example couples treated as one).
- Percent splits.
- Per-category totals.
