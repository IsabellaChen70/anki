/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* End-to-end state-machine test for the full-length exam. It loads the REAL
   vantage_addon/web/practice.js behind a tiny DOM stub and drives a whole shortened
   exam through the public window.vpractice API, exactly as the webview would. It
   proves, on the real engine:
     - sections chain in the real MCAT order,
     - a timed break sits between each section (and the break countdown, when it hits
       zero, starts the next section on its own),
     - the break can also be skipped,
     - NO feedback (correct/incorrect, explanations, confidence) appears until the very
       end, and
     - the final summary aggregates the real per-section tallies and shows the honest
       abstain state for a section with nothing answered, with no blended exam score.

   practice.js is a browser IIFE, so it is wrapped in a CommonJS function in this realm
   with a stubbed window/document/pycmd/timers/Date injected. Set PRACTICE_JS to point
   at a different copy (used to show the red baseline before the feature existed).

   Run:   node vantage_addon/tests/test_exam_flow.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const MODULE_PATH = process.env.PRACTICE_JS || path.join(__dirname, '..', 'web', 'practice.js');

// ---- deterministic time -----------------------------------------------------
let nowMs = 1_000_000;
const DateShim = { now: () => nowMs };

// ---- captured timers: keep the most recently created interval so the test can
// fire it deliberately (a section countdown or a break countdown) ------------
let activeTimer = null;
const setIntervalStub = (fn) => { activeTimer = fn; return 1; };
const clearIntervalStub = () => { activeTimer = null; };
function fireActiveTimer() { if (typeof activeTimer === 'function') activeTimer(); }

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
// Live page contract: mark this as a live app so the setup screen never reaches for
// MOCK demo data (there is no dashboard.js loaded here anyway).
const windowStub = { __VANTAGE_LIVE__: true };

const pycmds = [];
const pycmdStub = (cmd) => { pycmds.push(cmd); };

function load(file) {
  const src = fs.readFileSync(file, 'utf8');
  const moduleObj = { exports: {} };
  const names = ['module', 'exports', 'window', 'document', 'pycmd', 'setInterval', 'clearInterval', 'Date'];
  // eslint-disable-next-line no-new-func
  const fn = new Function(...names, src + '\n;return module.exports;');
  const exp = fn(moduleObj, moduleObj.exports, windowStub, documentStub, pycmdStub, setIntervalStub, clearIntervalStub, DateShim);
  return exp || {};
}

const paneHTML = () => (els['pane-practice'] ? els['pane-practice'].innerHTML : '');
const FEEDBACK_MARKERS = ['id="fb"', 'id="ex"', 'class="feedback', 'feedback--ok', 'feedback--no', 'Check answer', 'Not quite', 'confrow'];
function assertNoFeedback(where) {
  const html = paneHTML();
  FEEDBACK_MARKERS.forEach((mk) => {
    assert.ok(html.indexOf(mk) === -1, `feedback leaked before the end (${where}): found ${JSON.stringify(mk)}`);
  });
}

const order = [];   // observed running order, for an exact-order assertion
let m;
let api;
let passed = 0;
let failed = 0;

