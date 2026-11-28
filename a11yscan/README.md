# a11yscan

Offline accessibility checks for static HTML files.

## Problem

Most accessibility mistakes in hand-written or generated HTML are basic: images with no alt text, form fields with no label, links that say "click here", skipped heading levels, a missing `lang`. Browser audit tools catch them but need a running page and a browser, and are awkward to drop into a script or a pre-commit hook.

## Solution

A single-file Python script that parses HTML with the standard library and reports these mistakes with file and line number. It exits non-zero when it finds something, so it works in CI.

## Features

- 16 rules (run `--list-rules`): missing or file-name-like alt text, missing `lang`, missing title, heading skips, not exactly one h1, links and buttons with no accessible name, vague link text, unlabelled form fields, duplicate ids, positive tabindex, tables without `th`, iframes without a title, viewport that blocks zoom, autoplaying media.
- Accepts files and folders (folders are searched recursively for `.html` and `.htm`, skipping `.git` and `node_modules`).
- Page-level rules (lang, title, h1) only apply to files that contain an `<html>` tag, so template fragments are not flagged.
- `--ignore rule1,rule2` to skip rules, `--json` for machine-readable output.
- Reads UTF-8 (with or without BOM) and falls back to Latin-1.

## Install and usage

Needs Python 3.8 or newer. No dependencies.

```
python3 a11yscan.py index.html
python3 a11yscan.py site/ --ignore heading-h1,link-vague
python3 a11yscan.py site/ --json > report.json
```

Example output:

```
site/contact.html:12: [img-alt] Image has no alt attribute: team.png
site/contact.html:20: [input-label] Form field has no label
2 issue(s) in 1 file(s)
```

Exit codes: 0 no issues, 1 issues found, 2 usage or file error.

## Configuration

None beyond the command-line flags. No environment variables.

## Project structure

```
a11yscan.py        the scanner and CLI
test_a11yscan.py   unit tests
```

## Tests

```
cd a11yscan
python3 -m unittest
```

The tests cover each rule (passing and failing cases), malformed and empty HTML, nested tables, encodings, and the CLI exit codes and options.

## Limitations

- It only reads static HTML. Content built by JavaScript, or CSS that hides or changes things, is not seen.
- It does not compute colour contrast, check ARIA roles or states in depth, or understand `aria-labelledby` targets (it only checks that the attribute is present).
- Accessible-name logic is simplified: text, image alt text and `aria-label` count; `title` counts for form fields and iframes only.
- The vague-link list and the file-name alt pattern are short English-only lists.
- Passing this tool does not mean a page is accessible. It finds common mechanical errors, not usability problems.
- Tested only with the unit tests above and small hand-written pages, not against a large corpus of real sites.

## Future improvements

- Markdown and template (Jinja, Handlebars) support.
- Contrast checks for inline styles.
- Resolving `aria-labelledby` and `for` targets across the whole document, with a warning when they point nowhere.
- A baseline file so existing issues can be ignored while new ones fail the build.
