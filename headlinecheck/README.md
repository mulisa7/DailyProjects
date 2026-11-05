# headlinecheck

Scores news headlines for clickbait signals, as a Chrome/Edge extension that dims or labels them on the page, and as a command-line tool for files of headlines.

## The problem

People keep asking for a clickbait headline filter: headlines that are a vague question, promise a reveal without giving it, or shout. The existing options I could find mostly target YouTube thumbnails, or are black-box classifiers that give no reason for a verdict. I wanted something whose decisions you can read and argue with.

## The solution

A small rule-based scorer. Each headline gets points for specific, named signals, and the reasons are kept so you can see why it was flagged (the tooltip on a marked headline lists them). No network calls, no model, no data leaves the browser.

## Features

- Signals: curiosity-gap phrases ("you won't believe", "here's why"), yes/no question headlines, stacked punctuation, listicle openers, dangling "this/these" openers, emotive words, combat verbs ("slams", "destroys"), shouting in capitals.
- Acronyms like NASA or FBI do not count as shouting.
- A concrete figure (percentage, currency amount, year) takes a point off, so "Minister slams deal worth R40 million" scores lower than "Minister slams deal".
- Levels: below 2 is low, 2 to 3.9 medium, 4 and above high.
- Extension: threshold, dim or badge mode, and a list of sites to skip, set on the options page. Headlines added to the page later are picked up.
- CLI: reads files or stdin, `--min`, `--json`, `--fail-on` for use in scripts.

## Install and usage

Requires Node 18 or newer for the CLI and tests. No dependencies.

CLI:

```
node cli.js headlines.txt
echo "You won't believe what happened next" | node cli.js --json
node cli.js --fail-on 4 headlines.txt   # exit status 1 if any headline scores 4 or more
```

Output looks like:

```
 5.5  high    SHOCKING: Minister DESTROYS critic in epic reply!!
                - stacked punctuation
                - emotive words: shocking, epic
                - combat verb: "destroys"
                - words in capitals: SHOCKING, DESTROYS
```

Exit status: 0 ok, 1 `--fail-on` threshold reached, 2 bad usage or unreadable or empty input.

Extension (unpacked):

1. Open `chrome://extensions` (or `edge://extensions`) and turn on developer mode.
2. Choose "Load unpacked" and select the `extension` folder.
3. Open the extension's options to change the threshold or mode.

To try the same scripts without installing anything, serve the folder with any static server and open `demo/index.html`, for example `python -m http.server` from this directory and then `/demo/index.html`.

## Configuration

Stored in `chrome.storage.sync`:

| Key | Default | Meaning |
| --- | --- | --- |
| `threshold` | 4 | Minimum score to mark, between 0.5 and 10 |
| `mode` | `dim` | `dim` fades the headline, `badge` adds a score label |
| `disabledHosts` | none | Domains to skip; subdomains are included |

Invalid stored values fall back to the defaults.

## Project structure

```
cli.js                  command-line front end
extension/scoring.js    the scorer, shared by the extension, CLI and tests
extension/content.js    finds headings on a page and marks them
extension/content.css   dim and badge styles
extension/options.*     settings page
extension/manifest.json Manifest V3
demo/index.html         page that runs the content script without the extension
test/                   node:test suites for the scorer and the CLI
```

## Tests

```
npm test
```

(or `node --test "test/**/*.test.js"`). 31 tests cover each signal, the offsets and level boundaries, empty and whitespace input, non-string input, very long input, non-Latin text, and the CLI's options, exit codes, stdin, CRLF/BOM files and missing files.

## Limitations

- It is a heuristic over English headlines. It will miss clickbait that avoids these patterns and will flag some legitimate headlines ("Is the Fed about to cut rates?" scores as a yes/no question). The weights are my own judgement, not tuned on a labelled dataset, so treat the score as a hint.
- The extension only looks at `h1`-`h4` and `role="heading"` elements. Sites that render headlines in plain links or divs are not covered.
- Tested: the scorer and CLI with automated tests, and the content script through `demo/index.html` in a browser (marking, a headline added later, no console errors, no horizontal overflow at 375px width).
- Not tested: loading the extension itself in Chrome or Edge, the options page, `chrome.storage` behaviour, or behaviour on real news sites.

## Possible improvements

- Score headlines in link text on index pages.
- Tune weights against a labelled set of headlines.
- Per-site overrides and a "this was wrong" button that records local corrections.
