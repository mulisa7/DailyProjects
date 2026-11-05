(function () {
  'use strict';

  var DEFAULTS = { threshold: 4, mode: 'dim', disabledHosts: [] };
  var $ = function (id) { return document.getElementById(id); };

  function show(s) {
    $('threshold').value = s.threshold;
    $('mode').value = s.mode;
    $('hosts').value = (s.disabledHosts || []).join('\n');
  }

  function say(msg) {
    $('status').textContent = msg;
    setTimeout(function () { $('status').textContent = ''; }, 2500);
  }

  chrome.storage.sync.get(DEFAULTS, show);

  $('save').addEventListener('click', function () {
    var threshold = Number($('threshold').value);
    if (!isFinite(threshold) || threshold < 0.5 || threshold > 10) {
      say('Threshold must be between 0.5 and 10.');
      return;
    }
    var hosts = $('hosts').value.split(/\r?\n/)
      .map(function (h) { return h.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, ''); })
      .filter(Boolean);
    chrome.storage.sync.set({ threshold: threshold, mode: $('mode').value, disabledHosts: hosts }, function () {
      say(chrome.runtime.lastError ? 'Could not save: ' + chrome.runtime.lastError.message : 'Saved.');
    });
  });
})();
