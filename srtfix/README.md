# srtfix

A small command-line tool for fixing SRT subtitle files that are out of sync with the video.

## The problem

Downloaded subtitles often start a couple of seconds early or late, or drift further out of sync as the film goes on because they were timed for a different frame rate (23.976 vs 25 fps is the usual culprit). Kodi, VLC and most players can nudge the delay while playing, but that setting is not saved into the file, and it cannot fix drift. Editing the file by hand means doing timestamp arithmetic on hundreds of lines.

## The solution

`srtfix` reads an `.srt` file and rewrites the timings with one of four operations, then renumbers the cues. It uses only Node's standard library.

## Features

- `shift`: move every cue by a fixed amount (`2.5s`, `-800ms`, or plain milliseconds).
- `stretch`: rescale times for a frame-rate mismatch, e.g. `23.976 25`.
- `sync`: give two lines you know the correct times for (one early, one late) and every cue is mapped linearly, fixing both offset and drift.
- `check`: report problems (overlaps, end before start, empty text, out-of-order cues) without changing anything.
- `sort`: sort cues by start time and renumber.
- Handles UTF-8 BOM, CRLF line endings, missing index lines, and both `,` and `.` before milliseconds. Malformed blocks are skipped with a warning on stderr.

## Install and use

Requires Node 18 or newer. No dependencies.

```
cd srtfix
node cli.js shift movie.srt 2.5s -o movie.fixed.srt
node cli.js stretch movie.srt 23.976 25 -o movie.fixed.srt
node cli.js sync movie.srt 00:01:02,500 00:01:05,000 01:40:10,000 01:40:18,250 -o movie.fixed.srt
node cli.js check movie.fixed.srt
```

Without `-o` the result goes to stdout. The input file is never modified. `npm link` will install it as `srtfix` if you want it on your PATH.

Stretch direction: `stretch <from-fps> <to-fps>` multiplies every time by from/to. If the subtitles were made for 23.976 fps video and your video is 25 fps, use `23.976 25`.

Exit codes: 0 success, 1 `check` found problems, 2 bad arguments or unreadable input.

## Configuration

None. No environment variables.

## Project structure

- `srt.js` - parsing, formatting, shift, stretch, sync, validation (pure functions)
- `cli.js` - argument handling and file I/O
- `test.js` - tests

## Tests

```
cd srtfix
node --test test.js
```

17 tests cover timestamp parsing, CRLF/BOM input, empty and garbage input, clamping at zero, drift sync maths, validation rules, and CLI exit codes and error messages.

## Limitations

- SRT only. No WebVTT, ASS/SSA or encodings other than UTF-8 (a Latin-1 file will show replacement characters).
- Formatting tags in the text are kept as-is and not interpreted.
- Cues pushed before 0:00 by a negative shift are clamped or dropped.
- The tool does not detect how far out of sync a file is; you supply the numbers.
- Tested only with small hand-written sample files, not real subtitle files from different releases, and not played back in a video player.

## Future improvements

- WebVTT input and output.
- Encoding detection.
- Optionally fix overlaps automatically.
- Find the sync reference points by matching against a second, correctly timed subtitle file.
