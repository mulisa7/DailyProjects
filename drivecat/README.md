# drivecat

Keep a searchable catalog of what is on drives that are not plugged in.

## The problem

Old external disks, DVDs and backup drives pile up in a drawer. When you need a file you cannot remember which disk holds it, so you plug them in one by one. People on Hacker News asked for a tool that indexes folders and files from DVDs and external disks, keeps the sizes, and lets you browse and search the archive without the disk attached.

## What it does

`drivecat` walks a folder or mounted drive once and stores file names, relative paths, sizes and modification times in a small SQLite file. After that you can search, browse and size up every cataloged disk while it is on the shelf. It records metadata only, never file contents.

## Features

- `scan` a folder or mount point under a label of your choice. Scanning the same label again replaces the old entry.
- `search` across all disks by substring (matches the whole path) or glob (`*.mkv`, `report_??.pdf`, matches the file name; add a `/` to match the full path). Case-insensitive. Filter by disk and minimum size.
- `ls` a disk like a directory listing, with folder totals.
- `big` shows the largest folders on a disk at a chosen depth.
- `dupes` lists files that share a name and size, optionally only across different disks.
- `disks` shows what is cataloged and when it was last scanned. `forget` removes a disk.
- Symlinks are not followed. Unreadable entries are counted and reported as a warning instead of stopping the scan.

## Requirements

Python 3.8 or newer, standard library only.

## Install

No install step. Copy `drivecat.py` anywhere or run it from this folder.

```
python drivecat.py --help
```

## Usage

```
python drivecat.py scan E:\ --label "Backup 2019"
python drivecat.py scan /media/me/photos-hdd --label photos-hdd

python drivecat.py disks
python drivecat.py search holiday
python drivecat.py search "*.mkv" --min-size 700m
python drivecat.py search "invoice*" --label "Backup 2019"

python drivecat.py ls "Backup 2019" Documents/Tax
python drivecat.py big photos-hdd --depth 2 --top 10
python drivecat.py dupes --across-disks --min-size 1m
python drivecat.py forget "Backup 2019"
```

Exit codes: 0 success, 1 a problem with the input or catalog (also `search` with no matches), 2 bad command line arguments.

## Configuration

| Setting | Meaning | Default |
|---------|---------|---------|
| `--db PATH` | Catalog file | `~/.drivecat.db` |
| `DRIVECAT_DB` | Same as `--db`, used when the flag is absent | unset |

The catalog folder must already exist. Sizes accept `500`, `10k`, `2.5MB`, `1g` (powers of 1024).

## Project structure

```
drivecat/
  drivecat.py        the whole tool: scanning, queries, CLI
  test_drivecat.py   unittest suite
  README.md
```

## Running the tests

```
cd drivecat
python -m unittest -v
```

The tests build small folder trees in a temporary directory and run the CLI against a temporary catalog.

## Limitations

- Duplicate detection compares name and size only. Two different files with the same name and size will be reported together, and the same file renamed will be missed. Contents are not hashed.
- No content indexing, tags or file previews.
- Search reads every row for the selected disks and filters in Python. That is fine for hundreds of thousands of files; I have not measured it on millions.
- Re-scanning replaces a disk completely rather than updating it, so there is no history of what changed.
- Scanning was tested on a local Windows disk and temporary folders. It was not run against optical media, network shares, or non-UTF-8 file names on Linux. Windows long-path behavior was not tested.
- Directories themselves are not stored, so empty folders do not show up in `ls`.

## Future improvements

- Optional content hash (on request) for reliable duplicate detection.
- Incremental re-scan that reports added, removed and changed files.
- Export of a disk listing to CSV.
- An FTS index to keep search fast on very large catalogs.
