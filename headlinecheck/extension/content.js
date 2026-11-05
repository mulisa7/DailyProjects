(function () {
  'use strict';

  var Scoring = window.HeadlineScoring;
  if (!Scoring) return;

  var DEFAULTS = { threshold: 4, mode: 'dim', disabledHosts: [] };
  var SELECTOR = 'h1, h2, h3, h4, [role="heading"]';
  var MARK = 'data-headlinecheck';

  function normaliseSettings(raw) {
    var s = { threshold: DEFAULTS.threshold, mode: DEFAULTS.mode, disabledHosts: [] };
    if (!raw || typeof raw !== 'object') return s;
    var t = Number(raw.threshold);
    if (isFinite(t) && t >= 0.5 && t <= 10) s.threshold = t;
    if (raw.mode === 'dim' || raw.mode === 'badge') s.mode = raw.mode;
    if (Array.isArray(raw.disabledHosts)) {
      s.disabledHosts = raw.disabledHosts.filter(function (h) { return typeof h === 'string' && h; });
    }
    return s;
  }

  function hostDisabled(settings, host) {
    return settings.disabledHosts.some(function (h) {
      return host === h || host.slice(-(h.length + 1)) === '.' + h;
    });
  }

  function clear(el) {
    el.removeAttribute(MARK);
    el.removeAttribute('data-headlinecheck-mode');
    el.removeAttribute('title');
  }

  function scan(root, settings) {
    var nodes = root.querySelectorAll ? root.querySelectorAll(SELECTOR) : [];
    var flagged = 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var text = el.textContent || '';
      if (text.length > Scoring.MAX_LENGTH) continue; // container, not a headline
      if (el.getAttribute(MARK) === 'seen:' + text) continue;
      var r = Scoring.scoreHeadline(text);
      if (r.score >= settings.threshold) {
        el.setAttribute(MARK, 'seen:' + text);
        el.setAttribute('data-headlinecheck-mode', settings.mode);
        el.setAttribute('data-headlinecheck-score', String(r.score));
        el.setAttribute('title', 'Clickbait score ' + r.score + ': ' + r.reasons.join('; '));
        flagged++;
      } else if (el.hasAttribute(MARK)) {
        clear(el);
      } else {
        el.setAttribute(MARK, 'seen:' + text);
      }
    }
    return flagged;
  }

  function start(settings) {
    if (hostDisabled(settings, location.hostname)) return;
    scan(document, settings);
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      setTimeout(function () { pending = false; scan(document, settings); }, 400);
    }).observe(document.body, { childList: true, subtree: true });
  }

  var hasStorage = typeof chrome !== 'undefined' && chrome.storage && chrome.storage.sync;
  if (hasStorage) {
    chrome.storage.sync.get(DEFAULTS, function (stored) {
      start(normaliseSettings(chrome.runtime && chrome.runtime.lastError ? null : stored));
    });
  } else {
    start(normaliseSettings(window.HEADLINECHECK_SETTINGS));
  }
})();