function run() {
  m = load(MODULE_PATH);
  api = m.vpractice || (windowStub && windowStub.vpractice);
  assert.ok(api && typeof api.startExam === 'function', 'window.vpractice.startExam must exist');

  // Choose a full 4-section exam, shortened so it walks the whole flow quickly.
  api.setExamScope('full');
  api.setExamPace('quick');

  // ---- section 1: Chem/Phys --------------------------------------------------
  api.startExam();
  order.push(sectionTag());
  assert.ok(paneHTML().includes('Section 1 of 4'), 'exam should open on section 1 of 4');
  assertNoFeedback('section 1 start');
  answerSection(3, 'section 1');
  assertBreakTo('CARS', 'after section 1');
  assertBreakMinutesShown();

  // The break countdown reaching zero starts the next section on its own.
  fireBreakTimer();
  order.push(sectionTag());
  assert.ok(paneHTML().includes('Section 2 of 4'), 'break timer should advance to section 2');
  assertNoFeedback('section 2 start');

  // ---- section 2: CARS -------------------------------------------------------
  answerSection(3, 'section 2');
  assertBreakTo('Bio/Biochem', 'after section 2');

  // This time skip the break instead of waiting it out.
  api.examSkipBreak();
  order.push(sectionTag());
  assert.ok(paneHTML().includes('Section 3 of 4'), 'skip should advance to section 3');
  assertNoFeedback('section 3 start');

  // ---- section 3: Bio/Biochem ------------------------------------------------
  answerSection(3, 'section 3');
  assertBreakTo('Psych/Soc', 'after section 3');
  fireBreakTimer();
  order.push(sectionTag());
  assert.ok(paneHTML().includes('Section 4 of 4'), 'break timer should advance to section 4');
  assertNoFeedback('section 4 start');

  // ---- section 4: Psych/Soc, answer NOTHING, let the clock run out -----------
  // This produces a section with no answers, which must abstain in the summary.
  nowMs += 100 * 60_000; // well past the section's time budget
  fireActiveTimer(); // the section countdown hits zero -> section ends -> summary

  const summary = paneHTML();
  assert.ok(summary.includes('Full-length exam complete'), 'the last section should lead to the cross-section summary');
  // Each science section that was answered shows its raw tally; Psych/Soc abstains.
  ['Chem/Phys', 'CARS', 'Bio/Biochem', 'Psych/Soc'].forEach((label) => {
    assert.ok(summary.includes(label), `summary should list ${label}`);
  });
  assert.ok(summary.includes('No answers recorded'), 'the unanswered section must show the honest abstain state');
  // Honesty: the exam summary must NOT fabricate a blended / scaled MCAT score. The
  // MCAT scaled bounds (472..528), "scaled", and "composite" would be tell-tales of
  // one. Mentioning that memory/performance/readiness update on the dashboard is fine
  // and expected (it is a pointer, not a number), so the word itself is allowed.
  ['472', '528', 'scaled', 'composite'].forEach((mk) => {
    assert.ok(summary.indexOf(mk) === -1, `summary must not show a blended/scaled exam score: found ${JSON.stringify(mk)}`);
  });
  assert.ok(/\breadiness\b\s*(?:score)?\s*[:=]?\s*\d/.test(summary) === false, 'summary must not attach a number to readiness');
  assert.ok(summary.includes('not a single exam score'), 'summary should state plainly that these are raw tallies, not one exam score');

  // Exact running order actually observed.
  assert.deepStrictEqual(order, ['chem_phys', 'cars', 'bio_biochem', 'psych_soc']);

  // Each answered section's results were flushed to the SAME performance pipeline as a
  // normal timed test (mode "test"), tagged with the real section.
  const practice2 = pycmds
    .filter((c) => c.startsWith('vantage:practice2:'))
    .map((c) => JSON.parse(decodeURIComponent(c.slice('vantage:practice2:'.length))));
  const sectionsSent = practice2.map((p) => p.section);
  ['chem_phys', 'cars', 'bio_biochem'].forEach((s) => {
    assert.ok(sectionsSent.includes(s), `section ${s} answers should be reported to the host`);
  });
  assert.ok(practice2.every((p) => p.mode === 'test'), 'exam section answers should feed the pipeline tagged as a timed test');
}

// Answer `n` questions in the current section with no feedback appearing between them.
function answerSection(n, where) {
  for (let i = 0; i < n; i++) {
    assertNoFeedback(`${where} question ${i + 1}`);
    api.choose(0);
    api.nextTest();
  }
}
function sectionTag() {
  // The section currently running, read from the exam state via the plan order.
  const html = paneHTML();
  const map = { 'Chem/Phys reasoning': 'chem_phys', 'CARS practice': 'cars', 'Bio/Biochem reasoning': 'bio_biochem', 'Psych/Soc reasoning': 'psych_soc' };
  for (const title in map) if (html.includes(title)) return map[title];
  return '(unknown: ' + html.slice(0, 60) + ')';
}
function assertBreakTo(nextLabel, where) {
  const html = paneHTML();
  assert.ok(html.includes('>Break ') || html.includes('class="wrap pbreak"'), `expected a break screen ${where}`);
  assert.ok(html.includes('pbreaktimer'), `break ${where} should show a countdown`);
  assert.ok(html.includes(`Next up: ${nextLabel}`), `break ${where} should say next up: ${nextLabel}`);
  assertNoFeedback(`break ${where}`);
}
function assertBreakMinutesShown() {
  // Quick-run break is EXAM_SHORT.breakMin (0.2 min ~ 0:12); just confirm a real m:ss.
  assert.ok(/\d+:\d\d/.test(paneHTML()), 'break should render a m:ss countdown');
}
function fireBreakTimer() {
  nowMs += 60_000; // past the (short) break end
  fireActiveTimer();
}

try {
  run();
  passed = 1;
  console.log('Full-length exam: end-to-end flow  (module:', MODULE_PATH + ')');
  console.log('  ok   - drives a full shortened exam: chaining, break timer, skip, no early feedback, honest abstain summary');
  console.log('\n1 passed, 0 failed');
  process.exit(0);
} catch (e) {
  failed = 1;
  console.log('Full-length exam: end-to-end flow  (module:', MODULE_PATH + ')');
  console.log('  FAIL -', e.message);
  console.log('\n0 passed, 1 failed');
  process.exit(1);
}
