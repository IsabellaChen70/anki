/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Pure-logic unit tests for the full-length exam simulator (vantage_addon/web/
   practice.js). These drive the section-chaining plan and the cross-section summary
   headlessly (no DOM), proving the real MCAT figures, the chaining order, the break
   structure, and the honest abstain rule.

   practice.js is a browser IIFE (the desktop repo is an ES-module package), so it is
   loaded here by wrapping its source in a CommonJS function in THIS realm (so the
   arrays/objects it returns share the test's prototypes) with a `module` in scope,
   which triggers its test-only `module.exports`.

   Run:   node vantage_addon/tests/test_full_length_exam.cjs
   Set PRACTICE_JS to point at a different copy of practice.js (used to show the red
   baseline before the feature existed). */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const MODULE_PATH = process.env.PRACTICE_JS || path.join(__dirname, '..', 'web', 'practice.js');

// Load practice.js headlessly: no window/document (so its window.* writes are skipped
// by the `typeof window !== 'undefined'` guards) but a CommonJS module object so its
// test-only exports are populated. Runs in the current realm so returned values use
// the test's Array/Object prototypes (needed for assert.deepStrictEqual).
function loadExports(file) {
  const src = fs.readFileSync(file, 'utf8');
  const moduleObj = { exports: {} };
  // eslint-disable-next-line no-new-func
  const fn = new Function('module', 'exports', src + '\n;return module.exports;');
  return fn(moduleObj, moduleObj.exports);
}

let m = {};
try {
  m = loadExports(MODULE_PATH) || {};
} catch (e) {
  console.log('  (could not load module headlessly:', e.message + ')');
}

let passed = 0;
let failed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log('  ok   -', name);
  } catch (e) {
    failed += 1;
    console.log('  FAIL -', name);
    console.log('         ', e.message);
  }
}

console.log('Full-length exam: pure logic  (module:', MODULE_PATH + ')');

// 1. The real 4-section MCAT order with the app's real per-section budgets. The
//    (questions, minutes) here must match anki.vantage.scoring.SECTION_TIMING.
check('full plan is the real 4-section MCAT order with real budgets', () => {
  const plan = m.buildExamPlan({});
  assert.deepStrictEqual(plan.map((s) => s.section), ['chem_phys', 'cars', 'bio_biochem', 'psych_soc']);
  assert.deepStrictEqual(plan.map((s) => [s.count, s.minutes]), [[59, 95], [53, 90], [59, 95], [59, 95]]);
});

// 2. The real optional between-section breaks: 10 min, 30 min (mid-exam, after CARS),
//    10 min; the last section has none.
check('breaks are the AAMC 10 / 30 / 10 structure, last section has none', () => {
  const plan = m.buildExamPlan({});
  assert.deepStrictEqual(plan.map((s) => s.breakAfterMin), [10, 30, 10, 0]);
});

// 3. Science-only scope drops CARS (reconciling the title's "science sections") and
//    keeps the real science budgets and 10-minute breaks.
check('science-only scope runs the 3 science sections with 10-minute breaks', () => {
  const plan = m.buildExamPlan({ includeCars: false });
  assert.deepStrictEqual(plan.map((s) => s.section), ['chem_phys', 'bio_biochem', 'psych_soc']);
  assert.deepStrictEqual(plan.map((s) => [s.count, s.minutes]), [[59, 95], [59, 95], [59, 95]]);
  assert.deepStrictEqual(plan.map((s) => s.breakAfterMin), [10, 10, 0]);
});

// 4. Chaining: each finished section leads to a break with the right minutes and then
//    the next section, in order; only the last section leads to the summary.
check('sections chain in order with a break between each, summary only after the last', () => {
  const plan = m.buildExamPlan({});
  const seq = [];
  for (let i = 0; i < plan.length; i++) {
    const next = m.examNextPhase(plan, i);
    seq.push(next.phase === 'break' ? `break:${next.breakMin}->${plan[next.nextIdx].section}` : 'summary');
  }
  assert.deepStrictEqual(seq, [
    'break:10->cars', 'break:30->bio_biochem', 'break:10->psych_soc', 'summary',
  ]);
});

// 5. The cross-section summary is per-section raw tallies plus plain-sum totals, never
//    a blended/scaled/readiness score.
check('summary aggregates real per-section tallies without blending', () => {
  const agg = m.aggregateExamSummary([
    { section: 'chem_phys', count: 59, answered: 50, correct: 40 },
    { section: 'cars', count: 53, answered: 53, correct: 30 },
  ]);
  assert.strictEqual(agg.rows[0].pct, 80); // 40 of 50
  assert.strictEqual(agg.rows[1].pct, 57); // 30 of 53 rounds to 57
  assert.strictEqual(agg.totalCorrect, 70);
  assert.strictEqual(agg.totalAnswered, 103);
  assert.strictEqual(agg.totalPct, 68); // 70 of 103 rounds to 68
  assert.ok(!('score' in agg) && !('readiness' in agg) && !('scaled' in agg));
});

// 6. Give-up / abstain: a section with nothing answered shows no number instead of a
//    fabricated one, and does not pollute the totals.
check('a section with no answers abstains instead of fabricating a number', () => {
  const agg = m.aggregateExamSummary([
    { section: 'chem_phys', count: 59, answered: 10, correct: 7 },
    { section: 'cars', count: 53, answered: 0, correct: 0 },
    { section: 'bio_biochem', count: 59, answered: 0, correct: 0, notStarted: true },
  ]);
  assert.strictEqual(agg.rows[0].abstained, false);
  assert.strictEqual(agg.rows[1].abstained, true);
  assert.strictEqual(agg.rows[1].pct, null);
  assert.strictEqual(agg.rows[2].abstained, true);
  assert.strictEqual(agg.rows[2].notStarted, true);
  assert.strictEqual(agg.totalAnswered, 10);
  assert.strictEqual(agg.totalCorrect, 7);
});

// 7. The quick run is shortened (clearly not real timing) but keeps the same order and
//    a break between each section, so the flow is identical for testing.
check('quick run shortens counts/timers but keeps the section order', () => {
  const plan = m.buildExamPlan({ shortened: true });
  assert.deepStrictEqual(plan.map((s) => s.section), ['chem_phys', 'cars', 'bio_biochem', 'psych_soc']);
  assert.ok(plan.every((s) => s.count === m.EXAM_SHORT.count && s.minutes === m.EXAM_SHORT.min));
  assert.deepStrictEqual(
    plan.slice(0, 3).map((s) => s.breakAfterMin),
    [m.EXAM_SHORT.breakMin, m.EXAM_SHORT.breakMin, m.EXAM_SHORT.breakMin],
  );
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
