/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* UI-level test for source-traced explanations on a missed reasoning question. It
   loads the REAL vantage_addon/web/practice.js behind a tiny DOM stub (same harness
   as test_exam_flow.cjs) and drives untimed practice through window.vpractice.

   It proves, on the real practice engine, the honesty rule for this feature:
     - a MISS on a question that has a gate-approved explanation shows it, with its
       source citation (the host injects only explanations that passed the shared
       SourceRef + grounding + quality gate as window.__VANTAGE_EXPLANATIONS__),
     - a CORRECT answer shows no explanation (the feature is for misses),
     - a MISS on a question with NO approved explanation shows nothing at all
       (never an ungrounded or unverified explanation).

   practice.js is a browser IIFE, so it is wrapped in a CommonJS function with a
   stubbed window/document/pycmd/timers/Date injected.

   Run:   node vantage_addon/tests/test_reasoning_explanation.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const MODULE_PATH = process.env.PRACTICE_JS || path.join(__dirname, '..', 'web', 'practice.js');

// ---- deterministic time -----------------------------------------------------
let nowMs = 1_000_000;
const DateShim = { now: () => nowMs };
const setIntervalStub = () => 1;
const clearIntervalStub = () => {};

// ---- minimal DOM ------------------------------------------------------------
function makeEl() {
  return {
    innerHTML: '', textContent: '', disabled: false, hidden: false, className: '',
    value: '', dataset: {}, style: {}, onclick: null,
    setAttribute() {}, getAttribute() { return null; },
    classList: { add() {}, remove() {}, toggle() {} },
    appendChild() {}, remove() {}, querySelectorAll() { return []; },
  };
}
const els = {};
function getEl(id) { if (!els[id]) els[id] = makeEl(); return els[id]; }
const documentStub = {
  getElementById: getEl,
  querySelectorAll: () => [],
  querySelector: () => null,
  createElement: makeEl,
  body: makeEl(),
  addEventListener() {},
};

const MAPPED_STEM = 'Adding a small amount of strong acid to the buffer barely changes its pH because the added protons are mostly:';
const UNMAPPED_STEM = 'Which color did the indicator turn at the end point?';
const EXPL_TEXT = 'The conjugate base neutralizes and consumes most of the added hydrogen ions.';
const EXPL_SOURCE = "OpenStax Chemistry 2e, ch. 14 'Acid-Base Equilibria'.";
const EXPL_LOCATOR = 'src_buffers#s4';

function mkQ(stem) {
  return { stem, choices: ['w', 'x', 'y', 'z'], answer: 0, explain: 'authored blurb' };
}
const windowStub = {
  __VANTAGE_LIVE__: true,
  __VANTAGE_REASONING_BANK__: {
    chem_phys: {
      title: 'Chem/Phys reasoning',
      passages: [{ label: 'Experiment', paragraphs: ['p'], questions: [mkQ(MAPPED_STEM), mkQ(UNMAPPED_STEM)] }],
    },
  },
  __VANTAGE_EXPLANATIONS__: {
    chem_phys: { [MAPPED_STEM]: { text: EXPL_TEXT, source: EXPL_SOURCE, locator: EXPL_LOCATOR } },
  },
};

const pycmdStub = () => {};

function load(file) {
  const src = fs.readFileSync(file, 'utf8');
  const moduleObj = { exports: {} };
  const names = ['module', 'exports', 'window', 'document', 'pycmd', 'setInterval', 'clearInterval', 'Date'];
  // eslint-disable-next-line no-new-func
  const fn = new Function(...names, src + '\n;return module.exports;');
  const exp = fn(moduleObj, moduleObj.exports, windowStub, documentStub, pycmdStub, setIntervalStub, clearIntervalStub, DateShim);
  return exp || {};
}

const srcex = () => els.srcex || makeEl();

function run() {
  const m = load(MODULE_PATH);
  const api = m.vpractice || windowStub.vpractice;
  assert.ok(api && typeof api.open === 'function', 'window.vpractice.open must exist');

  // The pure lookup, exported for exactly this: a hit and two kinds of miss.
  assert.strictEqual(typeof m.pickExplanation, 'function', 'pickExplanation should be exported');
  const hit = m.pickExplanation(windowStub.__VANTAGE_EXPLANATIONS__, 'chem_phys', MAPPED_STEM);
  assert.ok(hit && hit.text === EXPL_TEXT, 'a mapped (section, stem) resolves to its gated explanation');
  assert.strictEqual(m.pickExplanation(windowStub.__VANTAGE_EXPLANATIONS__, 'chem_phys', UNMAPPED_STEM), null, 'an unmapped stem resolves to nothing');
  assert.strictEqual(m.pickExplanation(null, 'chem_phys', MAPPED_STEM), null, 'no explanation map -> nothing');

  // ---- 1) MISS on the mapped question: the source-checked explanation shows ----
  api.open('chem_phys');
  api.choose(1); // wrong (answer is 0)
  api.check();
  assert.strictEqual(srcex().hidden, false, 'a miss with a gated explanation should reveal it');
  let html = srcex().innerHTML;
  assert.ok(html.includes(EXPL_TEXT), 'the shown explanation text is rendered');
  assert.ok(html.includes(EXPL_SOURCE), 'the source citation rides with the explanation');
  assert.ok(html.includes(EXPL_LOCATOR), 'the exact source locator is shown');
  assert.ok(html.includes('Explanation, checked against a source'), 'it is labeled as source-checked');

  // ---- 2) CORRECT answer on the same question: nothing shown (miss-only) -------
  api.open('chem_phys');
  api.choose(0); // correct
  api.check();
  assert.strictEqual(srcex().hidden, true, 'a correct answer shows no explanation block');
  assert.strictEqual(srcex().innerHTML, '', 'no explanation content on a correct answer');

  // ---- 3) MISS on the UNMAPPED question: show NOTHING (honest abstain) ---------
  api.open('chem_phys');
  api.choose(1); // miss the first (mapped) question to advance
  api.check();
  api.miss('content'); // one-tap miss reason advances to the next question
  api.choose(1); // miss the second (unmapped) question
  api.check();
  assert.strictEqual(srcex().hidden, true, 'a miss with no gated explanation shows nothing');
  assert.strictEqual(srcex().innerHTML, '', 'no fabricated explanation for an unmapped question');
}

try {
  run();
  console.log('Reasoning explanation: source-checked, gate-gated  (module:', MODULE_PATH + ')');
  console.log('  ok   - miss shows the gated explanation with its source; correct and unmapped-miss show nothing');
  console.log('\n1 passed, 0 failed');
  process.exit(0);
} catch (e) {
  console.log('Reasoning explanation: source-checked, gate-gated  (module:', MODULE_PATH + ')');
  console.log('  FAIL -', e.message);
  console.log('\n0 passed, 1 failed');
  process.exit(1);
}
