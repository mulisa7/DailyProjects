# gradeneed

Work out what score you need on the remaining work in a course to finish with the grade you want.

## The problem

Syllabi give category weights (homework 20%, midterm 25%, final 40%) and often a "drop your lowest quiz" rule. Answering "what do I need on the final to get an 80?" by hand means redoing the weighted arithmetic every time a score comes in. Online calculators exist but most handle one category, ignore drop-lowest rules, or sit behind ads and sign-ups.

## The solution

A small text format describes the course, and a plain JavaScript module does the arithmetic. It runs as a command line tool or as a single static web page that works offline. Nothing is uploaded or stored.

## Features

- Weighted categories, with scores written as `8/10` or `85%`
- `drop=N` drops the lowest N scores in a category (by percentage, and never drops the last remaining score)
- Categories with no scores count as pending; the tool says what average you need across them for each target grade
- Reports "already secured" and "out of reach" instead of printing a nonsense number
- Custom targets with a `target:` line (defaults to 90, 80, 70, 60)
- Scores above 100% (extra credit) are accepted
- Comments with `#`, blank lines, and Windows line endings are fine

## Install and use

Needs Node.js 18 or newer. No dependencies.

```
cd gradeneed
node cli.js example.txt
cat myclass.txt | node cli.js -
```

Spec format:

```
# Invented sample course
Homework 20% drop=1: 8/10, 9/10, 4/10, 10/10
Quizzes 15%: 7/10, 8/10, 9/10
Midterm 25%: 72/100
Final 40%:
target: 90 80 70
```

Weights must add up to 100. Exit codes: 0 ok, 1 invalid spec, 2 usage or unreadable file.

Web page: open `index.html` in a browser and edit the text box; the result updates as you type.

## Configuration

None. No environment variables.

## Project structure

```
grade.js            parser and calculations (works in Node and in the browser)
cli.js              command line wrapper
index.html          static page using grade.js
example.txt         sample spec
test/grade.test.js  tests
```

## Tests

```
node --test test/grade.test.js
```

The tests cover normal use, drop-lowest, mixed score formats, targets that are secured or out of reach, a fully graded course, no scores at all, empty input, malformed lines, zero or negative values, duplicate categories, weights that do not total 100, and the CLI exit codes.

## Limitations

- `index.html` was not opened in a browser during development; only the logic in `grade.js` and the CLI are tested. The page is about 20 lines of glue, but treat it as unchecked.
- The pending categories share one required average; it does not suggest different scores for each one.
- A drop rule applies per category and is chosen by percentage, so categories with very different point sizes may not match how your instructor drops scores.
- No letter-grade cutoffs, rounding policies or curves. Check your syllabus for those.
- Results are an estimate; your instructor's gradebook is the one that counts.

## Future improvements

- Per-category "what if" scores
- Letter-grade cutoffs read from the spec
- Save and load multiple courses in the browser
