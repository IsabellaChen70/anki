/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Vantage dashboard renderer. Reads window.__VANTAGE__ (injected by the add-on),
   falling back to MOCK for standalone preview. Pure DOM, no framework.

   Every score shows the elements the brief requires: point, range, % of exam
   covered, a confidence ("how sure") indicator with its reason, last-updated
   time, and the give-up rule. Worded for the student, not the engineer. */

const ICON = {
  brain: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  gauge: '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
  grid: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  fwd: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/>',
  bolt: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  book: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  cloud: '<path d="M12 13v8"/><path d="m8 17 4 4 4-4"/><path d="M4.5 15.5A5 5 0 0 1 7 6a6 6 0 0 1 11.3 2A4.5 4.5 0 0 1 18 17"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
};

function svg(name) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg>`;
}
const pct = (x) => Math.round(x * 100) + '%';
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function bullets(lines) {
  if (!lines || !lines.length) return '';
  return `<ul class="reasons">${lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`;
}

// Confidence ("how sure") plus its reason. Coverage is deliberately NOT repeated
// here: it's the same number on every card, already shown once in the header chip
// and broken out per section in the Exam coverage panel.
function meta(how, reason) {
  const label = how === 'insufficient' ? 'not enough data yet' : how;
  const conf = `<div class="conf conf--${how}">Confidence: ${label}${reason ? ', ' + reason : ''}</div>`;
  return `<div class="cardmeta">${conf}</div>`;
}

// ---- Redesign shared helpers: status classification + the confidence chip ----
// Classify a 0..1 ratio into the shared red/amber/green status the redesign uses
// for bars, report-card tiles, and pills. The thresholds live here, once, instead
// of being sprinkled through markup: < 40% is red ("At risk"), 40-69% amber
// ("Watch"), >= 70% green ("Strong"). It never invents a number; callers pass a
// ratio the scoring core already produced.
const STATUS_PILL = { red: 'At risk', amber: 'Watch', green: 'Strong' };
function statusOf(ratio) {
  if (ratio < 0.4) return 'red';
  if (ratio < 0.7) return 'amber';
  return 'green';
}
// The white confidence pill shown inline on a score card. Carries the same honest
// "Confidence: <level> - <basis>" content the old meta() line did; abstaining
// scores never reach here (they render their own "not enough data yet" state).
function confChip(how, basis) {
  const label = how === 'insufficient' ? 'not enough data yet' : how;
  return `<span class="confchip confchip--${how}">Confidence: ${esc(label)}${basis ? ' \u00b7 ' + esc(basis) : ''}</span>`;
}

function pctCard(kind, title, sub, s, basis, abstainLine) {
  const cls = kind === 'memory' ? 'memory' : 'perf';
  const label = `<div class="card__label">${esc(title)}</div><div class="card__sub">${esc(sub)}</div>`;
  if (s.abstained) {
    const cta = kind === 'perf' ? '<button class="card__cta" onclick="vtab(\'practice\')">Start practice</button>' : '';
    return `<div class="card card--abstain">${label}
      <div class="abstain__title">Not enough data yet</div>
      ${bullets([abstainLine])}${cta}</div>`;
  }
  return `<div class="card card--${cls}">${label}
    <div class="metricline"><span class="metricline__val">${Math.round(s.point * 100)}%</span><span class="metricline__range">(${pct(s.low)}&ndash;${pct(s.high)})</span>${confChip(s.how_sure, basis)}</div>
  </div>`;
}

// Honest scale label for the readiness card. The projection is a labeled partial
// (three of the four sections) until CARS has real practice, then a full
// four-section projection. Reads the cars_modeled flag the scoring core set,
// falling back to whether a CARS section is present, so it never assumes either.
function readinessScale(s) {
  const carsModeled = s.cars_modeled || !!(s.sections && s.sections.cars);
  return carsModeled
    ? 'Covers all 4 sections'
    : 'Covers 3 of 4 sections, CARS not included yet';
}

// Short basis for the readiness confidence chip: the number of practice questions
// behind the projection when the latent-ability model is active, else the review
// count. Mirrors readinessReason's inputs; never a new number.
function readinessBasis(s, d) {
  if (s.model === 'irt_2pl_eap' && s.irt) {
    let nApp = 0;
    Object.keys(s.irt).forEach((k) => { nApp += (s.irt[k] && s.irt[k].n) || 0; });
    if (nApp > 0) return `${nApp} question${nApp === 1 ? '' : 's'}`;
  }
  return `${d.n_reviews} review${d.n_reviews === 1 ? '' : 's'}`;
}

function readinessCard(s, labels, d) {
  const head = `<div class="card__label">Readiness</div><div class="card__sub">your projected section scores</div>`;
  if (s.abstained) {
    const items = [];
    if (d.n_reviews < d.thresholds.reviews)
      items.push(`${d.thresholds.reviews} graded reviews (you have ${d.n_reviews})`);
    if (d.coverage < d.thresholds.coverage)
      items.push(`${pct(d.thresholds.coverage)} of the exam covered (you have ${pct(d.coverage)})`);
    if (d.performance.n < d.thresholds.performance_outcomes)
      items.push(`${d.thresholds.performance_outcomes} exam-style practice questions answered (you have ${d.performance.n})`);
    // The gates above can all be met yet readiness still abstains (e.g. no single
    // section has enough answered items yet). Never show an empty "You need:" list.
    if (!items.length) items.push('a bit more exam-style practice, spread across sections');
    return `<div class="card card--abstain">${head}
      <div class="abstain__title">No score yet</div>
      <p class="abstain__lead">You need:</p>${bullets(items)}
      <button class="card__cta" onclick="vtab('practice')">Start practice</button></div>`;
  }
  const subs = Object.entries(s.sections || {}).map(([k, b]) => {
    return `<div class="subrow"><div class="subrow__label">${esc(labels[k] || (k === 'cars' ? 'CARS' : k))}</div>
      <div class="subrow__score"><span class="subrow__val">${Math.round(b.point)}</span><span class="subrow__range">(${Math.round(b.low)}&ndash;${Math.round(b.high)})</span></div></div>`;
  }).join('');
  return `<div class="card card--ready">${head}
    <div class="subsections">${subs}</div>
    <div class="card__sub card__sub--scale">${readinessScale(s)}</div>
    ${confChip(s.how_sure, readinessBasis(s, d))}</div>`;
}

// Depth-aware, topic-grain coverage: the headline % and the per-section numbers
// come from how many AAMC topics actually have cards, so "% of the exam covered"
// and the topics-left list agree. Each section shows a small subject-colored dot
// and its percentage in the matching subject color; the name stays quiet grey and
// there is no progress bar, which would read as clutter without adding signal.
function coverageBlock(d) {
  const labels = d.section_labels;
  const bySec = d.topic_coverage_by_section || d.coverage_by_section || {};
  const secs = Object.keys(labels).map((k) =>
    `<div class="cover__sec cover__sec--${esc(k)}"><span class="cover__sec-dot"></span><span class="cover__sec-name">${esc(labels[k])}</span><span class="cover__sec-pct">${pct(bySec[k] || 0)}</span></div>`,
  ).join('');
  const overall = typeof d.topic_coverage === 'number' ? d.topic_coverage : d.coverage;
  return `<div class="coverblock">
    <div class="cover__overall"><span class="cover__num">${pct(overall)}</span><span class="cover__of">of the exam covered</span></div>
    <div class="cover__sections">${secs}</div>
    ${gapsBlock(d)}</div>`;
}

// How many topics-left rows show before the "see all" toggle: enough to read the
// top priorities without a long list, the rest one tap away (mirrors the
// study-next queue's own show-more).
const GAPS_SHOWN = 3;
let gapsShowAll = false;

// One topic still to study: its AAMC id, name, and how many of its topics have
// cards so far. On the desktop add-on (the only host that can run generation) the
// row also carries an inline Generate button, so a topic and its action sit on one
// line instead of the old separate list that repeated every title. The button
// fires the SAME source-traced generation pipeline as before (window.vgen).
function gapRow(d, g) {
  const thin = !(typeof g.covered === 'number' && typeof g.total === 'number' && g.covered >= g.total);
  const count = g.total ? `<span class="tgap__count">${g.covered}/${g.total} topics</span>` : '';
  const btn = (window.__VANTAGE_CARDGEN__ && thin)
    ? `<button class="genbtn" onclick="vgen('${esc(g.concept_id)}')" aria-label="Generate cards for ${esc(g.name || g.concept_id)}">${svg('bolt')} Generate</button>`
    : '';
  return `<div class="tgap tgap--${esc(g.section)}">
    <span class="tgap__name"><b>${esc(g.concept_id)}</b> ${esc(g.name)}</span>
    ${count}${btn}</div>`;
}

function gapsListInner(d) {
  const list = d.topic_gaps || [];
  const total = list.length;
  const showAll = gapsShowAll || total <= GAPS_SHOWN;
  const rows = (showAll ? list : list.slice(0, GAPS_SHOWN)).map((g) => gapRow(d, g)).join('');
  const more = total > GAPS_SHOWN
    ? `<button class="tgapsmore" onclick="vgaps()">${showAll ? 'Show fewer' : `See all ${total} topics`}</button>`
    : '';
  return rows + more;
}

// The honest note for the inline Generate button: each card is checked against its
// source first, where the cards land (the "Vantage Generated" deck), and what a
// tap that adds nothing means. Shown only where generation can run, so the
// mobile/preview list stays a plain to-do.
function gapsNote() {
  if (!window.__VANTAGE_CARDGEN__) return '';
  return '<div class="tgaps__note">Generate adds a few cards to your Vantage Generated deck, each checked against its source first. If a topic has nothing new to add, none are created.</div>';
}

function gapsBlock(d) {
  gapsShowAll = false;
  const list = d.topic_gaps || [];
  if (!list.length) return '';
  return `<div class="tgaps">
    <div class="tgaps__head">Most topics left to study</div>
    ${gapsNote()}
    <div class="tgaps__list" id="vtgaps">${gapsListInner(d)}</div>
  </div>`;
}

// Toggle the full topics-left list vs the first few (see GAPS_SHOWN), re-rendering
// just the list in place like the study-next queue's show-more.
window.vgaps = function () {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  gapsShowAll = !gapsShowAll;
  const el = document.getElementById('vtgaps');
  if (el) el.innerHTML = gapsListInner(d);
};

// Per-section flashcard progress = how much of this section you have both learned
// and retained, i.e. the section's mean FSRS recall R weighted by how much of the
// section you actually have cards for. Raw recall alone sits near the FSRS target
// retention (~95%) for every section, so on its own the bar reads uniformly high
// and tells you little. Scaling recall by the depth-aware per-section coverage
// (topic_coverage_by_section, falling back to coverage_by_section, then to plain
// recall when no coverage is exposed) gives a lower, more meaningful number that
// separates "studied a little, very well" from "learned most of the section". Both
// inputs are 0..1 from collect.gather / mobile_scoring; the product is clamped and
// classified with the shared statusOf. Still null when the section has no recall
// entry (no studied cards yet), so the card shows a plain note instead of a
// fabricated 0% bar for an active student.
function sectionFlashInfo(d, sec) {
  const r = (d.section_recall || {})[sec];
  if (r === null || r === undefined) return null;
  const bySec = d.topic_coverage_by_section || {};
  const bySecFallback = d.coverage_by_section || {};
  const cov = typeof bySec[sec] === 'number' ? bySec[sec]
    : typeof bySecFallback[sec] === 'number' ? bySecFallback[sec]
      : 1;
  const ratio = Math.max(0, Math.min(1, r * cov));
  return { ratio, status: statusOf(ratio) };
}
// Per-section reasoning accuracy from the exposed application outcomes. Needs
// enough answers to judge -- the same per-section gate readiness uses -- else null
// (honest abstain). Reads section_reason, which INCLUDES cars, so the CARS card can
// show its accuracy; section_outcomes (the 3 science sections that feed the scores)
// is the fallback and gives an identical number for those sections.
function sectionReasonInfo(d, sec) {
  const outs = (d.section_reason && d.section_reason[sec]) || (d.section_outcomes || {})[sec];
  if (!outs || !outs.length) return null;
  const minN = (d.thresholds && d.thresholds.readiness_per_section) || 5;
  if (outs.length < minN) return null;
  const correct = outs.reduce((a, b) => a + (b ? 1 : 0), 0);
  const ratio = correct / outs.length;
  return { ratio, status: statusOf(ratio) };
}
// The single reddest reasoning section (lowest accuracy AND in the red band), used
// to flag one card "Start here". Deterministic; null when nothing is red.
function reddestReasonSection(d) {
  const labels = d.section_labels || {};
  let best = null;
  Object.keys(labels).forEach((k) => {
    const info = sectionReasonInfo(d, k);
    if (info && info.status === 'red' && (!best || info.ratio < best.ratio)) best = { sec: k, ratio: info.ratio };
  });
  return best ? best.sec : null;
}
// One color-coded progress bar (flashcards recall or reasoning accuracy). `info`
// from the section*Info helpers, or null -> an honest note instead of a bar.
function secBar(label, info, emptyNote) {
  if (!info) return `<div class="secbar__note">${esc(emptyNote)}</div>`;
  const v = Math.round(info.ratio * 100);
  return `<div class="secbar">
    <span class="secbar__k">${esc(label)}</span>
    <div class="secbar__track"><div class="secbar__fill secbar__fill--${info.status}" style="width:${v}%"></div></div>
    <span class="secbar__v secbar__v--${info.status}">${v}%</span></div>`;
}
// One section card: its name, the same Flashcards / Reasoning launchers as before
// (unchanged handlers), and the color-coded progress bars. `flag` marks it the
// reddest reasoning section ("Start here").
function sectionCard(d, key, label, opts) {
  const acts = [];
  if (opts.flashcards) acts.push(`<button class="secbtn secbtn--flash" onclick="vstudy('${key}')">${svg('play')} Flashcards</button>`);
  if (opts.reason) acts.push(`<button class="secbtn secbtn--reason" onclick="vpractice.open('${key}')">${svg('book')} Reasoning</button>`);
  const bars = [];
  if (opts.flashcards) bars.push(secBar('Flashcards', sectionFlashInfo(d, key), 'Study a few cards to see your flashcard progress here.'));
  if (opts.reason) bars.push(secBar('Reasoning', sectionReasonInfo(d, key), 'Answer a few reasoning questions to see your accuracy here.'));
  const flag = opts.flag ? '<span class="seccard__flag">Start here</span>' : '';
  return `<div class="seccard seccard--${key}${opts.flag ? ' seccard--flag' : ''}">
    <div class="seccard__head">
      <div class="seccard__name">${esc(label)}${flag}</div>
      <div class="seccard__actions">${acts.join('')}</div>
    </div>
    <div class="secbars">${bars.join('')}</div>
  </div>`;
}

// One-tap "what should I study now" (Feature 2). Resolves the single highest-
// priority action from the pace/focus split the backend already computed
// (study_pace.reasoning_focus). Section = its default_section (the same suggestion
// the practice setup pre-selects); flashcards vs reasoning reuses the study_plan
// content-before-transfer split. Returns null (the honest wait state) when the
// give-up rule is already withholding both scores, or there is no section basis.
// CARS is never a focus section (no outline weight).
function focusNowChoice(d) {
  const f = d && d.study_pace && d.study_pace.reasoning_focus;
  const sec = f && f.has_focus ? f.default_section : null;
  const thin = d && d.memory && d.performance && d.memory.abstained && d.performance.abstained;
  if (!sec || thin) return null;
  const gap = ((d.study_plan && d.study_plan.study) || []).some((x) => x.section === sec);
  return { sec, action: gap ? 'flashcards' : 'reasoning' };
}

// The "Study now" card. `choice` from focusNowChoice, or null for the honest wait
// state. Reuses vstudy / vpractice.open verbatim, so the session-length cap and
// desktop/mobile routing are inherited with no new bridge command.
function focusNowCard(d, choice) {
  if (!choice) {
    return `<div class="focusnow focusnow--wait">
      <div class="focusnow__eyebrow">Study now</div>
      <div class="focusnow__title">Do a little more first</div>
      <p class="focusnow__lead">Study a few cards and answer a few questions. Then this will show the one thing to focus on next. For now, pick a section below.</p>
    </div>`;
  }
  const label = (d.section_labels && d.section_labels[choice.sec]) || choice.sec;
  const a = choice.action === 'flashcards'
    ? { icon: 'play', lead: 'Learn the material on flashcards first.', btn: `Study ${label} flashcards`, click: `vstudy('${choice.sec}')` }
    : { icon: 'book', lead: 'You have learned enough to test it, so try some reasoning questions.', btn: `Practice ${label} reasoning`, click: `vpractice.open('${choice.sec}')` };
  return `<div class="focusnow focusnow--${esc(choice.sec)}">
    <div class="focusnow__eyebrow">Study now</div>
    <div class="focusnow__title">Start with ${esc(label)}</div>
    <p class="focusnow__lead">${esc(a.lead)}</p>
    <button class="btn btn--study focusnow__go" onclick="${a.click}">${svg(a.icon)} ${esc(a.btn)}</button>
  </div>`;
}

// The single weakest science section by application-item accuracy (Feature 5).
// Read-only over the already-computed per-section outcomes (d.section_outcomes);
// picks the lowest, never recomputes a score. A section needs enough answered
// questions to judge (d.thresholds.readiness_per_section, the same per-section gate
// readiness uses). Deterministic tie-break (more evidence, then section key) so
// desktop and mobile agree. Returns null when no section qualifies (honest abstain).
function weakestSection(d) {
  const bySec = (d && d.section_outcomes) || {};
  const minN = (d && d.thresholds && d.thresholds.readiness_per_section) || 5;
  const cands = Object.keys(bySec).map((s) => {
    const outs = bySec[s] || [];
    const n = outs.length;
    const correct = outs.reduce((acc, b) => acc + (b ? 1 : 0), 0);
    return { section: s, n, accuracy: n ? correct / n : 1 };
  }).filter((c) => c.n >= minN);
  if (!cands.length) return null;
  cands.sort((a, b) => a.accuracy - b.accuracy || b.n - a.n || (a.section < b.section ? -1 : 1));
  return cands[0];
}

// The "Your weakest area" card (Feature 5): one tap into the weakest section's
// reasoning practice. Paired beside the "Study now" card with a distinct eyebrow
// so the two never read as duplicates (pace/focus vs measured performance). `w`
// from weakestSection.
function weakSpotCard(d, w) {
  const label = (d.section_labels && d.section_labels[w.section]) || w.section;
  const pctRight = Math.round(w.accuracy * 100);
  return `<div class="focusnow focusnow--weak">
    <div class="focusnow__eyebrow focusnow__eyebrow--weak">Your weakest area</div>
    <div class="focusnow__title">Focus on ${esc(label)}</div>
    <p class="focusnow__lead">Your answers here are your lowest so far, ${pctRight}% correct. A few reasoning questions will help the most.</p>
    <button class="btn btn--reason focusnow__go" onclick="vpractice.open('${esc(w.section)}')">${svg('bolt')} Practice ${esc(label)}</button>
  </div>`;
}

// Session length (Feature 3): the single "before you start" choice shared by the
// Flashcards and Reasoning launchers below. 0 = no limit (unchanged, study until
// exhausted). Governs only this Study & practice launcher, not the already-timed
// Test / Full-length exam cards.
window.__vSessionMin = window.__vSessionMin || 0;
const V_SESSION_PRESETS = [0, 5, 10, 20];
function sessionLenBlock() {
  const cur = Math.max(0, parseInt(window.__vSessionMin, 10) || 0);
  const onPreset = V_SESSION_PRESETS.includes(cur);
  const chips = V_SESSION_PRESETS.map((m) =>
    `<button class="pchip vseschip${cur === m ? ' pchip--on' : ''}" onclick="vsessionSet(${m})">${m === 0 ? 'No limit' : m + ' min'}</button>`,
  ).join('');
  const custom = `<input class="psetup__num vsescustom" type="number" min="1" max="180" inputmode="numeric"
      placeholder="min" value="${!onPreset && cur > 0 ? cur : ''}"
      aria-label="Custom session length in minutes"
      oninput="vsessionSet(this.value)">`;
  return `<div class="vseslen">
    <span class="vseslen__label">Study for</span>
    <div class="vseslen__chips">${chips}${custom}</div>
  </div>`;
}
window.vsessionSet = function (v) {
  const n = Math.max(0, Math.min(180, parseInt(v, 10) || 0));
  window.__vSessionMin = n;
  // Re-mark the preset chips without a full re-render (a custom value lights none).
  document.querySelectorAll('.vseschip').forEach((el, i) => {
    el.classList.toggle('pchip--on', V_SESSION_PRESETS[i] === n);
  });
};
// One launcher for flashcards + interleave. With a cap, send a distinct timed
// command the host understands; with no cap, keep the exact command sent today, so
// the untimed study-until-exhausted flow is byte-for-byte unchanged.
window.vStudyLaunch = function (key) {
  const m = Math.max(0, parseInt(window.__vSessionMin, 10) || 0);
  if (m > 0) vpy('studytimed:' + m + ':' + key);
  else vpy('study:' + key);
};

// The place to click into studying: flashcards for the 3 science sections,
// reasoning for all 4 (CARS included), and one interleaved-everything option.
// Mounted on the Practice tab (practice.js renderSetup calls this); the Dashboard
// tab is purely informational and carries no study-action buttons. This is the
// convergence point for the study-area features: (a) the Study now (F2) + Your
// weakest area (F5) CTA pair, (b) the session-length chooser (F3), (c) the section
// list. The Flagged-for-review launcher (F4) is mounted right after this block by
// practice.js renderSetup (it needs practice.js's findByStem), completing (d).
function studyBlock(d) {
  const labels = d.section_labels || {};
  // (a) The pace/focus "study now" CTA (F2) and the performance "your weakest
  // area" CTA (F5), side by side. Distinct eyebrows so they never read as
  // duplicates; the weak-spot card hides when it resolves to the SAME section AND
  // action (reasoning) as study-now (dedupe).
  const choice = focusNowChoice(d);
  const w = weakestSection(d);
  const dupe = !!(w && choice && choice.sec === w.section && choice.action === 'reasoning');
  const focusCards = [focusNowCard(d, choice)];
  if (w && !dupe) focusCards.push(weakSpotCard(d, w));
  const focusPair = `<section class="section"><div class="focusgrid">${focusCards.join('')}</div></section>`;
  // (c) the section list, now cards with color-coded flashcards + reasoning bars.
  // The interleave launcher (still routed through the session cap, F3) stays a
  // full-width dark row on top; the sections sit in a 2-up grid beneath it.
  const reddest = reddestReasonSection(d);
  const interleave = `<div class="srow srow--all">
    <div class="srow__meta"><div class="srow__name">Interleaved review</div></div>
    <div class="srow__actions"><button class="btn btn--study" onclick="vStudyLaunch('interleave')">${svg('layers')} Start mixed review</button></div></div>`;
  const cards = [];
  Object.keys(labels).forEach((k) => {
    cards.push(sectionCard(d, k, labels[k], { flashcards: true, reason: true, flag: k === reddest }));
  });
  cards.push(sectionCard(d, 'cars', 'CARS', { flashcards: false, reason: true, flag: reddest === 'cars' }));
  return `${focusPair}<section class="section">
    <div class="section__head"><div class="section__title section__title--group">Study &amp; practice</div></div>
    ${sessionLenBlock()}
    <div class="studygrid">${interleave}<div class="secgrid">${cards.join('')}</div></div>
  </section>`;
}

// The common full MCAT review sets, by prep-book subject. The student picks the
// set they own; "Study this next" then names their book. Kaplan and Princeton
// Review are clean subject sets; Examkrackers splits biology into Molecules
// (biochem/cell) and Systems, and folds organic chemistry into one combined
// Chemistry manual (there is no standalone Examkrackers organic chem book).
const BOOK_SETS = {
  kaplan: {
    label: 'Kaplan',
    books: {
      'Physics and Math': 'Kaplan MCAT Physics and Math Review',
      'General Chemistry': 'Kaplan MCAT General Chemistry Review',
      'Organic Chemistry': 'Kaplan MCAT Organic Chemistry Review',
      Biochemistry: 'Kaplan MCAT Biochemistry Review',
      Biology: 'Kaplan MCAT Biology Review',
      'Behavioral Sciences': 'Kaplan MCAT Behavioral Sciences Review',
    },
  },
  tpr: {
    label: 'Princeton Review',
    books: {
      'Physics and Math': 'The Princeton Review MCAT Physics and Math Review',
      'General Chemistry': 'The Princeton Review MCAT General Chemistry Review',
      'Organic Chemistry': 'The Princeton Review MCAT Organic Chemistry Review',
      Biochemistry: 'The Princeton Review MCAT Biochemistry Review',
      Biology: 'The Princeton Review MCAT Biology Review',
      'Behavioral Sciences': 'The Princeton Review MCAT Psychology and Sociology Review',
    },
  },
  ek: {
    label: 'Examkrackers',
    books: {
      'Physics and Math': 'Examkrackers MCAT Physics',
      'General Chemistry': 'Examkrackers MCAT Chemistry',
      'Organic Chemistry': 'Examkrackers MCAT Chemistry',
      Biochemistry: 'Examkrackers MCAT Biology 1: Molecules',
      Biology: 'Examkrackers MCAT Biology 1 & 2',
      'Behavioral Sciences': 'Examkrackers MCAT Psychology & Sociology',
    },
  },
};

// Real chapter titles per book set, researched from each publisher's actual
// tables of contents (Kaplan verified high-confidence against the ebook TOCs;
// Princeton Review and Examkrackers verified where a genuine TOC was available).
// Keyed by AAMC concept, then book set. Missing entries fall back to the generic
// topic below. Examkrackers uses "lectures"; we render them the same way.
const CHAPTER_BY_BOOK = {
  '4A': { kaplan: 'Kinematics and Dynamics', tpr: 'Kinematics and Mechanics', ek: 'Motion and Force' },
  '4B': { kaplan: 'Fluids', tpr: 'Fluids and Elasticity of Solids', ek: 'Fluids' },
  '4C': { kaplan: 'Electrochemistry', tpr: 'Electrochemistry', ek: 'Solutions and Electrochemistry' },
  '4D': { kaplan: 'Light and Optics', tpr: 'Light and Geometrical Optics', ek: 'Waves: Sound and Light' },
  '4E': { kaplan: 'Atomic Structure', tpr: 'Atomic Structure and Periodic Trends', ek: 'Introduction to General Chemistry' },
  '5A': { kaplan: 'Acids and Bases', tpr: 'Acids and Bases', ek: 'Acids and Bases' },
  '5B': { kaplan: 'Bonding and Chemical Interactions', tpr: 'Bonding and Intermolecular Forces', ek: 'Introduction to General Chemistry' },
  '5C': { kaplan: 'Separations and Purifications', tpr: 'Separations and Spectroscopy' },
  '5D': { kaplan: 'Analyzing Organic Reactions', tpr: 'Biologically Important Molecules', ek: 'Oxygen Containing Reactions' },
  '5E': { kaplan: 'Thermochemistry', tpr: 'Thermodynamics', ek: 'Thermodynamics and Kinetics' },
  '1A': { kaplan: 'Amino Acids, Peptides, and Proteins', tpr: 'Amino Acids and Proteins', ek: 'Biological Molecules and Enzymes' },
  '1B': { kaplan: 'RNA and the Genetic Code', tpr: 'Nucleic Acids', ek: 'Genetics' },
  '1C': { kaplan: 'Genetics and Evolution', tpr: 'Genetics and Evolution', ek: 'Genetics' },
  '1D': { kaplan: 'Bioenergetics and Regulation of Metabolism', tpr: 'Carbohydrate Metabolism', ek: 'Metabolism' },
  '2A': { kaplan: 'The Cell', tpr: 'Eukaryotic Cells', ek: 'The Cell' },
  '2B': { kaplan: 'The Cell', tpr: 'Microbiology' },
  '2C': { kaplan: 'Reproduction', tpr: 'Eukaryotic Cells', ek: 'The Cell' },
  '3A': { kaplan: 'The Nervous System and the Endocrine System', tpr: 'The Nervous and Endocrine Systems', ek: 'The Nervous System and The Endocrine System' },
  // 3B (the main organ systems) spans many chapters in every set; uses the topic fallback.
  '6A': { kaplan: 'Sensation and Perception', tpr: 'Sensation, Perception, and Cognition', ek: 'Biological Correlates of Psychology' },
  '6B': { kaplan: 'Cognition, Consciousness, and Language', tpr: 'Sensation, Perception, and Cognition', ek: 'Thought and Emotion' },
  '6C': { kaplan: 'Motivation, Emotion, and Stress', tpr: 'Behavioral Neuroscience', ek: 'Thought and Emotion' },
  '7A': { kaplan: 'Learning and Memory', tpr: 'Behavioral Neuroscience', ek: 'Identity and the Individual' },
  '7B': { kaplan: 'Social Processes, Attitudes, and Behavior', tpr: 'Social Psychology', ek: 'Relationships and Behavior' },
  '7C': { kaplan: 'Social Processes, Attitudes, and Behavior', tpr: 'Social Psychology', ek: 'Relationships and Behavior' },
  '8A': { kaplan: 'Identity and Personality', tpr: 'Social Psychology', ek: 'Identity and the Individual' },
  '8B': { kaplan: 'Social Thinking', tpr: 'Social Psychology', ek: 'Relationships and Behavior' },
  '8C': { kaplan: 'Social Interaction', tpr: 'Social Psychology', ek: 'Relationships and Behavior' },
  '9A': { kaplan: 'Social Structure and Demographics', tpr: 'Sociological Theories and Social Institutions', ek: 'The Biopsychosocial Model, Society and Culture' },
  '9B': { kaplan: 'Social Structure and Demographics', tpr: 'Sociological Theories and Social Institutions', ek: 'The Biopsychosocial Model, Society and Culture' },
  '10A': { kaplan: 'Social Stratification', tpr: 'Sociological Theories and Social Institutions', ek: 'The Biopsychosocial Model, Society and Culture' },
};

// Generic, edition-proof topic per concept. Fallback when a specific book set's
// real chapter isn't mapped above (e.g. topics that span several chapters).
const CHAPTER_TOPIC = {
  '4A': 'translational motion, work, and energy',
  '4B': 'fluids',
  '4C': 'electrochemistry and circuits',
  '4D': 'light, sound, and waves',
  '4E': 'atomic structure',
  '5A': 'acids, bases, and solutions',
  '5B': 'bonding and molecular structure',
  '5C': 'separations and spectroscopy',
  '5D': 'functional groups and organic reactions',
  '5E': 'thermodynamics and kinetics',
  '1A': 'amino acids, peptides, and proteins',
  '1B': 'gene expression: transcription and translation',
  '1C': 'genetics and inheritance',
  '1D': 'metabolism and bioenergetics',
  '2A': 'the cell and its membranes',
  '2B': 'microbiology: prokaryotes and viruses',
  '2C': 'the cell cycle and division',
  '3A': 'the nervous and endocrine systems',
  '3B': 'organ systems and physiology',
  '6A': 'sensation and perception',
  '6B': 'cognition, memory, and consciousness',
  '6C': 'emotion, stress, and motivation',
  '7A': 'learning and personality',
  '7B': 'social influence and group behavior',
  '7C': 'attitudes and persuasion',
  '8A': 'self-identity',
  '8B': 'social cognition: attribution and bias',
  '8C': 'social interaction',
  '9A': 'social structure and institutions',
  '9B': 'demographic characteristics and processes',
  '10A': 'social inequality',
};

function bookBrand(d) {
  return d && d.book_set && BOOK_SETS[d.book_set] ? d.book_set : 'kaplan';
}
// Khan Academy has no public deep-link API, but its search reliably resolves a
// concept keyword to the right lesson(s). We link each focus topic to a search
// for that exact term, so "Study this next" points at real lessons, not a
// generic landing page. Encode ' too (encodeURIComponent leaves it) so the URL
// is safe inside the single-quoted onclick handler.
const KHAN_SEARCH = 'https://www.khanacademy.org/search?page_search_query=';
function khanQuery(q) {
  return encodeURIComponent(String(q)).replace(/'/g, '%27');
}
function khanClick(q) {
  return `vpy('open:${KHAN_SEARCH}${khanQuery(q)}');return false`;
}

let nextIdx = 0;
// How many topics show before the "see all" toggle: enough to read the near-term
// queue at a glance without listing everything at once. The rest are one tap away.
const NEXT_SHOWN = 4;
let nextShowAll = false;

function nextList(d) {
  if (d.next_topics && d.next_topics.length) return d.next_topics;
  return d.best_next ? [d.best_next] : [];
}

// Where to study the open topic: the student's own book and chapter (with the
// book-set picker) plus per-topic Khan Academy lesson links. Same data and the
// same handlers (vbook, khanClick) as before, now housed inside the open row.
function nextWhere(d, bn) {
  const subject = bn.subject || '';
  if (!subject) return '';
  const brandKey = bookBrand(d);
  const book = BOOK_SETS[brandKey].books[subject] || '';
  const byBook = CHAPTER_BY_BOOK[bn.concept_id] || {};
  const chapter = byBook[brandKey] || CHAPTER_TOPIC[bn.concept_id] || (bn.topics && bn.topics[0]) || '';
  const unit = brandKey === 'ek' ? 'lecture' : 'chapter'; // Examkrackers numbers "lectures"
  const picker = `<select class="bookpick" aria-label="Your MCAT book set" onchange="vbook(this.value)">${Object.keys(
    BOOK_SETS,
  )
    .map((k) => `<option value="${k}"${k === brandKey ? ' selected' : ''}>${esc(BOOK_SETS[k].label)}</option>`)
    .join('')}</select>`;
  const readRow = book
    ? `<div class="where__row where__row--book"><span class="where__k">Read</span><span class="where__val">
         <span class="where__book">${esc(book)}</span>
         ${chapter ? `<span class="where__chapter">${esc(chapter)} ${unit}</span>` : ''}</span>${picker}</div>`
    : '';
  const topicList = bn.topics && bn.topics.length ? bn.topics : [];
  const topicLinks = topicList
    .map((t) => `<a href="#" onclick="${khanClick(t)}">${esc(t)}</a>`)
    .join('<span class="where__sep">&middot;</span>');
  const focusRow = topicLinks
    ? `<div class="where__row"><span class="where__k">Focus on</span><span class="where__val">
         <span class="where__links">${topicLinks}</span>
         <span class="where__cap">Each opens a free Khan Academy lesson</span></span></div>`
    : '';
  if (!readRow && !focusRow) return '';
  return `<div class="nextblock__where">${readRow}${focusRow}</div>`;
}

// One topic in the queue: rank, name, section, and how well studied so far. The
// open row (accordion) also carries the where-to-study detail below its header.
function nextRow(d, bn, idx, open) {
  const labels = d.section_labels || {};
  const state = bn.covered ? `${pct(bn.mastery)} recalled` : 'not studied yet';
  const secLabel = labels[bn.section] || bn.section || '';
  const topicsTag = bn.topics_total
    ? `<span class="nextrow__count">${bn.topics_covered}/${bn.topics_total} topics</span>` : '';
  return `<div class="nextrow nextrow--${esc(bn.section)}${open ? ' nextrow--open' : ''}">
    <button class="nextrow__head" onclick="vpick(${idx})" aria-expanded="${open ? 'true' : 'false'}">
      <span class="nextrow__rank">${idx + 1}</span>
      <span class="nextrow__body">
        <span class="nextrow__name">${esc(bn.name)}</span>
        <span class="nextrow__meta"><span class="nextrow__sec">${esc(secLabel)}</span><span class="nextrow__state">${esc(state)}</span>${topicsTag}</span>
      </span>
      <span class="nextrow__chev">${svg('fwd')}</span>
    </button>
    ${open ? nextWhere(d, bn) : ''}
  </div>`;
}

// The near-term study queue: the backend's ranked topics as a compact stack, so
// the next few priorities read at a glance instead of one page at a time. The
// order and the topics are the backend's, untouched; this only lays them out.
function renderNextInner(d) {
  const list = nextList(d);
  if (!list.length) {
    return '<div class="deco"></div><div class="nextblock__eyebrow">Study this next</div><div class="nextblock__title nextblock__title--empty">All caught up</div>';
  }
  if (nextIdx >= list.length) nextIdx = 0;
  const total = list.length;
  const showAll = nextShowAll || total <= NEXT_SHOWN;
  const visible = showAll ? list : list.slice(0, NEXT_SHOWN);
  const count = total > 1 ? `<span class="nextblock__count">${total} topics</span>` : '';
  const rows = visible.map((bn, i) => nextRow(d, bn, i, i === nextIdx)).join('');
  const more = total > NEXT_SHOWN
    ? `<button class="nextmore" onclick="vmore()">${showAll ? 'Show fewer' : `See all ${total} topics`}</button>`
    : '';
  return `<div class="deco"></div>
    <div class="nextblock__head"><div class="nextblock__eyebrow">Study this next</div>${count}</div>
    <div class="nextstack">${rows}</div>${more}`;
}

function nextBlock(d) {
  nextIdx = 0;
  nextShowAll = false;
  return `<div class="nextblock" id="nextblock">${renderNextInner(d)}</div>`;
}

// Toggle the full queue vs the first few. Keeps the open row visible when
// collapsing back so the where-to-study detail never hides itself.
window.vmore = function () {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  nextShowAll = !nextShowAll;
  if (!nextShowAll && nextIdx >= NEXT_SHOWN) nextIdx = 0;
  const el = document.getElementById('nextblock');
  if (el) el.innerHTML = renderNextInner(d);
};

// Open a topic in the queue. Accordion: exactly one row open at a time, with its
// where-to-study detail underneath. Re-renders in place so the rest is untouched.
window.vpick = function (idx) {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  const list = nextList(d);
  if (idx < 0 || idx >= list.length) return;
  nextIdx = idx;
  const el = document.getElementById('nextblock');
  if (el) el.innerHTML = renderNextInner(d);
};

// Switch the student's book set. Update the display in place (keeping the open
// topic) and persist the choice; the host stores it without forcing a reload.
window.vbook = function (brand) {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  d.book_set = brand;
  const el = document.getElementById('nextblock');
  if (el) el.innerHTML = renderNextInner(d);
  if (window.pycmd) vpy('bookset:' + brand);
};

function planItem(num, label, hint) {
  return `<div class="plan__item"><div class="plan__num">${num}</div>
    <div class="plan__lbl">${esc(label)}<span class="plan__hint">${esc(hint)}</span></div></div>`;
}

// Countdown to the exam plus a transparent daily target (a stated heuristic).
function planBlock(d) {
  const p = d.study_pace;
  if (!p) return '';
  const input = `<input class="datein" type="date" value="${esc(p.exam_date || '')}" oninput="vpy('examdatesave:' + this.value)" onchange="vpy('examdate:' + this.value)">`;
  if (!p.has_exam_date || p.passed) {
    const msg = p.message || 'Set your exam date to get a daily study target.';
    return `<section class="section"><div class="plancard plancard--set">
      <div class="plan__eyebrow">Exam countdown</div>
      <div class="plan__setrow"><div class="plan__title">${esc(msg)}</div><div>${input}</div></div>
    </div></section>`;
  }
  const dayWord = p.days_left === 1 ? 'day' : 'days';
  const s = (n) => (n === 1 ? '' : 's');
  const dl = p.days_left && p.days_left > 0 ? p.days_left : 1;
  // Pace scales with how close the exam is: the same work spread over fewer days
  // means more per day. When it works out to less than one a day, show a weekly
  // cadence so the number still moves as you change the date.
  const pace = (remaining, noun, hint) => {
    const rate = remaining / dl;
    if (rate >= 1) {
      const n = Math.ceil(rate);
      return planItem(n, `${noun}${s(n)} a day`, hint);
    }
    const n = Math.max(1, Math.ceil(rate * 7));
    return planItem(n, `${noun}${s(n)} a week`, hint);
  };
  const flash = p.flashcards_per_day || p.reviews_due;
  const flashHint = flash > p.reviews_due ? 'to get through your deck by exam day' : 'chosen for you today';
  const items = [planItem(flash, `flashcard${s(flash)} to study today`, flashHint)];
  if (p.new_remaining > 0) items.push(pace(p.new_remaining, 'new card', `${p.new_remaining} new cards left`));
  // Reasoning is a real daily study goal (a few a day, more as the exam nears),
  // so show the backend's per-day number, not a countdown to the confidence bar.
  if (p.reasoning_per_day > 0) {
    const n = p.reasoning_per_day;
    const hint = p.reasoning_remaining > 0 ? `${p.reasoning_remaining} more to a confident score` : 'keeps your score sharp';
    items.push(planItem(n, `reasoning question${s(n)} a day`, hint));
  }
  return `<section class="section"><div class="plancard">
    <div class="plan__eyebrow">Exam countdown</div>
    <div class="plan__count"><span class="plan__days">${p.days_left}</span> ${dayWord} until your MCAT</div>
    <div class="plan__daterow">${input}</div>
    <div class="plan__grid">${items.join('')}</div>
  </div></section>`;
}

// Compares recall (what you remember) with accuracy on real questions. A gap
// means recognizing an answer is not the same as reasoning to it. Student-facing:
// no model or statistics terms, just the two numbers and what they mean.
function calibrationBlock(d) {
  const c = d.calibration;
  if (!c) return '';
  const head = '<div class="section__head"><div class="section__title">Memory vs. real performance</div></div>';
  if (c.abstained) {
    return `<section class="section">${head}
      <div class="coverblock">
        <div class="abstain__title">Not enough practice yet</div>
        <p class="abstain__lead">Answer a few more practice questions to see whether what you remember holds up on new questions.</p>
      </div></section>`;
  }
  const ok = c.well_calibrated;
  const verdict = ok
    ? 'What you remember lines up with how you do on questions.'
    : 'You remember more than you can use on new questions yet.';
  const fromMem = Math.round(c.mean_predicted * 100);
  const onReal = Math.round(c.mean_observed * 100);
  return `<section class="section">${head}
    <div class="coverblock">
      <div class="calibsummary calibverdict--${ok ? 'ok' : 'off'}"><b>${verdict}</b></div>
      <div class="calib">
        <div class="calibbar"><span class="calibbar__k">From memory</span><div class="calibbar__track"><div class="calibbar__fill calibbar__fill--pred" style="width:${fromMem}%"></div></div><span class="calibbar__v">${fromMem}%</span></div>
        <div class="calibbar"><span class="calibbar__k">On real questions</span><div class="calibbar__track"><div class="calibbar__fill calibbar__fill--obs" style="width:${onReal}%"></div></div><span class="calibbar__v">${onReal}%</span></div>
      </div>
      ${meta(c.how_sure, 'based on ' + c.n + ' questions')}
    </div></section>`;
}

// The fluency illusion, concept by concept: topics recalled well on cards but
// missed once the question is reworded. The app's core thesis, made specific.
// The scoring layer lists a concept only after enough real answers and puts the
// widest gap first, so an empty list is honest silence, not a blank slate.
function fluencyPanel(d) {
  const items = d.fluency_items || [];
  const head = '<div class="section__head"><div class="section__title">Recall vs. using it</div></div>';
  const risks = items.filter((x) => x.fluency_risk);
  if (!risks.length) {
    const lead = items.length
      ? 'On the concepts you have practiced, your recall and your answers line up. Nothing to flag here.'
      : 'Answer a few reworded questions on concepts you have studied. Any recall you cannot yet apply will show up here.';
    return `<section class="section">${head}<div class="coverblock">
      <div class="abstain__title">No recall gaps to flag</div>
      <p class="abstain__lead">${lead}</p>
    </div></section>`;
  }
  const rows = risks.slice(0, 5).map((x) => {
    const name = x.name || x.concept_id;
    const label = (d.section_labels && d.section_labels[x.section]) || x.section || '';
    const rec = Math.round(x.recall * 100);
    const app = Math.round(x.application * 100);
    return `<div class="flurow">
      <div class="flurow__head"><span class="flurow__name">${esc(name)}</span>${label ? `<span class="fluchip">${esc(label)}</span>` : ''}</div>
      <div class="flubar"><span class="flubar__k">Recall</span><div class="flubar__track"><div class="flubar__fill flubar__fill--rec" style="width:${rec}%"></div></div><span class="flubar__v">${rec}%</span></div>
      <div class="flubar"><span class="flubar__k">On questions</span><div class="flubar__track"><div class="flubar__fill flubar__fill--app" style="width:${app}%"></div></div><span class="flubar__v">${app}%</span></div>
    </div>`;
  }).join('');
  const n = risks.length;
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary"><b>You recall these well but miss them when the wording changes.</b> Practice them as questions, not just cards.</div>
    <div class="flulist">${rows}</div>
    <div class="cover" style="margin-top:0.85rem">${n === 1 ? '1 concept' : n + ' concepts'} where recall runs ahead of what you can apply</div>
  </div></section>`;
}

