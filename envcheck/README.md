# envcheck

Check your `.env` against `.env.example` and catch missing environment variables before the app crashes.

## Problem

You pull a branch, run the app, and it dies with `undefined` or a `KeyError` because someone added a new variable and your local `.env` never got it. The reverse happens too: code reads a variable that nobody documented in `.env.example`, so the next person hits the same wall.

## Solution

`envcheck` compares the two files and reports what is missing, empty or extra. With `--scan` it also greps your source for env reads (`process.env.X`, `os.environ["X"]`, `os.getenv("X")`, `os.Getenv("X")`, `import.meta.env.X`) and flags variables the code uses that the example file never mentions.

## Features

- Missing / empty / extra keys between `.env` and `.env.example`
- `--scan DIR` finds undocumented variables used in Python, JS/TS and Go code
- `--strict` for CI: also fail on extra, empty and unused keys
- `--json` output for scripts
- Handles `export`, comments, quotes and inline comments
- Exit codes: `0` ok, `1` problems, `2` bad input
- Standard library only, no install step

## Installation

Needs Python 3.8+.

```bash
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/envcheck
```

## Usage

```bash
python envcheck.py                      # compares ./.env with ./.env.example
python envcheck.py --scan src           # also scan src/ for env reads
python envcheck.py --env .env.local --example .env.sample --strict
python envcheck.py --json
```

Example output:

```
Missing from .env (listed in example):
  - DATABASE_URL
Read by code but not in example:
  - STRIPE_KEY  (src/billing.js)
```

Use it as a pre-commit hook or CI step: a non-zero exit fails the job.

## Configuration

None. No environment variables or network access are used, and values from your `.env` are never printed.

## Project structure

```
envcheck.py        the CLI (parser, scanner, report)
test_envcheck.py   unit tests
```

## Testing

```bash
python -m unittest -v
```

## Limitations

- The scanner is regex based, so dynamic names like `process.env[name]` are not detected.
- Multi-line quoted values are read only up to the end of their first line.

## Future improvements

- Support Ruby, PHP and Rust env reads
- `--fix` to append missing keys to `.env`
- Read `docker-compose.yml` environment blocks

## License

MIT, see the repository root.
