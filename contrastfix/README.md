# contrastfix

## The problem

Checking one colour pair against WCAG contrast rules is easy. Checking a whole palette is tedious, and when a pair fails, the usual next step is nudging the colour by hand and re-checking until the number turns green. Most online checkers do one pair at a time and leave the guessing to you.

## The solution

A small Rust command line tool. Give it a list of foreground/background pairs, and it prints the contrast ratio for each, marks pass or fail, and with `--fix` suggests the closest foreground colour (same hue and saturation, only the lightness changes) that meets the required ratio.

## Features

- WCAG 2.x relative luminance and contrast ratio.
- AA or AAA thresholds, normal or large text.
- Colours as `#rgb`, `#rrggbb`, `rgb(r,g,b)` or a few basic names (black, white, red, green, blue, yellow, gray/grey, orange, purple, navy, silver).
- Reads a pairs file, standard input, or a single pair from the command line.
- `--fix` searches for the smallest lightness change that passes. If no lightness works for that hue against that background, it says so rather than inventing something.
- Exit code 0 when everything passes, 1 when something fails, 2 for bad input, so it works in CI.
- No dependencies beyond the Rust standard library.

## Install

Needs a Rust toolchain (cargo).

```
cd contrastfix
cargo build --release
```

The binary is `target/release/contrastfix`.

## Usage

```
contrastfix [--aaa] [--large] [--fix] (FILE | - | --pair FG BG)
```

Single pair:

```
$ contrastfix --pair "#999999" white --fix
FAIL  #999999 on #ffffff  2.85:1 (need 4.5)
      try foreground #767676 (4.54:1)
0 of 1 pairs pass
```

Pairs file, one pair per line, optional label after the colours. Blank lines and lines starting with `//` are ignored:

```
// palette.txt
#222222 #ffffff body text
#999999 #ffffff muted text
#ffffff #0a84ff button
```

```
contrastfix --fix palette.txt
```

`rgb()` values in a file must not contain spaces (`rgb(10,20,30)`), because fields are split on whitespace. On the command line, quote the argument if you want spaces.

## Configuration

None. There are no environment variables or config files.

## Project structure

```
contrastfix/
  Cargo.toml
  src/lib.rs      colour parsing, contrast maths, suggestion search, pair file parsing
  src/main.rs     argument handling and output
  tests/contrast.rs   unit and command line tests
```

## Tests

```
cargo test
```

The tests cover known ratios (black on white is 21, #767676 on white is just over 4.5), symmetric ratios, every colour format, malformed colours, malformed pair files with line numbers, empty files, suggestions on light and dark backgrounds, hue preservation, the impossible case, and the exit codes of the real binary.

## Limitations

- Implements the WCAG 2.x ratio only. It does not implement APCA, the proposed WCAG 3 method.
- Only the foreground is adjusted. Sometimes the right fix is the background.
- The suggestion changes HSL lightness only, so it can look slightly different from what a designer would pick, and very saturated colours may shift in perceived brightness.
- Transparency (alpha) is not supported; blend colours yourself first.
- Only twelve named colours are recognised; use hex for anything else.
- Contrast ratio is not the whole of accessibility. Font size, weight and context still matter.
- Tested on Linux only. Output was compared against known reference values, not against an external checker.

## Future improvements

- Optional background adjustment.
- Alpha blending against a base colour.
- Reading colours from CSS custom properties.
- A pair matrix mode that checks every foreground against every background in a palette.