const CONF_LABELS = { guess: 'Guessing', unsure: 'Unsure', sure: 'Sure' };
const CONF_ORDER = { guess: 0, unsure: 1, sure: 2 };
const MISS_LABELS = { content: 'Content gap', misread: 'Misread the question', trap: 'Trap answer', time: 'Rushed the reasoning', math: 'Arithmetic slip' };
// The AAMC reasoning skills, in plain words: the second axis of a miss (what the
// question tested), alongside the cause above (why the point was lost).
const SKILL_LABELS = { concepts: 'Applying concepts', reasoning: 'Scientific reasoning', research: 'Experiment design', data: 'Evaluating data' };

// Metacognition: did feeling sure line up with being right?
function confidencePanel(d) {
  const c = d.confidence;
  if (!c) return '';
  const head = '<div class="section__head"><div class="section__title">Confidence check</div></div>';
  if (c.abstained) {
    return `<section class="section">${head}<div class="coverblock">
      <div class="abstain__title">Not enough answers yet</div>
      <p class="abstain__lead">Mark how sure you are on each practice question. After a few, you'll see whether your confidence matches your results.</p>
    </div></section>`;
  }
  const rows = (c.levels || []).slice().sort((a, b) => CONF_ORDER[a.level] - CONF_ORDER[b.level]).map((l) => `<div class="calibbar">
      <span class="calibbar__k">${CONF_LABELS[l.level] || l.level} (${l.n})</span>
      <div class="calibbar__track"><div class="calibbar__fill calibbar__fill--obs" style="width:${Math.round(l.rate * 100)}%"></div></div>
      <span class="calibbar__v">${pct(l.rate)}</span></div>`).join('');
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary"><b>${esc(c.insight)}</b></div>
    <div class="calib">${rows}</div>
    <div class="cover" style="margin-top:0.85rem">based on ${c.n} answers</div>
  </div></section>`;
}

// One labelled bar group for a miss axis (cause or skill). `items` is the
// serialized [{<key>, count}] list; `labels` maps the key to plain words; `fill`
// is the bar color class. Shared so both axes render identically.
function missBars(items, keyName, labels, fill) {
  const list = items || [];
  const max = Math.max(...list.map((x) => x.count), 1);
  return list.map((x) => `<div class="calibbar">
      <span class="calibbar__k">${esc(labels[x[keyName]] || x[keyName])}</span>
      <div class="calibbar__track"><div class="calibbar__fill ${fill}" style="width:${Math.round((x.count / max) * 100)}%"></div></div>
      <span class="calibbar__v">${x.count}</span></div>`).join('');
}

// Diagnosis: not just WHERE points go, but WHY (the mistake cause) and WHAT KIND
// of thinking the missed question tested (the AAMC reasoning skill). Two axes of
// the same misses, each with its own honest give-up state.
function mistakesPanel(d) {
  const m = d.mistakes;
  const s = d.skills;
  if (!m && !s) return '';
  const head = '<div class="section__head"><div class="section__title">How you lose points</div></div>';
  // Both axes still thin: one honest empty state, no invented pattern.
  if ((!m || m.abstained) && (!s || s.abstained)) {
    return `<section class="section">${head}<div class="coverblock">
      <div class="abstain__title">Not enough misses to diagnose</div>
      <p class="abstain__lead">When you miss a question, tag why. Once you have a few, you'll see which kind of mistake costs you the most points, and which reasoning skill they test.</p>
    </div></section>`;
  }
  // Cause axis: why the point was lost.
  let causeBlock = '';
  if (m && !m.abstained) {
    const secLabel = (d.section_labels && d.section_labels[m.top_section]) || m.top_section || '';
    const topLabel = (MISS_LABELS[m.top_reason] || m.top_reason || '').toLowerCase();
    const lead = m.top_reason ? `Most points lost to <b>${esc(topLabel)}</b>${secLabel ? ', mostly in ' + esc(secLabel) : ''}.` : '';
    causeBlock = `<div class="calibsummary">${lead}</div>
      <div class="calib">${missBars(m.items, 'reason', MISS_LABELS, 'calibbar__fill--pred')}</div>`;
  }
  // Skill axis: what kind of thinking the misses tested. The actionable contrast,
  // e.g. the points are lost on evaluating data, not on the facts themselves.
  let skillBlock = '';
  if (s && !s.abstained) {
    const topLabel = (SKILL_LABELS[s.top_skill] || s.top_skill || '').toLowerCase();
    const lead = s.top_skill
      ? (s.top_skill === 'concepts'
        ? `These mostly come down to <b>applying concepts</b>.`
        : `You lose more to <b>${esc(topLabel)}</b> than to the facts themselves.`)
      : '';
    skillBlock = `<div class="calibsummary" style="margin-top:0.85rem">${lead}</div>
      <div class="calib">${missBars(s.items, 'skill', SKILL_LABELS, 'calibbar__fill--obs')}</div>`;
  } else if (s && s.abstained && m && !m.abstained) {
    // Cause is ready but skill isn't: name the gap honestly instead of guessing.
    skillBlock = `<div class="cover" style="margin-top:0.85rem">Keep practicing to see which reasoning skill these misses test.</div>`;
  }
  const basis = (m && !m.abstained) ? m.n_wrong : (s ? s.n_wrong : 0);
  return `<section class="section">${head}<div class="coverblock">
    ${causeBlock}
    ${skillBlock}
    <div class="cover" style="margin-top:0.85rem">based on ${basis} missed questions</div>
  </div></section>`;
}

// Content before transfer: learn on flashcards first, then practice reasoning.
function planPanel(d) {
  const p = d.study_plan;
  if (!p || (!(p.study || []).length && !(p.practice || []).length)) return '';
  const chips = (list, empty) => (list && list.length ? list.slice(0, 5).map((x) => `<span class="planchip">${esc(x.name)}</span>`).join('') : `<span class="planempty">${empty}</span>`);
  return `<section class="section">
    <div class="section__head"><div class="section__title section__title--group">Where to focus</div></div>
    <div class="plansplit">
      <div class="plancol"><div class="plancol__h">Study these</div><div class="planchips">${chips(p.study, 'nothing pressing')}</div></div>
      <div class="plancol plancol--ready"><div class="plancol__h">Ready to practice</div><div class="planchips">${chips(p.practice, 'study a bit more first')}</div></div>
    </div>
  </section>`;
}

// Pace-to-finish: your median time per question vs the real section budget.
function pacingPanel(d) {
  const p = d.pacing;
  if (!p) return '';
  const head = '<div class="section__head"><div class="section__title">Pacing</div></div>';
  if (p.abstained) {
    return `<section class="section">${head}<div class="coverblock">
      <div class="abstain__title">Not enough timed questions yet</div>
      <p class="abstain__lead">Each practice question is timed. After a few, you'll see whether you'd finish each section before time runs out.</p>
    </div></section>`;
  }
  const rows = (p.sections || []).map((s) => {
    const label = (d.section_labels && d.section_labels[s.section]) || (s.section === 'cars' ? 'CARS' : s.section);
    const verdict = s.on_pace ? `finishes with ${s.spare_min} min to spare` : `runs out with ${s.projected_left} unanswered`;
    return `<div class="pacerow">
      <div class="pacerow__sec">${esc(label)}</div>
      <div class="pacerow__nums"><span class="pacerow__you pacerow__you--${s.on_pace ? 'ok' : 'off'}">${Math.round(s.median_sec)}s</span><span class="pacerow__t"> / ${Math.round(s.target_sec)}s budget</span></div>
      <div class="pacerow__verdict pacerow__verdict--${s.on_pace ? 'ok' : 'off'}">${esc(verdict)}</div>
    </div>`;
  }).join('');
  const lead = p.overall_on_pace ? 'You are finishing sections in time.' : 'At this pace you would not finish every section.';
  // CARS reading pace, stated per passage (a speed signal, never a score). CARS is
  // pure reading comprehension, so the honest unit is minutes per passage, not per
  // question. Shown only when there is enough timed CARS practice; it stays quiet
  // otherwise rather than guessing, and never claims a humanities vs social sciences
  // split, which the answered items do not carry.
  const c = p.cars;
  let carsCallout = '';
  if (c && !c.abstained) {
    const pp = c.per_passage_min;
    const tgt = Math.round(c.target_passage_min);
    const line = c.on_pace
      ? `CARS reading pace: about ${pp} minutes per passage, inside the ${tgt} minute budget.`
      : `CARS reading pace: about ${pp} minutes per passage, ${c.over_budget_pct}% over the ${tgt} minute budget.`;
    const sub = c.on_pace
      ? 'Your reading pace is on track. Keep it steady on test day.'
      : 'CARS is really a reading speed test, so pace yourself by the passage and work on reading a little faster.';
    carsCallout = `<div class="calibsummary calibverdict--${c.on_pace ? 'ok' : 'off'}" style="margin-top:0.85rem"><b>${line}</b></div>
    <div class="cover" style="margin-top:0.35rem">${sub}</div>`;
  }
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary"><b>${lead}</b></div>
    <div class="pacelist">${rows}</div>
    <div class="cover" style="margin-top:0.85rem">your typical time per question vs each section's time budget</div>
    ${carsCallout}
  </div></section>`;
}

