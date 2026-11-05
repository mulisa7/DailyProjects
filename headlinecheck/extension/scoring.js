(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.HeadlineScoring = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MAX_LENGTH = 400;

  // Phrases that promise something without saying it.
  var GAP_PHRASES = [
    /\byou (won't|will not|wouldn't) believe\b/,
    /\bwhat happened next\b/,
    /\b(will|might|could) (shock|blow|surprise|amaze|stun)\b/,
    /\bone (weird |simple |easy )?(trick|secret|thing)\b/,
    /\bthe (real )?(reason|truth|secret) (why|behind|about)\b/,
    /\bwhat (they|he|she|nobody|no one|experts?) (don't|doesn't|won't|isn't) (want you to |telling )?(know|say|tell)/,
    /\bhere's (why|what|how|the)\b/,
    /\bwhat you (need|have) to know\b/,
    /\bfind out (why|what|how|who)\b/,
    /\b(this|these) (is|are) (why|what|how)\b/,
    /\bchanged (everything|my life|the game)\b/
  ];

  var EMOTIVE = [
    'shocking', 'stunning', 'jaw-dropping', 'insane', 'epic', 'mind-blowing',
    'heartbreaking', 'terrifying', 'incredible', 'unbelievable', 'devastating',
    'bombshell', 'explosive', 'outrageous', 'hilarious', 'genius', 'brutal'
  ];

  var COMBAT_VERBS = /\b(slams?|destroys?|obliterates?|torches|eviscerates?|rips|blasts?|crushes|owns|demolishes)\b/;

  var YES_NO_OPENERS = /^(is|are|was|were|can|could|will|would|does|do|did|should|has|have|might|may)\b/;

  var STACKED = /\?!|!\?|!{2,}|\?{2,}/;

  var CONCRETE = /[$£€]\s?\d|\d+(\.\d+)?\s?%|\b(19|20)\d\d\b/;

  var ACRONYMS = {
    NASA: 1, FBI: 1, CIA: 1, USA: 1, NATO: 1, FIFA: 1, UEFA: 1, GDP: 1, CEO: 1,
    NBA: 1, NFL: 1, BBC: 1, CNN: 1, IMF: 1, WHO: 1, SEC: 1, IRS: 1, ETF: 1, NHS: 1
  };

  function normalise(text) {
    return text
      .replace(/[‘’ʼ]/g, "'")
      .replace(/[“”]/g, '"')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Returns { score, level, reasons, words } for one headline.
  // Throws TypeError for non-strings so callers notice bad input.
  function scoreHeadline(input) {
    if (typeof input !== 'string') throw new TypeError('headline must be a string');
    var original = normalise(input).slice(0, MAX_LENGTH);
    var result = { score: 0, level: 'low', reasons: [], words: original ? original.split(' ').length : 0 };
    if (!original) return result;

    var text = original.toLowerCase();
    var score = 0;
    var reasons = result.reasons;

    function add(points, why) {
      score += points;
      reasons.push(why);
    }

    var i, m;
    for (i = 0; i < GAP_PHRASES.length; i++) {
      m = GAP_PHRASES[i].exec(text);
      if (m) { add(3, 'curiosity gap: "' + m[0] + '"'); break; }
    }

    if (/\?\s*$/.test(text) && YES_NO_OPENERS.test(text)) add(2, 'yes/no question headline');
    if (STACKED.test(text)) add(1.5, 'stacked punctuation');

    m = /^(\d{1,3}) (\w+ ){0,2}(things|reasons|ways|tips|facts|signs|mistakes|secrets|tricks|hacks|ideas|lessons|moments|photos|pictures)\b/.exec(text);
    var listicle = !!m;
    if (listicle) add(1.5, 'listicle opener: "' + m[0] + '"');

    if (!listicle && /^(this|these|those|here's|here are) /.test(text) &&
        !/^this (week|month|year|morning|summer|winter)\b/.test(text)) {
      add(1.5, 'opens with a pronoun that has nothing to refer to');
    }

    var emotive = [];
    for (i = 0; i < EMOTIVE.length; i++) {
      if (new RegExp('\\b' + EMOTIVE[i] + '\\b').test(text)) emotive.push(EMOTIVE[i]);
    }
    if (emotive.length) add(Math.min(emotive.length, 2), 'emotive words: ' + emotive.slice(0, 3).join(', '));

    m = COMBAT_VERBS.exec(text);
    if (m) add(1, 'combat verb: "' + m[0] + '"');

    var letters = original.replace(/[^A-Za-z]/g, '');
    if (original.length > 12 && letters.length > 8 && letters === letters.toUpperCase()) {
      add(1.5, 'whole headline in capitals');
    } else {
      var shouted = (original.match(/\b[A-Z]{3,}\b/g) || []).filter(function (w) { return !ACRONYMS[w]; });
      if (shouted.length >= 2) add(1, 'words in capitals: ' + shouted.slice(0, 3).join(', '));
    }

    if (score > 0 && !listicle && (CONCRETE.test(text) || /\bR\s?\d/.test(original))) {
      score -= 1;
      reasons.push('offset: contains a concrete figure');
    }

    if (score < 0) score = 0;
    result.score = Math.round(score * 10) / 10;
    result.level = score >= 4 ? 'high' : score >= 2 ? 'medium' : 'low';
    return result;
  }

  return { scoreHeadline: scoreHeadline, normalise: normalise, MAX_LENGTH: MAX_LENGTH };
});
