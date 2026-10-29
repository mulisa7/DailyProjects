# Sound Timer

A practice timer that only counts the time you are actually making sound.

## Problem

Practice timers count the whole session. If you set a 20 minute piano timer, a good part of it goes on turning pages, fetching water, fixing a mistake or talking. You finish "20 minutes" having played maybe 12. Parents of kids who practice an instrument, and anyone trying to build a real habit, have no honest number.

## Solution

Sound Timer listens through the microphone and runs the clock only while it hears sound. Short rests between notes are bridged, so a pause in a phrase does not stop the count, but a minute of silence does.

## Features

- Time with sound, total session time and a "% playing" figure
- Goal (5 to 60 min) with a progress bar
- Two second room calibration, plus a sensitivity slider for quiet or loud instruments
- Live level meter with the trigger mark, so you can see why it is or is not counting
- Pause and resume, last 10 sessions kept in your browser
- Clear message if the microphone is blocked, missing or busy, and a clean stop if it disconnects mid-session
- No dependencies, no build step, no network

## Privacy

Audio is never recorded, stored or sent anywhere. The page only reads the loudness of each short audio frame. Session history is stored in your browser's `localStorage` and nowhere else.

## Installation

Browsers only allow microphone access on `https://` pages or `localhost`, so serve the folder instead of double-clicking the file:

```bash
git clone https://github.com/mulisa7/DailyProjects.git
cd DailyProjects/sound-timer
python -m http.server 8000
```

Then open http://localhost:8000. It also works as-is on any static host with HTTPS, such as GitHub Pages.

## Usage

1. Pick a goal and press Start, then allow the microphone.
2. Stay quiet for two seconds while it measures the room.
3. Play. The time with sound counts up while the meter is orange.
4. If it counts room noise, lower the sensitivity. If it misses soft playing, raise it, or press Recalibrate.
5. Press Finish to save the session.

## Project structure

```
index.html, style.css   page
app.js                  microphone, calibration, UI, history
engine.js               timing logic with no browser APIs (unit tested)
test/engine.test.js     tests
```

## Testing

```bash
node --test
```

Needs Node 18 or newer. The tests cover the timing logic: counting only during sound, bridging short rests, ignoring clicks, capping long gaps, pausing, threshold maths and formatting. The page itself was checked in a browser with a fake microphone (a toggled oscillator) and with a denied-permission error, but not on a phone or with a real instrument.

## Limitations

- Background tabs run timers about once a second, so the count is coarser while the tab is hidden.
- It measures loudness, not music: speech, a TV or a noisy room can count as playing.
- Noise suppression and auto gain are requested off, but some devices ignore that.

## Future improvements

- AudioWorklet sampling so background tabs stay accurate
- Weekly totals and a streak view
- Basic pitch detection to tell music from talking

## License

MIT, see the repository root.
