# datename

Renames photos, screenshots and downloads to a date-based name such as `2024-03-15_142210.jpg`.

## The problem

Files from phones, cameras and screenshot tools end up with unhelpful or inconsistent names (`IMG_4471.JPG`, `Screenshot 2024-03-15 at 14.22.10.png`, `PXL_20231201_090000123.jpg`), so they do not sort by date. Existing renamers such as exiftool work well when a file has EXIF data, but screenshots, messaging-app images and scans have none, and people end up writing a script that tries EXIF, then the name, then the file date.

## The solution

`datename` picks a date for each file from a list of sources, tried in order, and renames the file from that date. Default order: EXIF, then a date found in the file name, then the modified time. It is a dry run unless you pass `--apply`.

## Features

- EXIF `DateTimeOriginal` (falling back to `DateTime`) read from JPEG, little- and big-endian.
- Dates in names: `20240315_142210`, `2024-03-15`, `2024.03.15`, `... at 14.22.10`, trailing milliseconds. Impossible dates such as Feb 30 are ignored.
- Choose and order sources with `--sources`.
- Custom layout with `--format` (tokens `YYYY MM DD hh mm ss`).
- `--keep-name` appends the original name; already-stamped files are left alone, so reruns do nothing.
- Name collisions get `_2`, `_3`. An existing file is never overwritten.
- Dry run by default; prints which source gave each date.

## Install

Needs Go 1.21 or newer. No dependencies.

```
cd datename
go build -o datename .
```

## Usage

```
./datename ~/Pictures/inbox                    # preview
./datename --apply ~/Pictures/inbox            # rename
./datename -r --apply --keep-name --format YYYYMMDD ~/Pictures
./datename --sources name,mtime --apply downloads/
```

Exit codes: 0 success, 1 some file could not be dated or renamed, 2 bad arguments or unreadable path.

## Configuration

No environment variables or config files. Everything is a flag; see `./datename -h`.

## Project structure

- `dates.go` - date from file name, EXIF parsing
- `rename.go` - planning, collision handling, applying renames
- `main.go` - flags and output
- `main_test.go` - tests

## Tests

```
cd datename
go test ./...
```

Tests cover name patterns, invalid dates, EXIF in both byte orders, truncated and corrupted EXIF data, collisions, not overwriting, idempotence, recursion, and CLI errors. They use temporary directories.

## Limitations

- EXIF is read from JPEG only (not HEIC, PNG, RAW or video). Those files fall through to the next source.
- EXIF times have no time zone and are used as written. Modified time is shown in the local zone.
- Only the first 256 KiB of a file is scanned for EXIF.
- Only tested on Linux, and only against synthetic JPEGs built in the tests, not real camera files from many makers.
- Renames within a single run are not atomic; if it is interrupted some files may be renamed and others not.
- No undo. Use the dry run first.

## Future improvements

- HEIC and PNG metadata, video creation dates.
- An undo log.
- Time zone offset option for EXIF dates.