// Project the readiness composite to exam day at your current rate of improvement.
function trajectoryPanel(d) {
  const t = d.trajectory;
  if (!t) return '';
  // Label sits INSIDE the card as an eyebrow (like the Exam countdown) so the two
  // outlook cards line up at the top instead of an outside title pushing this down.
  const eyebrow = '<div class="plan__eyebrow" style="margin-bottom:0.85rem">Score trajectory</div>';
  // The target lives on the scale of the sections you're currently modeling: the 3
  // science sections (354-396), or the full 472-528 once you've practiced CARS.
  const lo = t.scale_lo || 354;
  const hi = t.scale_hi || 396;
  const input = `<input class="targetin" type="number" min="${lo}" max="${hi}" placeholder="target" value="${t.target || ''}" oninput="vpy('targetsave:' + this.value)" onchange="vpy('target:' + this.value)">`;
  if (t.abstained) {
    return `<section class="section"><div class="coverblock">${eyebrow}
      <div class="plan__setrow"><div class="plan__title">${esc(t.reason || 'Set a target score and an exam date.')}</div><div>Target (${lo}\u2013${hi}): ${input}</div></div>
    </div></section>`;
  }
  const secName = t.weakest_section === 'cars' ? 'CARS' : ((d.section_labels && d.section_labels[t.weakest_section]) || t.weakest_section || '');
  const verdict = t.on_pace ? 'On pace to hit your target.' : `Behind your target${secName ? ', focus on ' + esc(secName) : ''}.`;
  // Qualitative pace from the SAME projected-vs-target the trajectory already
  // computed (no new metric); replaces the raw points-per-week rate. A one-point
  // band around the target reads as "on pace" rather than exact-tie only.
  const proj = typeof t.projected === 'number' ? t.projected : null;
  const tgt = typeof t.target === 'number' ? t.target : null;
  let pace = t.on_pace ? 'on' : 'behind';
  if (proj !== null && tgt !== null) pace = proj < tgt ? 'behind' : proj > tgt + 1 ? 'ahead' : 'on';
  const paceLabel = pace === 'behind' ? 'Behind pace' : pace === 'ahead' ? 'Ahead of pace' : 'On pace';
  // Actionable pointer: reuse the weakest section and the daily reasoning target
  // already shown under Exam countdown. Never a new points-to-effort conversion.
  const sp = d.study_pace;
  const rday = sp && typeof sp.reasoning_per_day === 'number' && sp.reasoning_per_day > 0 ? sp.reasoning_per_day : 0;
  const qWord = rday === 1 ? 'question' : 'questions';
  let hint;
  if (pace === 'behind') {
    if (secName && rday) hint = `Aim today's ${rday} reasoning ${qWord} at ${secName}, your weakest section.`;
    else if (secName) hint = `Put your reasoning practice into ${secName}, your weakest section.`;
    else if (rday) hint = `Get through today's ${rday} reasoning ${qWord} to catch up.`;
    else hint = 'Keep up your daily reasoning and flashcards to catch up.';
  } else if (pace === 'ahead') {
    hint = 'Nice work. Keep your daily practice steady.';
  } else {
    hint = rday
      ? `Right on track. Keep today's ${rday} reasoning ${qWord} and your due flashcards going.`
      : 'Right on track. Keep your daily practice steady.';
  }
  return `<section class="section"><div class="coverblock">${eyebrow}
    <div class="calibsummary calibverdict--${t.on_pace ? 'ok' : 'off'}"><b>${verdict}</b></div>
    <div class="trajstats">
      <div class="trajstat"><span class="trajstat__num">${t.projected}</span><span class="trajstat__lbl">projected by exam day</span></div>
      <div class="trajstat"><span class="trajstat__num">${t.target}</span><span class="trajstat__lbl">your target</span></div>
    </div>
    <div class="pacestatus pacestatus--${pace}">
      <span class="pacestatus__badge">${paceLabel}</span>
      <span class="pacestatus__hint">${esc(hint)}</span>
    </div>
    <div class="cover" style="margin-top:0.85rem">Change target (${lo}\u2013${hi}): ${input}</div>
  </div></section>`;
}

