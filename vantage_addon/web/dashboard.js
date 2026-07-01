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
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/>',
  bolt: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
};

function svg(name, extra) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="${extra || ''}">${ICON[name]}</svg>`;
}
const pct = (x) => Math.round(x * 100) + '%';
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function bullets(lines) {
  if (!lines || !lines.length) return '';
  return `<ul class="reasons">${lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`;
}

// Confidence ("how sure") plus its reason, and the % of the exam covered.
function meta(how, reason, coverage) {
  const label = how === 'insufficient' ? 'not enough data yet' : how;
  const conf = `<div class="conf conf--${how}">Confidence: ${label}${reason ? ', ' + reason : ''}</div>`;
  const cov = coverage == null ? '' : `<div class="cover">${pct(coverage)} of the exam covered</div>`;
  return `<div class="cardmeta">${conf}${cov}</div>`;
}

function pctCard(kind, iconName, title, sub, s, coverage, reason, abstainLine) {
  const cls = kind === 'memory' ? 'memory' : 'perf';
  const head = `<div class="card__top"><div class="iconwrap i-${s.abstained ? 'abstain' : cls}">${svg(iconName)}</div>
      <div><div class="card__label">${esc(title)}</div><div class="card__sub">${esc(sub)}</div></div></div>`;
  if (s.abstained) {
    return `<div class="card card--abstain">${head}
      <div class="abstain__title">Not enough data yet</div>
      ${bullets([abstainLine])}${meta('insufficient', '', coverage)}</div>`;
  }
  return `<div class="card card--${cls}">${head}
    <div class="metric metric--${cls}"><span class="metric__num">${Math.round(s.point * 100)}</span><span class="metric__unit">%</span></div>
    <div class="range"><b>(${pct(s.low)}&ndash;${pct(s.high)})</b></div>
    ${meta(s.how_sure, reason, coverage)}</div>`;
}

function readinessCard(s, labels, d) {
  const head = `<div class="card__top"><div class="iconwrap i-${s.abstained ? 'abstain' : 'ready'}">${svg('gauge')}</div>
      <div><div class="card__label">Readiness</div><div class="card__sub">your projected section scores</div></div></div>`;
  if (s.abstained) {
    const items = [];
    if (d.n_reviews < d.thresholds.reviews)
      items.push(`${d.thresholds.reviews} reviews (you have ${d.n_reviews})`);
    if (d.coverage < d.thresholds.coverage)
      items.push(`${pct(d.thresholds.coverage)} of the exam covered (you have ${pct(d.coverage)})`);
    return `<div class="card card--abstain">${head}
      <div class="abstain__title">No score yet</div>
      <p class="abstain__lead">You need:</p>${bullets(items)}${meta('insufficient', '', d.coverage)}</div>`;
  }
  const subs = Object.entries(s.sections || {}).map(([k, b]) => {
    return `<div class="subrow"><div class="subrow__label">${esc(labels[k] || k)}</div>
      <div class="subrow__score"><span class="subrow__val">${Math.round(b.point)}</span><span class="subrow__range">(${Math.round(b.low)}&ndash;${Math.round(b.high)})</span></div></div>`;
  }).join('');
  const reason = `based on ${d.n_reviews} reviews and ${pct(d.coverage)} coverage`;
  return `<div class="card card--ready">${head}
    <div class="subsections">${subs}</div>
    ${meta(s.how_sure, reason, d.coverage)}</div>`;
}

function coverageBlock(d) {
  const labels = d.section_labels;
  const bars = Object.keys(labels).map((k) => {
    const v = (d.coverage_by_section && d.coverage_by_section[k]) || 0;
    return `<div class="bar bar--${k}"><div class="bar__head"><span>${esc(labels[k])}</span><span>${pct(v)}</span></div>
      <div class="bar__track"><div class="bar__fill" style="width:${Math.round(v * 100)}%"></div></div></div>`;
  }).join('');
  return `<div class="coverblock">
    <div class="cover__overall"><span class="cover__num">${pct(d.coverage)}</span><span class="cover__of">of the exam covered</span></div>
    <div class="bars">${bars}</div></div>`;
}

function nextBlock(d) {
  const bn = d.best_next;
  if (!bn) return '<div class="nextblock"><div class="deco"></div><div class="nextblock__eyebrow">Study this next</div><div class="nextblock__title">All caught up</div></div>';
  const state = bn.covered ? `${pct(bn.mastery)} recalled` : 'not studied yet';
  return `<div class="nextblock"><div class="deco"></div>
    <div class="nextblock__eyebrow">Study this next</div>
    <div class="nextblock__title">${esc(bn.name)}</div>
    <div class="nextblock__meta">
      <span class="tag tag--accent">${esc((d.section_labels && d.section_labels[bn.section]) || bn.section)}</span>
      <span class="tag">${esc(state)}</span>
    </div></div>`;
}

function render() {
  const d = window.__VANTAGE__ || MOCK;
  const app = document.getElementById('app');
  const memAbstain = `Study at least ${d.thresholds.memory_cards} cards to see this. You've studied ${d.memory.n}.`;
  const perfAbstain = `Answer at least ${d.thresholds.performance_outcomes} new questions to see this. You've answered ${d.performance.n}.`;
  const memReason = `based on ${d.memory.n} cards studied`;
  const perfReason = `based on ${d.performance.n} questions answered`;
  app.innerHTML = `
  <header class="masthead">
    <div class="masthead__deco"><span class="c1"></span><span class="c2"></span><span class="sq"></span></div>
    <div class="masthead__row">
      <div><div class="brand__mark">Vantage<span class="dot">.</span></div></div>
      <div class="toolbar">
        <button class="btn btn--primary" onclick="vpy('study')">${svg('play')} Study now</button>
        <button class="btn btn--ghost" onclick="vpy('refresh')">${svg('refresh')} Refresh</button>
        <button class="btn btn--ghost" onclick="vpy('back')">${svg('back')} Back to Anki</button>
      </div>
    </div>
    <div class="chips">
      <span class="chip">${svg('grid')} ${pct(d.coverage)} of the exam covered</span>
      <span class="chip">${svg('bolt')} ${d.n_reviews} reviews</span>
      <span class="chip">${svg('layers')} ${d.n_cards_seen} cards studied</span>
    </div>
  </header>

  <section class="section">
    <div class="scores">
      ${pctCard('memory', 'brain', 'Memory', 'how well you remember your cards', d.memory, d.coverage, memReason, memAbstain)}
      ${pctCard('perf', 'target', 'Performance', 'how well you apply it to new questions', d.performance, d.coverage, perfReason, perfAbstain)}
      ${readinessCard(d.readiness, d.section_labels, d)}
    </div>
  </section>

  <section class="section">
    <div class="section__head"><div class="section__title">Exam coverage</div></div>
    <div class="coverage">${coverageBlock(d)}${nextBlock(d)}</div>
  </section>

  <div class="note">${svg('shield')}
    <p><b>When Vantage won't guess.</b> No readiness score until you have at least ${d.thresholds.reviews} graded reviews and ${pct(d.thresholds.coverage)} of the exam covered. Below that line it shows what is missing and the best next topic, not a number.</p></div>

  <div class="footmeta"><span>Scores updated ${esc(d.updated)}</span></div>`;
}

