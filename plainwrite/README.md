# plainwrite

## Problem
Checking whether a draft is easy to read usually means pasting it into a website that wants a login, a subscription, or sends your text to a server. People keep asking for small, free, local versions of basic writing utilities.

## Solution
A readability checker with no dependencies. It computes Flesch reading ease and Flesch-Kincaid grade level, and points at sentences that are too long, use passive voice, contain filler words, or repeat a word twice in a row. It runs as a Node CLI or as a single static HTML page that works offline.

## Features
- Reading ease, grade level, average sentence length, word and sentence counts
- Flags: long sentences (default over 25 words), passive voice, filler words, repeated words
- `--markdown` strips code blocks, inline code, links, URLs and heading markers first
- `--json` output and `--max-grade N` exit code, so it can gate a docs build in CI
- Reads a file or stdin; rejects binary input

## Install and usage
Needs Node 18 or newer. No install step.

```
node cli.js essay.txt
cat notes.md | node cli.js --markdown
node cli.js --max-grade 10 README.md; echo $?
node cli.js --json --max-sentence 30 draft.txt
```

Exit codes: 0 ok, 1 grade above `--max-grade`, 2 bad usage or unreadable input.

For the web page, open `index.html` in a browser. Everything runs locally.

## Configuration
No environment variables or config files. Options are listed by `node cli.js --help`.

## Project structure
- `analyze.js` - text analysis, no DOM or Node APIs
- `cli.js` - argument parsing, formatting, exit codes
- `index.html` - minimal page using `analyze.js`
- `test/analyze.test.js` - tests

## Tests
```
cd plainwrite
node --test test/*.test.js
```

## Limitations
- English only. Syllable counting is a heuristic and is off for some words (for example "beautiful" counts as 4), so scores are approximate and best used to compare drafts, not as exact numbers.
- Passive voice detection is pattern-based: a form of "to be" followed by a word ending in -ed or a short list of irregular participles. It misses some passives and may flag adjectives such as "was tired".
- Sentence splitting knows a short list of abbreviations; unusual ones may split a sentence early.
- The HTML page was not opened in a browser during development. Only the analysis module and CLI are covered by tests.
- No suggestions for rewrites, only flags.

## Future improvements
- Highlight flagged sentences inside the text in the web page
- Per-paragraph scores
- A configurable filler word list