// Honest empty state: the live app failed to compute scores. Never fall back to
// the demo numbers here, that would show fabricated results as if they were real.
function errorCard() {
  const msg = window.__VANTAGE_ERR__ || 'Something went wrong computing your scores. Tap Refresh to try again.';
  return `
  <header class="masthead">
    <div class="masthead__deco"><span class="c1"></span><span class="c2"></span><span class="sq"></span></div>
    <div class="masthead__row">
      <div><div class="brand__mark">Vantage<span class="dot">.</span></div></div>
      <div class="toolbar">
        <button class="btn btn--ghost" onclick="vpy('back')">${svg('back')} Back to Anki</button>
      </div>
    </div>
  </header>
  <div class="app__body">
  <section class="section">
    <div class="card card--abstain">
      <div class="abstain__title">Couldn't load your scores</div>
      <p class="abstain__lead">${esc(msg)}</p>
      <button class="card__cta" onclick="vpy('refresh')">Refresh</button>
    </div>
  </section>
  </div>`;
}

// A dashboard-open reminder: how many flashcards are due to review today. Reuses
// the SAME value the plan shows (d.study_pace.reviews_due) so the banner and the
// plan never diverge. Hidden when nothing is due; no fabricated number. "Study
// now" launches the due-card review directly (the same vStudyLaunch('interleave')
// the studyBlock "Start mixed review" uses, so the session-length cap is honored
// and both hosts open the real flashcard reviewer), not just a tab switch.
function dueBanner(d) {
  const sp = d.study_pace;
  const due = sp && typeof sp.reviews_due === 'number' ? sp.reviews_due : 0;
  if (!(due > 0)) return '';
  return `<div class="duebanner" role="status">
    <span class="duebanner__dot"></span>
    <span class="duebanner__text"><b>${due}</b> flashcard${due === 1 ? '' : 's'} due to review today</span>
    <button class="duebanner__btn" onclick="vStudyLaunch('interleave')">Study now</button>
  </div>`;
}

