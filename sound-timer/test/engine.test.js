const test = require("node:test");
const assert = require("node:assert/strict");
const E = require("../engine.js");

// Feed a level for `ms` milliseconds at 50 ms steps, starting at t.
function feed(gate, t, ms, level) {
  let snap;
  for (let i = 0; i <= ms; i += 50) snap = gate.update(t + i, level);
  return { t: t + ms + 50, snap };
}

test("counts only time with sound", () => {
  const g = E.createGate({ threshold: 0.05, holdMs: 500 });
  let r = feed(g, 0, 2000, 0.01); // silence
  assert.equal(r.snap.activeMs, 0);
  r = feed(g, r.t, 3000, 0.2); // playing
  r = feed(g, r.t, 3000, 0.01); // silence again
  assert.ok(r.snap.activeMs > 3000 && r.snap.activeMs < 4000, r.snap.activeMs);
  assert.ok(r.snap.totalMs > 8000);
});

test("short rest inside hold window keeps counting", () => {
  const g = E.createGate({ threshold: 0.05, holdMs: 1500 });
  let r = feed(g, 0, 1000, 0.2);
  r = feed(g, r.t, 1000, 0.0); // 1 s rest < hold
  r = feed(g, r.t, 1000, 0.2);
  assert.ok(r.snap.activeMs > 2800, r.snap.activeMs);
});

test("a click shorter than minOnMs does not start the clock", () => {
  const g = E.createGate({ threshold: 0.05, minOnMs: 200 });
  let r = feed(g, 0, 1000, 0);
  g.update(r.t, 0.9);
  r = feed(g, r.t + 50, 2000, 0);
  assert.equal(r.snap.activeMs, 0);
});

test("long gap between samples is capped", () => {
  const g = E.createGate({ threshold: 0.05 });
  g.update(0, 0.5);
  g.update(100, 0.5);
  const snap = g.update(600000, 0.5); // laptop slept for 10 minutes
  assert.ok(snap.totalMs <= 100 + E.MAX_GAP_MS);
});

test("breakContinuity drops paused time", () => {
  const g = E.createGate({ threshold: 0.05 });
  feed(g, 0, 1000, 0.5);
  const before = g.snapshot().totalMs;
  g.breakContinuity();
  g.update(60000, 0.5); // resume a minute later
  assert.equal(g.snapshot().totalMs, before);
  assert.equal(g.snapshot().active, false);
});

test("threshold can change while running", () => {
  const g = E.createGate({ threshold: 0.5 });
  let r = feed(g, 0, 1000, 0.1);
  assert.equal(r.snap.activeMs, 0);
  g.setThreshold(0.05);
  r = feed(g, r.t, 1000, 0.1);
  assert.ok(r.snap.activeMs > 800);
});

test("thresholdFromNoise: handles empty, scales with noise and sensitivity", () => {
  assert.equal(E.thresholdFromNoise([], 5), 0.01);
  assert.equal(E.thresholdFromNoise(undefined, 5), 0.01);
  const noisy = Array(20).fill(0.05);
  const lowSens = E.thresholdFromNoise(noisy, 1);
  const highSens = E.thresholdFromNoise(noisy, 10);
  assert.ok(lowSens > highSens);
  assert.ok(highSens > 0.05);
  assert.equal(E.thresholdFromNoise(Array(5).fill(5), 1), 0.5); // capped
  assert.ok(E.thresholdFromNoise(noisy, "abc") > 0.05); // bad input falls back
});

test("rms", () => {
  assert.equal(E.rms([]), 0);
  assert.equal(E.rms(null), 0);
  assert.ok(Math.abs(E.rms([1, -1, 1, -1]) - 1) < 1e-9);
});

test("formatDuration", () => {
  assert.equal(E.formatDuration(0), "0:00");
  assert.equal(E.formatDuration(65000), "1:05");
  assert.equal(E.formatDuration(3725000), "1:02:05");
  assert.equal(E.formatDuration(-5), "0:00");
  assert.equal(E.formatDuration(NaN), "0:00");
});
