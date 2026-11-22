# mdrefs

Checks relative links and heading anchors in Markdown files, offline.

## Problem

Docs folders rot quietly. A file gets renamed, a heading is reworded, and every `[see setup](setup.md#install)` pointing at it breaks. Most link checkers either fetch URLs over the network or only check that the file exists, so a dead `#anchor` goes unnoticed until a reader clicks it.

## Solution

A single-file Python script that walks a folder of Markdown, finds the links that point at local files, and verifies both the file and, for Markdown targets, the heading anchor. It never touches the network.

## Features

- Inline links, images, and reference-style links (`[text][label]` with `[label]: target`)
- Anchor check using GitHub-style slugs, including the `-1`, `-2` suffix for repeated headings
- Anchors from raw HTML `id=` and `name=` attributes
- Skips fenced code blocks and inline code
- Handles `<path with spaces>`, `%20`, parentheses in file names, optional titles and `?query` strings
- Reports links that escape the checked root and reference links with no definition
- Exit code 0 clean, 1 problems found, 2 bad usage

External links (`http:`, `mailto:`, `//host`) are ignored on purpose.

## Install and usage

Needs Python 3.8 or newer. No dependencies.

```
python3 mdrefs.py                 # check the current folder
python3 mdrefs.py docs README.md  # folders and files
python3 mdrefs.py docs --root .   # resolve /absolute links against another folder
```

Output is one line per problem, then a summary:

```
docs/guide.md:12: no heading or id matches this anchor: setup.md#instal
docs/guide.md:20: file not found: img/old.png
2 file(s) checked, 2 problem(s)
```

## Configuration

There are none. The only option is `--root`. `.git` and `node_modules` are always skipped.

## Project structure

```
mdrefs/
  mdrefs.py            the tool
  tests/test_mdrefs.py unit and CLI tests
```

## Tests

```
cd mdrefs
python3 -m unittest discover -s tests
```

27 tests cover slug rules, duplicate headings, code fences, missing files, bad anchors, reference links, odd URL forms, empty files and folders, a missing path, and an undecodable file.

## Limitations

- Slug rules follow GitHub's behaviour as I understand it. Other renderers (GitLab, MkDocs, Docusaurus) slugify differently, so anchors may be wrongly flagged or accepted there. I did not compare against GitHub's renderer output beyond common cases; non-ASCII headings and emoji are the likeliest to differ.
- Setext headings (underlined with `===`) are not recognised as anchors.
- Links inside HTML blocks (`<a href=...>`, `<img src=...>`) are not checked.
- Anchors in non-Markdown files (for example `code.py#L10`) are not verified.
- Case-insensitive file systems are not accounted for: a link with the wrong case passes on macOS and Windows but breaks on Linux. The tool checks whatever the local file system says.

## Future improvements

- Setext headings and HTML `href`/`src` checking
- Selectable slug style per renderer
- A `--json` output mode for CI annotations