// ============================================================================
// Redesign: Dashboard "where to go next" banner + the Progress report card.
// Everything here is presentation. It classifies and phrases numbers the scoring
// core already produced (statusOf + the existing panels) and reuses the existing
// handlers verbatim. No new number is computed.
// ============================================================================

// The single next action, from the reddest signal the app already computes: the
// measured weakest section (lowest application accuracy), else the pace/focus
// suggestion. Returns null -- and the banner then hides -- when there is not
// enough to point anywhere yet, so the CTA is never fabricated. Routes through the
// SAME handlers the section launchers use (vpractice.open / vstudy).
function nextStep(d) {
  const w = weakestSection(d);
  const choice = focusNowChoice(d);
  let sec;
  let action;
  let reason;
  if (w) {
    sec = w.section;
    action = 'reasoning';
    const pctRight = Math.round(w.accuracy * 100);
    const off = d.pacing && !d.pacing.abstained && (d.pacing.sections || []).some((x) => x.section === sec && !x.on_pace);
    reason = off
      ? `Your weakest area at ${pctRight}%, and you're short on time there.`
      : `Your lowest section so far at ${pctRight}% correct.`;
  } else if (choice) {
    sec = choice.sec;
    action = choice.action;
  } else {
    return null;
  }
  const label = (d.section_labels && d.section_labels[sec]) || (sec === 'cars' ? 'CARS' : sec);
  const click = action === 'flashcards' ? `vstudy('${sec}')` : `vpractice.open('${sec}')`;
  const title = action === 'flashcards' ? `Study ${label} flashcards` : `Practice ${label} reasoning`;
  const btn = action === 'flashcards' ? `Start ${label} flashcards` : `Start ${label} reasoning`;
  const why = 'This is your weakest area by the answers you have logged so far, so a little focused work here moves your score the most.';
  return { title, reason, click, btn, why };
}

