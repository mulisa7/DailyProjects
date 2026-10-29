// Pure timing logic, no browser APIs, so it can be unit tested in Node.
(function (root) {
  "use strict";

  // Longest gap between two samples that still counts as time passing.
  // Browsers throttle timers in background tabs to about 1 s.
  var MAX_GAP_MS = 2000;

  function createGate(opts) {
    opts = opts || {};
    var threshold = opts.threshold == null ? 0.02 : opts.threshold;
    var holdMs = opts.holdMs == null ? 1500 : opts.holdMs; // bridges rests between notes
    var minOnMs = opts.minOnMs == null ? 80 : opts.minOnMs; // ignores clicks and bumps

    var active = false;
    var loudSince = null;
    var lastLoudAt = -Infinity;
    var lastT = null;
    var activeMs = 0;
    var totalMs = 0;

    function update(t, level) {
      if (lastT !== null && t > lastT) {
        var dt = Math.min(t - lastT, MAX_GAP_MS);
        totalMs += dt;
        if (active) activeMs += dt;
      }
      lastT = t;

      if (level >= threshold) {
        lastLoudAt = t;
        if (!active) {
          if (loudSince === null) loudSince = t;
          if (t - loudSince >= minOnMs) active = true;
        }
      } else {
        loudSince = null;
        if (active && t - lastLoudAt > holdMs) active = false;
      }
      return snapshot();
    }

    function snapshot() {
      return { active: active, activeMs: activeMs, totalMs: totalMs };
    }

    return {
      update: update,
      snapshot: snapshot,
      setThreshold: function (v) { threshold = v; },
      getThreshold: function () { return threshold; },
      // Call after a pause so the paused time is not counted.
      breakContinuity: function () { lastT = null; loudSince = null; active = false; },
    };
  }

  // Sensitivity 1 (needs loud sound) .. 10 (picks up quiet sound).
  function thresholdFromNoise(samples, sensitivity) {
    var s = Math.min(10, Math.max(1, Number(sensitivity) || 5));
    var noise = 0;
    if (samples && samples.length) {
      var sorted = samples.slice().sort(function (a, b) { return a - b; });
      noise = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.9))];
    }
    var mult = 4 - (s - 1) * (2.5 / 9);
    return Math.min(0.5, Math.max(0.01, noise * mult, noise + 0.005));
  }

  function rms(buf) {
    if (!buf || !buf.length) return 0;
    var sum = 0;
    for (var i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    return Math.sqrt(sum / buf.length);
  }

  function formatDuration(ms) {
    var total = Math.max(0, Math.floor((ms || 0) / 1000));
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
  }

  var api = {
    createGate: createGate,
    thresholdFromNoise: thresholdFromNoise,
    rms: rms,
    formatDuration: formatDuration,
    MAX_GAP_MS: MAX_GAP_MS,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SoundTimerEngine = api;
})(typeof self !== "undefined" ? self : this);
