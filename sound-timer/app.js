(function () {
  "use strict";
  var E = window.SoundTimerEngine;
  var $ = function (id) { return document.getElementById(id); };

  var HISTORY_KEY = "soundtimer.history.v1";
  var CALIBRATE_MS = 2000;
  var TICK_MS = 50;

  var el = {
    soundTime: $("soundTime"), goalFill: $("goalFill"), goalBar: $("goalBar"),
    goalText: $("goalText"), sessionText: $("sessionText"), pctText: $("pctText"),
    meterFill: $("meterFill"), meterMark: $("meterMark"), status: $("status"),
    start: $("startBtn"), pause: $("pauseBtn"), finish: $("finishBtn"),
    goalSel: $("goalSel"), sens: $("sens"), recal: $("recalBtn"),
    list: $("historyList"), empty: $("historyEmpty"), clear: $("clearBtn"),
  };

  var ctx = null, stream = null, analyser = null, buf = null, timer = null, wakeLock = null;
  var gate = E.createGate();
  var state = "idle"; // idle | calibrating | running | paused
  var noiseSamples = [];
  var calibrateUntil = 0;
  var goalReached = false;
  var baseTitle = document.title;

  function setStatus(msg, isError) {
    el.status.textContent = msg;
    el.status.classList.toggle("error", !!isError);
  }

  function goalMs() { return Number(el.goalSel.value) * 60000; }

  function render(snap) {
    el.soundTime.textContent = E.formatDuration(snap.activeMs);
    el.sessionText.textContent = "Session " + E.formatDuration(snap.totalMs);
    el.goalText.textContent = "Goal " + E.formatDuration(goalMs());
    var pct = snap.totalMs > 0 ? Math.round((snap.activeMs / snap.totalMs) * 100) : 0;
    el.pctText.textContent = pct + "% playing";
    var done = Math.min(100, (snap.activeMs / goalMs()) * 100);
    el.goalFill.style.width = done + "%";
    el.goalFill.classList.toggle("done", done >= 100);
    el.goalBar.setAttribute("aria-valuenow", String(Math.round(done)));
  }

  function setMeter(level) {
    // Square-root scale so quiet instruments still move the bar.
    el.meterFill.style.width = Math.min(100, Math.sqrt(level) * 100) + "%";
  }

  function placeMark() {
    el.meterMark.style.left = Math.min(100, Math.sqrt(gate.getThreshold()) * 100) + "%";
  }

  function applyThreshold() {
    gate.setThreshold(E.thresholdFromNoise(noiseSamples, el.sens.value));
    placeMark();
  }

  function readLevel() {
    analyser.getFloatTimeDomainData(buf);
    return E.rms(buf);
  }

  function tick() {
    var now = performance.now();
    var level = readLevel();
    setMeter(level);

    if (state === "calibrating") {
      noiseSamples.push(level);
      var left = Math.ceil((calibrateUntil - now) / 1000);
      setStatus("Stay quiet for a moment to measure the room... " + Math.max(left, 0));
      if (now >= calibrateUntil) {
        applyThreshold();
        state = "running";
        gate.breakContinuity();
        el.pause.disabled = false;
        setStatus("Listening. Play when you're ready.");
      }
      return;
    }
    if (state !== "running") return;

    var snap = gate.update(now, level);
    el.meterFill.classList.toggle("on", snap.active);
    render(snap);
    if (!goalReached && snap.activeMs >= goalMs()) {
      goalReached = true;
      document.title = "Goal reached - " + baseTitle;
      setStatus("Goal reached. Keep going or press Finish.");
    } else if (!goalReached) {
      setStatus(snap.active ? "Counting..." : "Waiting for sound");
    }
  }

  function explain(err) {
    var name = err && err.name;
    if (name === "NotAllowedError" || name === "SecurityError")
      return "Microphone blocked. Allow access in the browser's address bar and try again.";
    if (name === "NotFoundError" || name === "OverconstrainedError")
      return "No microphone found. Plug one in and try again.";
    if (name === "NotReadableError") return "The microphone is busy in another app.";
    return "Could not start the microphone" + (err && err.message ? ": " + err.message : ".");
  }

  async function openMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
      throw new Error("This browser has no microphone support, or the page is not on HTTPS/localhost.");
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    var AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    if (ctx.state === "suspended") await ctx.resume();
    var src = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    buf = new Float32Array(analyser.fftSize);
    src.connect(analyser);
    // If the mic disappears mid-session, stop cleanly instead of counting silence.
    stream.getAudioTracks().forEach(function (t) {
      t.addEventListener("ended", function () {
        if (state !== "idle") {
          setStatus("Microphone disconnected. Session paused.", true);
          pause();
        }
      });
    });
  }

  function closeMic() {
    clearInterval(timer);
    timer = null;
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    if (ctx) ctx.close().catch(function () {});
    stream = ctx = analyser = null;
    releaseWake();
  }

  async function keepAwake() {
    try {
      if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request("screen");
    } catch (e) { /* optional nicety */ }
  }
  function releaseWake() {
    try { if (wakeLock) wakeLock.release(); } catch (e) { /* ignore */ }
    wakeLock = null;
  }

  function beginCalibration() {
    noiseSamples = [];
    calibrateUntil = performance.now() + CALIBRATE_MS;
    state = "calibrating";
    el.pause.disabled = true;
  }

  async function start() {
    el.start.disabled = true;
    setStatus("Asking for the microphone...");
    try {
      await openMic();
    } catch (err) {
      setStatus(explain(err), true);
      el.start.disabled = false;
      closeMic();
      return;
    }
    gate = E.createGate();
    goalReached = false;
    document.title = baseTitle;
    render(gate.snapshot());
    beginCalibration();
    el.finish.disabled = false;
    el.recal.disabled = false;
    el.start.textContent = "Start";
    timer = setInterval(tick, TICK_MS);
    keepAwake();
  }

  function pause() {
    if (state === "paused") return resume();
    if (state !== "running") return;
    state = "paused";
    el.pause.textContent = "Resume";
    el.meterFill.classList.remove("on");
    setStatus("Paused");
  }

  function resume() {
    gate.breakContinuity();
    state = "running";
    el.pause.textContent = "Pause";
    setStatus("Listening...");
  }

  function finish() {
    var snap = gate.snapshot();
    if (snap.totalMs > 1000) saveSession(snap);
    closeMic();
    state = "idle";
    el.start.disabled = false;
    el.pause.disabled = true;
    el.pause.textContent = "Pause";
    el.finish.disabled = true;
    el.recal.disabled = true;
    el.meterFill.style.width = "0";
    el.meterFill.classList.remove("on");
    document.title = baseTitle;
    setStatus("Saved. Press Start for a new session.");
  }

  // History lives only in this browser's localStorage.
  function loadHistory() {
    try {
      var h = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(h) ? h : [];
    } catch (e) { return []; }
  }
  function saveHistory(h) {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 30))); } catch (e) { /* private mode */ }
  }
  function saveSession(snap) {
    var h = loadHistory();
    h.unshift({ at: Date.now(), activeMs: snap.activeMs, totalMs: snap.totalMs });
    saveHistory(h);
    renderHistory();
  }
  function renderHistory() {
    var h = loadHistory().slice(0, 10);
    el.list.textContent = "";
    el.empty.hidden = h.length > 0;
    h.forEach(function (s) {
      var li = document.createElement("li");
      var when = document.createElement("span");
      when.textContent = new Date(s.at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
      var what = document.createElement("span");
      var pct = s.totalMs ? Math.round((s.activeMs / s.totalMs) * 100) : 0;
      what.textContent = E.formatDuration(s.activeMs) + " of " + E.formatDuration(s.totalMs) + " (" + pct + "%)";
      li.append(when, what);
      el.list.appendChild(li);
    });
  }

  el.start.addEventListener("click", start);
  el.pause.addEventListener("click", pause);
  el.finish.addEventListener("click", finish);
  el.recal.addEventListener("click", function () {
    if (state === "running" || state === "paused") beginCalibration();
  });
  el.sens.addEventListener("input", function () {
    if (noiseSamples.length) applyThreshold();
  });
  el.goalSel.addEventListener("change", function () {
    goalReached = false;
    render(gate.snapshot());
  });
  el.clear.addEventListener("click", function () {
    if (confirm("Delete all saved sessions from this browser?")) {
      saveHistory([]);
      renderHistory();
    }
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && stream && !wakeLock) keepAwake();
  });

  placeMark();
  render(gate.snapshot());
  renderHistory();
})();