function nextStepBanner(d) {
  const ns = nextStep(d);
  if (!ns) return '';
  return `<div class="vnext" role="region" aria-label="Where to go next">
    <div class="vnext__body">
      <div class="vnext__eyebrow"><span class="vnext__dot"></span>Where to go next</div>
      <div class="vnext__title">${esc(ns.title)}</div>
      ${ns.reason ? `<div class="vnext__reason">${esc(ns.reason)}</div>` : ''}
      <div class="vnext__why-detail" id="vnextwhy" hidden>${esc(ns.why)}</div>
    </div>
    <div class="vnext__actions">
      <button class="vnext__go" onclick="${ns.click}">${esc(ns.btn)}</button>
      <button class="vnext__why" onclick="vwhy()" aria-controls="vnextwhy" aria-expanded="false">Why this?</button>
    </div>
  </div>`;
}
// Reveal the one-line rationale under the banner. Client-only; no bridge command.
window.vwhy = function () {
  const el = document.getElementById('vnextwhy');
  const btn = document.querySelector('.vnext__why');
  if (!el) return;
  const show = el.hasAttribute('hidden');
  if (show) el.removeAttribute('hidden'); else el.setAttribute('hidden', '');
  if (btn) btn.setAttribute('aria-expanded', show ? 'true' : 'false');
};

// ---- The Progress report card: one graded tile per area, grouped by status ----
// Each tile derives its status (red/amber/green, or neutral when the area still
// abstains) and a one-line verdict from the SAME data its drawer shows; the drawer
// is the existing panel builder, unchanged, so every honest-abstain state and
// handler inside it is preserved.
const MISS_SHORT = { content: 'Content gaps', misread: 'Misreads', trap: 'Trap answers', time: 'Rushing', math: 'Arithmetic slips' };

function coverageTile(d) {
  const overall = typeof d.topic_coverage === 'number' ? d.topic_coverage : (d.coverage || 0);
  const labels = d.section_labels || {};
  const bySec = d.topic_coverage_by_section || d.coverage_by_section || {};
  let weak = null;
  Object.keys(labels).forEach((k) => {
    const v = bySec[k];
    if (typeof v === 'number' && (!weak || v < weak.v)) weak = { k, v };
  });
  const detail = weak ? `${labels[weak.k]} is your least covered at ${pct(weak.v)}` : 'Across every section of the exam';
  const drawer = `${planPanel(d)}<div class="coverage">${coverageBlock(d)}${nextBlock(d)}</div>`;
  return { id: 'cov', name: 'Coverage', status: statusOf(overall), verdict: `${pct(overall)} of the exam covered`, detail, drawer };
}

function recallTile(d) {
  const items = d.fluency_items || [];
  const risks = items.filter((x) => x.fluency_risk);
  const drawer = fluencyPanel(d);
  if (!items.length) return { id: 'recall', name: 'Recall vs. using it', status: 'neutral', verdict: 'Not enough practice yet', detail: 'Answer a few reworded questions to compare recall with using it', drawer };
  if (!risks.length) return { id: 'recall', name: 'Recall vs. using it', status: 'green', verdict: 'Recall and answers line up', detail: 'Nothing you recall slips when the wording changes', drawer };
  const worst = risks[0];
  const name = worst.name || worst.concept_id;
  const n = risks.length;
  return {
    id: 'recall', name: 'Recall vs. using it', status: 'amber',
    verdict: `${n} concept${n === 1 ? '' : 's'} slip${n === 1 ? 's' : ''} when reworded`,
    detail: `${name}: ${pct(worst.recall)} recall, ${pct(worst.application)} on questions`,
    drawer,
  };
}

function loseTile(d) {
  const m = d.mistakes;
  const s = d.skills;
  const drawer = mistakesPanel(d);
  if ((!m || m.abstained) && (!s || s.abstained)) {
    return { id: 'lose', name: 'How you lose points', status: 'neutral', verdict: 'Not enough misses to diagnose', detail: 'Tag why you miss questions to see the pattern', drawer };
  }
  const nWrong = (m && !m.abstained) ? m.n_wrong : (s ? s.n_wrong : 0);
  const reason = (m && !m.abstained && m.top_reason) ? m.top_reason : null;
  const secKey = m && m.top_section;
  const secLabel = secKey ? ((d.section_labels && d.section_labels[secKey]) || (secKey === 'cars' ? 'CARS' : secKey)) : '';
  return {
    id: 'lose', name: 'How you lose points', status: 'amber',
    verdict: reason ? `${MISS_SHORT[reason] || 'Mistakes'} cost the most` : 'Where your points go',
    detail: `${nWrong} missed question${nWrong === 1 ? '' : 's'}${secLabel ? ', mostly ' + secLabel : ''}`,
    drawer,
  };
}

function memoryTile(d) {
  const c = d.calibration;
  const drawer = calibrationBlock(d);
  if (!c || c.abstained) return { id: 'mem', name: 'Memory', status: 'neutral', verdict: 'Not enough practice yet', detail: 'Answer more questions to compare memory with real performance', drawer };
  const recall = c.mean_predicted;
  const status = statusOf(recall);
  const word = status === 'green' ? 'solid' : status === 'amber' ? 'building' : 'still low';
  return {
    id: 'mem', name: 'Memory', status,
    verdict: `Your recall is ${word} at ${pct(recall)}`,
    detail: c.well_calibrated ? 'It lines up with how you do on questions' : 'But you use less of it on new questions',
    drawer,
  };
}

function confidenceTile(d) {
  const c = d.confidence;
  const drawer = confidencePanel(d);
  if (!c || c.abstained) return { id: 'conf', name: 'Confidence', status: 'neutral', verdict: 'Not enough answers yet', detail: 'Mark how sure you are to calibrate your confidence', drawer };
  const levels = c.levels || [];
  const sure = levels.find((l) => l.level === 'sure');
  const rate = sure ? sure.rate : (levels.length ? levels[levels.length - 1].rate : 0);
  return {
    id: 'conf', name: 'Confidence', status: statusOf(rate),
    verdict: sure ? `Right ${pct(sure.rate)} when you felt sure` : 'Your certainty vs. your results',
    detail: 'How well feeling sure matches being right',
    drawer,
  };
}

function pacingTile(d) {
  const p = d.pacing;
  const drawer = pacingPanel(d);
  if (!p || p.abstained) return { id: 'pace', name: 'Pacing', status: 'neutral', verdict: 'Not enough timed questions yet', detail: 'Each practice question is timed; a few more shows your pace', drawer };
  if (p.overall_on_pace) return { id: 'pace', name: 'Pacing', status: 'green', verdict: 'You finish sections in time', detail: 'Your pace is on track across sections', drawer };
  let worst = null;
  (p.sections || []).forEach((s) => {
    if (!s.on_pace && (!worst || (s.projected_left || 0) > (worst.projected_left || 0))) worst = s;
  });
  const carsOff = p.cars && !p.cars.abstained && !p.cars.on_pace;
  let verdict = 'You would not finish every section';
  let detail = 'At this pace you would not finish every section in time';
  if (worst) {
    const label = (d.section_labels && d.section_labels[worst.section]) || (worst.section === 'cars' ? 'CARS' : worst.section);
    verdict = `You'd run out of time in ${label}`;
    detail = `${Math.round(worst.median_sec)}s vs a ${Math.round(worst.target_sec)}s budget, ${worst.projected_left} question${worst.projected_left === 1 ? '' : 's'} left unanswered`;
  } else if (carsOff) {
    verdict = "You'd run out of time in CARS";
    detail = `About ${p.cars.per_passage_min} minutes per passage, ${p.cars.over_budget_pct}% over the reading budget`;
  }
  return { id: 'pace', name: 'Pacing', status: 'red', verdict, detail, drawer };
}