// Bridge to the app (desktop add-on or the AnkiDroid WebView). No-op in preview.
window.vpy = function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };

const MOCK = {
  coverage: 0.79, coverage_by_section: { chem_phys: 1.0, bio_biochem: 1.0, psych_soc: 0.42 },
  outline_version: 'aamc-approx-2023.v1', n_reviews: 240, n_cards_seen: 72, ai_used: false, updated: '2026-07-01 08:00',
  section_labels: { chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' },
  thresholds: { memory_cards: 20, performance_outcomes: 20, reviews: 200, coverage: 0.5 },
  best_next: { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', weight: 3, mastery: 0.0, covered: false, priority: 3.0 },
  memory: { abstained: false, point: 0.89, low: 0.87, high: 0.90, how_sure: 'high', n: 72, reasons: [] },
  performance: { abstained: false, point: 0.66, low: 0.57, high: 0.73, how_sure: 'medium', n: 96, reasons: [] },
  readiness: { abstained: false, point: 376, low: 368, high: 381, how_sure: 'medium', n: 240, cars_modeled: false,
    sections: { chem_phys: { point: 124, low: 120, high: 128 }, bio_biochem: { point: 126, low: 122, high: 129 }, psych_soc: { point: 125, low: 121, high: 128 } }, reasons: [] },
};

document.addEventListener('DOMContentLoaded', render);