function progressTile(t, open) {
  const st = t.status;
  const pill = st === 'neutral' ? '' : `<span class="rtile__pill rtile__pill--${st}">${STATUS_PILL[st]}</span>`;
  const head = `<div class="rtile__head"><span class="rtile__name">${esc(t.name)}</span>${pill}</div>`;
  const verdict = `<div class="rtile__verdict">${esc(t.verdict)}</div>`;
  const detail = `<div class="rtile__detail">${esc(t.detail)}</div>`;
  if (st === 'red') {
    return `<button class="rtile rtile--red" onclick="vprog('${t.id}')" aria-expanded="${open ? 'true' : 'false'}">
      <div class="rtile__body">${head}${verdict}${detail}</div>
      <span class="rtile__open">${open ? 'Close' : 'Open'} &rsaquo;</span>
    </button>`;
  }
  return `<button class="rtile rtile--${st}" onclick="vprog('${t.id}')" aria-expanded="${open ? 'true' : 'false'}">${head}${verdict}${detail}</button>`;
}

function progressCard(d) {
  const open = window.__vProgOpen || null;
  const tiles = [coverageTile(d), recallTile(d), loseTile(d), memoryTile(d), confidenceTile(d), pacingTile(d)];
  const by = { red: [], amber: [], green: [], neutral: [] };
  tiles.forEach((t) => { (by[t.status] || by.neutral).push(t); });
  const groups = [
    { status: 'red', label: 'Needs attention', cls: '' },
    { status: 'amber', label: 'Keep an eye on', cls: 'rtiles--3' },
    { status: 'green', label: 'Doing well', cls: 'rtiles--2' },
    { status: 'neutral', label: 'Not enough data yet', cls: 'rtiles--3' },
  ];
  const parts = [];
  groups.forEach((g) => {
    const list = by[g.status];
    if (!list.length) return;
    parts.push(`<div class="rgroup__label"><span class="rgroup__dot rgroup__dot--${g.status}"></span>${esc(g.label)}</div>`);
    if (g.status === 'red') {
      // Red tiles are prominent full-width cards; the open one's drawer sits right
      // beneath it.
      list.forEach((t) => {
        parts.push(progressTile(t, open === t.id));
        if (open === t.id) parts.push(`<div class="pdrawer">${t.drawer}</div>`);
      });
    } else {
      parts.push(`<div class="rtiles ${g.cls}">${list.map((t) => progressTile(t, open === t.id)).join('')}</div>`);
      const openT = list.find((t) => t.id === open);
      if (openT) parts.push(`<div class="pdrawer">${openT.drawer}</div>`);
    }
  });
  const hint = open ? '' : '<div class="rhint">Tap a card for the detail.</div>';
  return `<div class="rcard">${parts.join('')}${hint}</div>`;
}
// Toggle the open report-card tile (one at a time) and re-render the Progress pane
// in place, so the rest of the page and the current tab are untouched.
window.vprog = function (id) {
  window.__vProgOpen = window.__vProgOpen === id ? null : id;
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  const pane = document.getElementById('pane-progress');
  if (pane) pane.innerHTML = progressCard(d);
};

function render() {
  const live = window.__VANTAGE_LIVE__;
  const d = window.__VANTAGE__ || (live ? null : MOCK);
  const app = document.getElementById('app');
  if (live && !d) {
    app.innerHTML = errorCard();
    return;
  }
  const memAbstain = `Study at least ${d.thresholds.memory_cards} cards to see this. You've studied ${d.memory.n}.`;
  const perfAbstain = `Answer at least ${d.thresholds.performance_outcomes} new questions to see this. You've answered ${d.performance.n}.`;
  const memBasis = `${d.memory.n} card${d.memory.n === 1 ? '' : 's'}`;
  const perfBasis = `${d.performance.n} question${d.performance.n === 1 ? '' : 's'}`;
  app.innerHTML = `
  <header class="masthead">
    <div class="masthead__deco"><span class="c1"></span><span class="c2"></span><span class="sq"></span></div>
    <div class="masthead__row">
      <div><div class="brand__mark">Vantage<span class="dot">.</span></div></div>
      <div class="toolbar">
        <button class="btn btn--ghost" id="vsyncbtn" onclick="vsync()">${svg('cloud')} <span id="vsynclbl">Sync</span></button>
        <button class="btn btn--ghost" onclick="vrefresh()">${svg('refresh')} Refresh</button>
        <button class="btn btn--ghost" onclick="vpy('back')">${svg('back')} Back to Anki</button>
        <span class="syncago" id="vsyncago">${vSyncAgoText(d.last_sync_ms, Date.now())}</span>
      </div>
    </div>
    <div class="chips">
      <span class="chip">${svg('grid')} ${pct(d.topic_coverage)} of the exam covered</span>
      <span class="chip">${svg('bolt')} ${d.n_reviews} reviews</span>
    </div>
    <nav class="tabs" role="tablist">
      <button class="tab tab--on" data-tab="dashboard" role="tab" onclick="vtab('dashboard')">Dashboard</button>
      <button class="tab" data-tab="practice" role="tab" onclick="vtab('practice')">Practice</button>
      <button class="tab" data-tab="progress" role="tab" onclick="vtab('progress')">Progress</button>
    </nav>
  </header>

  <div class="app__body">
  ${dueBanner(d)}
  <div class="tabpane tabpane--on" id="pane-dashboard" role="tabpanel">
    ${nextStepBanner(d)}
    <div class="outlook">
      ${planBlock(d)}
      ${trajectoryPanel(d)}
    </div>

    <section class="section">
      <div class="scores">
        <div class="scorestack">
          ${pctCard('memory', 'Memory', 'how well you remember your cards', d.memory, memBasis, memAbstain)}
          ${pctCard('perf', 'Performance', 'how well you apply it to new questions', d.performance, perfBasis, perfAbstain)}
        </div>
        ${readinessCard(d.readiness, d.section_labels, d)}
      </div>
    </section>
  </div>

  <div class="tabpane" id="pane-practice" role="tabpanel" hidden></div>

  <div class="tabpane" id="pane-progress" role="tabpanel" hidden>${progressCard(d)}</div>

  <div class="footmeta"><span>Scores updated ${esc(d.updated)}</span></div>
  </div>`;
  // Which tab to open after this (re)render. Desktop bakes it into
  // window.__VANTAGE_INITIAL_TAB__ (returning from study -> Practice; Refresh ->
  // your current tab). Mobile's Refresh reloads the asset itself, which cannot
  // re-bake, so there the wanted tab is handed across the reload in sessionStorage
  // instead. Resolve it ONCE per page load and cache on window: mobile re-renders
  // after the host injects live scores, and that second render must land on the
  // same tab without needing the (already consumed) sessionStorage hand-off.
  // Consuming it also means a stashed tab never leaks into a later reload that is
  // meant to land on Dashboard (a finished practice session, an exam-date edit).
  window.__vtab = 'dashboard';
  if (typeof window.__vtabWanted === 'undefined') {
    let want = window.__VANTAGE_INITIAL_TAB__;
    if (window.__VANTAGE_MOBILE__) {
      try {
        const stashed = sessionStorage.getItem('vantageRefreshTab');
        if (stashed) { sessionStorage.removeItem('vantageRefreshTab'); want = stashed; }
      } catch (e) { /* storage unavailable */ }
    }
    window.__vtabWanted = want;
  }
  const wantTab = window.__vtabWanted;
  if ((wantTab === 'practice' || wantTab === 'progress') && typeof window.vtab === 'function') window.vtab(wantTab);
  // Keep the "last synced" label honest while the page sits open. render() can run
  // twice on mobile (baked then live), so guard the interval to one instance; a
  // full-page swap (desktop reload / mobile asset reload) starts a fresh document
  // and re-arms it.
  vSyncAgoRefresh();
  if (!window.__vsyncTickStarted) {
    window.__vsyncTickStarted = true;
    setInterval(vSyncAgoRefresh, 60000);
  }
}

// Bridge to the app (desktop add-on or the AnkiDroid WebView). No-op in preview.
window.vpy = function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };

// Refresh, staying on the tab you're on (Dashboard, Practice, or Progress).
// Desktop rebuilds the page in Python, so the current tab rides along in the
// refresh:<tab> bridge and is baked back into the new page. Mobile reloads the
// asset itself, which cannot re-bake, so there the tab also rides across the
// reload in sessionStorage, read once when the page comes back. Plain
// vpy('refresh') is deliberately left for the flows meant to land on Dashboard
// (a finished practice session, error retry, sync).
window.vrefresh = function () {
  const tab = window.__vtab || 'dashboard';
  if (window.__VANTAGE_MOBILE__) {
    try { sessionStorage.setItem('vantageRefreshTab', tab); } catch (e) { /* storage off */ }
  }
  vpy('refresh:' + tab);
};

// Opt-in: ask the host to generate cards for one thin AAMC category. The host
// runs the existing generation pipeline (source-traced, gated); no-op without a
// bridge (offline preview just logs).
window.vgen = function (cid) { if (cid) vpy('gencards:' + cid); };

// Per-section Flashcards launcher. Routes through vStudyLaunch so a chosen session
// length (Feature 3) is honored; with no cap it sends the plain study:<section> as
// before. The host decides Mixed vs Blocked automatically from the section's card
// maturity, so there is no marker to pass (and no "mix:" path that could build an
// empty deck on mobile).
window.vstudy = function (key) { vStudyLaunch(key); };

// ---- Tabs: Dashboard / Practice / Progress (client-side, no reload) ----
window.__vtab = 'dashboard';
window.vtab = function (name) {
  window.__vtab = name;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('tab--on', t.dataset.tab === name));
  document.querySelectorAll('.tabpane').forEach((p) => {
    const on = p.id === 'pane-' + name;
    p.hidden = !on;
    p.classList.toggle('tabpane--on', on);
  });
  // Opening Practice mounts its setup screen (unless a session is already running).
  if (name === 'practice' && window.vpractice && window.vpractice.mount) window.vpractice.mount();
  try { window.scrollTo(0, 0); } catch (e) { /* preview */ }
};

// ---- Sync button: additive to auto-sync. Fires the host's real sync, shows a
// brief "Syncing..." state, then the host either reloads (success) or calls
// vantageSyncDone(false) so we show a plain-language error. ----
window.vsync = function () {
  const btn = document.getElementById('vsyncbtn');
  const lbl = document.getElementById('vsynclbl');
  if (btn && btn.dataset.busy === '1') return;
  if (btn) { btn.dataset.busy = '1'; btn.classList.add('btn--busy'); }
  if (lbl) lbl.textContent = 'Syncing...';
  const ago = document.getElementById('vsyncago');
  if (ago) ago.textContent = 'Syncing now';
  clearTimeout(window.__vsyncTimer);
  // Safety net: if the host never reports back, stop spinning and say so.
  window.__vsyncTimer = setTimeout(function () { window.vantageSyncDone(false); }, 45000);
  vpy('sync:trigger');
};
window.vantageSyncDone = function (ok) {
  clearTimeout(window.__vsyncTimer);
  if (ok) { vpy('refresh'); return; } // success: reload with fresh scores (resets the button)
  const btn = document.getElementById('vsyncbtn');
  const lbl = document.getElementById('vsynclbl');
  if (btn) { btn.dataset.busy = ''; btn.classList.remove('btn--busy'); }
  if (lbl) lbl.textContent = 'Sync';
  // A failed sync must NOT advance the indicator: restore the real last-synced
  // label from the unchanged col.ls the host injected.
  vSyncAgoRefresh();
  vmsg("Couldn't sync, check your connection");
};

// ---- "Last synced Xm ago" indicator. Reads the collection's core `ls` value
// (window.__VANTAGE__.last_sync_ms, ms) the host injects; never fabricates a time.
// 0 / absent -> "Never synced". Clock skew (a server mtime slightly ahead of the
// local clock) clamps to "just now". ----
function vSyncAgoText(ms, nowMs) {
  const t = Number(ms) || 0;
  if (t <= 0) return 'Never synced';
  let sec = Math.round((nowMs - t) / 1000);
  if (sec < 0) sec = 0;
  if (sec < 45) return 'Synced just now';
  const min = Math.round(sec / 60);
  if (min < 60) return 'Synced ' + min + 'm ago';
  const hr = Math.round(min / 60);
  if (hr < 24) return 'Synced ' + hr + 'h ago';
  return 'Synced ' + Math.round(hr / 24) + 'd ago';
}
function vSyncAgoRefresh() {
  const el = document.getElementById('vsyncago');
  if (!el) return;
  // Resolve the data source the same way render() does, so the offline MOCK preview
  // reads MOCK.last_sync_ms and the live app reads the injected window.__VANTAGE__.
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : (typeof MOCK !== 'undefined' ? MOCK : null));
  el.textContent = vSyncAgoText(d && d.last_sync_ms, Date.now());
}

// Small bottom-center message (sync errors, etc.). Self-contained, no stylesheet
// dependency beyond .vmsg in dashboard.css.
function vmsg(text) {
  let el = document.getElementById('vmsg');
  if (!el) {
    el = document.createElement('div');
    el.id = 'vmsg';
    el.className = 'vmsg';
    (document.body || document.documentElement).appendChild(el);
  }
  el.textContent = text;
  el.classList.add('vmsg--show');
  clearTimeout(window.__vmsgTimer);
  window.__vmsgTimer = setTimeout(function () { el.classList.remove('vmsg--show'); }, 3400);
}
window.vmsg = vmsg;

const MOCK = {
  coverage: 1.0, coverage_by_section: { chem_phys: 1.0, bio_biochem: 1.0, psych_soc: 1.0 },
  topic_coverage: 0.69, topic_coverage_by_section: { chem_phys: 0.71, bio_biochem: 0.74, psych_soc: 0.6 },
  topic_gaps: [
    { concept_id: '2B', name: 'Microbiology (prokaryotes, viruses)', section: 'bio_biochem', covered: 0, total: 6 },
    { concept_id: '5C', name: 'Separation and purification methods', section: 'chem_phys', covered: 1, total: 5 },
    { concept_id: '1B', name: 'Transmission of genetic information', section: 'bio_biochem', covered: 6, total: 10 },
    { concept_id: '7C', name: 'Attitude and behavior change', section: 'psych_soc', covered: 1, total: 4 },
  ],
  card_suggestions: [
    { concept_id: '2B', name: 'Microbiology (prokaryotes, viruses)', section: 'bio_biochem', covered: 0, total: 6 },
    { concept_id: '5C', name: 'Separation and purification methods', section: 'chem_phys', covered: 1, total: 5 },
    { concept_id: '1B', name: 'Transmission of genetic information', section: 'bio_biochem', covered: 6, total: 10 },
  ],
  outline_version: 'aamc-approx-2023.v1', n_reviews: 240, n_cards_seen: 72, ai_used: false, updated: '2026-07-01 08:00',
  section_labels: { chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' },
  section_maturity: {
    chem_phys: { mixed: true, reason: 'enough cards have matured', mature: 41, review: 60 },
    bio_biochem: { mixed: false, reason: 'still consolidating', mature: 9, review: 48 },
    psych_soc: { mixed: false, reason: 'not enough graduated cards yet', mature: 2, review: 5 },
  },
  // Per science-section mean FSRS recall R (0..1), the source of the Practice tab's
  // per-section Flashcards bar (see sectionFlashInfo). Non-zero here so the offline
  // preview shows real bars, not 0%.
  section_recall: { chem_phys: 0.89, bio_biochem: 0.9, psych_soc: 0.6 },
  thresholds: { memory_cards: 20, performance_outcomes: 20, reviews: 200, coverage: 0.5, readiness_per_section: 5 },
  // Per science-section application outcomes (1/0) for the weak-spot quick jump
  // preview. psych_soc is clearly weakest (2 of 6 = 33%).
  section_outcomes: { chem_phys: [1, 1, 0, 1, 1, 0, 1, 1], bio_biochem: [1, 1, 1, 0, 1, 1, 1], psych_soc: [0, 1, 0, 0, 1, 0] },
  best_next: { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', weight: 3, mastery: 0.0, covered: false, priority: 3.0,
    subject: 'Behavioral Sciences', topics: ['attribution', 'prejudice', 'stereotypes', 'social cognition'] },
  next_topics: [
    { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', mastery: 0.0, covered: false, subject: 'Behavioral Sciences', topics: ['attribution', 'prejudice', 'stereotypes', 'social cognition'] },
    { concept_id: '1A', name: 'Structure and function of proteins and amino acids', section: 'bio_biochem', mastery: 0.22, covered: true, subject: 'Biochemistry', topics: ['amino acids', 'proteins', 'enzymes', 'protein structure'] },
    { concept_id: '5D', name: 'Structure, function, and reactivity of biological molecules', section: 'chem_phys', mastery: 0.31, covered: true, subject: 'Organic Chemistry', topics: ['organic chemistry', 'functional groups', 'reactions', 'stereochemistry'] },
    { concept_id: '2B', name: 'Microbiology (prokaryotes, viruses)', section: 'bio_biochem', mastery: 0.0, covered: false, subject: 'Biology', topics: ['prokaryotes', 'bacteria', 'viruses', 'microbial genetics'] },
    { concept_id: '4C', name: 'Electrochemistry and electrical circuits', section: 'chem_phys', mastery: 0.4, covered: true, subject: 'General Chemistry', topics: ['electrochemistry', 'circuits', 'capacitors', 'resistance'] },
    { concept_id: '7C', name: 'Attitude and behavior change', section: 'psych_soc', mastery: 0.0, covered: false, subject: 'Behavioral Sciences', topics: ['attitude change', 'persuasion', 'cognitive dissonance', 'social influence'] },
  ],
  memory: { abstained: false, point: 0.89, low: 0.87, high: 0.90, how_sure: 'high', n: 72, reasons: [] },
  performance: { abstained: false, point: 0.66, low: 0.57, high: 0.73, how_sure: 'medium', n: 96, reasons: [] },
  readiness: { abstained: false, point: 376, low: 368, high: 381, how_sure: 'medium', n: 240, cars_modeled: false,
    model: 'irt_2pl_eap', modeled_sections: ['chem_phys', 'bio_biochem', 'psych_soc'],
    irt: { chem_phys: { theta: -0.2, theta_sd: 0.42, information: 7.1, n: 22 }, bio_biochem: { theta: 0.3, theta_sd: 0.38, information: 9.4, n: 28 }, psych_soc: { theta: 0.0, theta_sd: 0.55, information: 5.2, n: 16 } },
    sections: { chem_phys: { point: 124, low: 120, high: 128 }, bio_biochem: { point: 126, low: 122, high: 129 }, psych_soc: { point: 125, low: 121, high: 128 } }, reasons: [] },
  fluency_items: [
    { concept_id: '1A', name: 'Structure and function of proteins and amino acids', section: 'bio_biochem', recall: 0.91, application: 0.44, gap: 0.47, n_app: 9, fluency_risk: true },
    { concept_id: '5A', name: 'Acids, bases, and their equilibria', section: 'chem_phys', recall: 0.86, application: 0.55, gap: 0.31, n_app: 6, fluency_risk: true },
    { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', recall: 0.80, application: 0.62, gap: 0.18, n_app: 5, fluency_risk: true },
  ],
  calibration: { abstained: false, how_sure: 'medium', n: 24, brier: 0.187, mean_predicted: 0.89, mean_observed: 0.71, well_calibrated: false,
    bins: [{ lo: 0.6, hi: 0.8, n: 8, pred_mean: 0.72, obs_rate: 0.75 }, { lo: 0.8, hi: 1.0, n: 16, pred_mean: 0.93, obs_rate: 0.69 }] },
  study_pace: { has_exam_date: true, exam_date: '2026-08-30', days_left: 60, passed: false, reviews_due: 32, flashcards_per_day: 32,
    new_remaining: 0, new_per_day: 0, reasoning_target: 60, reasoning_done: 24, reasoning_today: 2, reasoning_remaining: 36, reasoning_per_day: 5,
    flashcards_to_exam: 1920, reasoning_to_exam: 300,
    // Exam-countdown-aware default reasoning split (Feature 2 reads default_section).
    reasoning_focus: { has_focus: true, default_section: 'bio_biochem', per_day: 5, days_to_exam: 60, concentration: 0.4,
      by_section: [
        { section: 'bio_biochem', weight: 0.35, coverage: 0.74, gap: 0.26, share: 0.5, target: 3 },
        { section: 'chem_phys', weight: 0.33, coverage: 0.71, gap: 0.29, share: 0.3, target: 1 },
        { section: 'psych_soc', weight: 0.32, coverage: 0.6, gap: 0.4, share: 0.2, target: 1 }] } },
  confidence: { abstained: false, n: 24, insight: 'When you felt sure you were right 70%. Slow down on the ones you are sure about.',
    levels: [{ level: 'guess', n: 6, rate: 0.5 }, { level: 'unsure', n: 8, rate: 0.62 }, { level: 'sure', n: 10, rate: 0.7 }] },
  mistakes: { abstained: false, n_wrong: 8, top_reason: 'trap', top_section: 'psych_soc',
    items: [{ reason: 'trap', count: 4 }, { reason: 'content', count: 2 }, { reason: 'misread', count: 1 }, { reason: 'time', count: 1 }] },
  skills: { abstained: false, n_wrong: 8, top_skill: 'data', top_section: 'psych_soc',
    items: [{ skill: 'data', count: 4 }, { skill: 'reasoning', count: 2 }, { skill: 'concepts', count: 1 }, { skill: 'research', count: 1 }] },
  study_plan: { study: [{ name: 'Social inequality', section: 'psych_soc' }, { name: 'Electrochemistry and electrical circuits', section: 'chem_phys' }],
    practice: [{ name: 'Structure and function of proteins and amino acids', section: 'bio_biochem' }, { name: 'Principles of bioenergetics and fuel molecule metabolism', section: 'bio_biochem' }] },
  pacing: { abstained: false, n: 24, overall_on_pace: false, sections: [
    { section: 'chem_phys', n: 8, median_sec: 112, target_sec: 97, on_pace: false, projected_left: 9, spare_min: 0 },
    { section: 'bio_biochem', n: 8, median_sec: 78, target_sec: 97, on_pace: true, projected_left: 0, spare_min: 18.4 },
    { section: 'psych_soc', n: 8, median_sec: 70, target_sec: 97, on_pace: true, projected_left: 0, spare_min: 26.5 }],
    cars: { abstained: false, n: 18, median_sec: 140, target_sec: 101.9, per_passage_min: 13.7, target_passage_min: 10, over_budget_pct: 37, on_pace: false } },
  trajectory: { abstained: false, projected: 388, target: 396, on_pace: false, per_week: 6.5, weakest_section: 'psych_soc', scale_lo: 354, scale_hi: 396, reason: '' },
  // Second look: previously-missed questions re-served after a delay. Raw counts,
  // distinct from the three scores. (Preview has none actually due to re-serve.)
  second_look: { due: [], due_count: 0, scheduled_count: 2, corrected: 3, still_failing: 1, attempts: 5 },
  // Last successful sync (ms) for the toolbar indicator preview; about 12 min ago.
  last_sync_ms: Date.now() - 12 * 60 * 1000,
  // Flagged-for-review launcher preview (Feature 4): a few flagged flashcards.
  flagged: { card_count: 3, reasoning: [] },
};

// Exposed so the AnkiDroid host can re-render after injecting live collection data.
window.__vantageRender = render;
document.addEventListener('DOMContentLoaded', render);
