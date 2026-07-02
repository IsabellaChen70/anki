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
    const cta = kind === 'perf' ? '<button class="card__cta" onclick="vpractice.open()">Start practice</button>' : '';
    return `<div class="card card--abstain">${head}
      <div class="abstain__title">Not enough data yet</div>
      ${bullets([abstainLine])}${cta}</div>`;
  }
  return `<div class="card card--${cls}">${head}
    <div class="metric metric--${cls}"><span class="metric__num">${Math.round(s.point * 100)}</span><span class="metric__unit">%</span></div>
    <div class="range"><b>(${pct(s.low)}&ndash;${pct(s.high)})</b></div>
    ${meta(s.how_sure, reason, coverage)}</div>`;
}

// Plain-language "how sure" for readiness. When the latent-ability estimate is
// active, describe the projection from how the student actually answered (which
// questions, not just how many) and how settled it is, never naming the model or
// its internals. Otherwise keep the reviews-and-coverage phrasing.
function readinessReason(s, d) {
  if (s.model === 'irt_2pl_eap' && s.irt) {
    let nApp = 0;
    Object.keys(s.irt).forEach((k) => { nApp += (s.irt[k] && s.irt[k].n) || 0; });
    const settle = s.how_sure === 'high'
      ? 'your section scores have settled into a narrow range'
      : s.how_sure === 'medium'
        ? 'your section scores are still settling'
        : 'your section scores can still move a lot';
    return nApp > 0
      ? `from how you answered ${nApp} practice question${nApp === 1 ? '' : 's'}, ${settle}`
      : settle;
  }
  return `based on ${d.n_reviews} reviews and ${pct(d.coverage)} of the exam covered`;
}

function readinessCard(s, labels, d) {
  const head = `<div class="card__top"><div class="iconwrap i-${s.abstained ? 'abstain' : 'ready'}">${svg('gauge')}</div>
      <div><div class="card__label">Readiness</div><div class="card__sub">your projected section scores</div></div></div>`;
  if (s.abstained) {
    const items = [];
    if (d.n_reviews < d.thresholds.reviews)
      items.push(`${d.thresholds.reviews} graded reviews (you have ${d.n_reviews})`);
    if (d.coverage < d.thresholds.coverage)
      items.push(`${pct(d.thresholds.coverage)} of the exam covered (you have ${pct(d.coverage)})`);
    if (d.performance.n < d.thresholds.performance_outcomes)
      items.push(`${d.thresholds.performance_outcomes} exam-style practice questions answered (you have ${d.performance.n})`);
    return `<div class="card card--abstain">${head}
      <div class="abstain__title">No score yet</div>
      <p class="abstain__lead">You need:</p>${bullets(items)}
      <button class="card__cta" onclick="vpractice.open()">Start practice</button></div>`;
  }
  const subs = Object.entries(s.sections || {}).map(([k, b]) => {
    return `<div class="subrow"><div class="subrow__label">${esc(labels[k] || k)}</div>
      <div class="subrow__score"><span class="subrow__val">${Math.round(b.point)}</span><span class="subrow__range">(${Math.round(b.low)}&ndash;${Math.round(b.high)})</span></div></div>`;
  }).join('');
  const reason = readinessReason(s, d);
  const nSec = Object.keys(s.sections || {}).length;
  const partial = `<div class="readypartial">Covers ${nSec} of the 4 MCAT sections. CARS is not scored.</div>`;
  return `<div class="card card--ready">${head}
    <div class="subsections">${subs}</div>
    ${partial}
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

function studyRow(key, label, sub, opts) {
  const acts = [];
  if (opts.flashcards) acts.push(`<button class="btn btn--study" onclick="vpy('study:${key}')">${svg('play')} Flashcards</button>`);
  if (opts.reason) acts.push(`<button class="btn btn--reason" onclick="vpractice.open('${key}')">${svg('book')} Reasoning</button>`);
  const subHtml = sub ? `<div class="srow__sub">${esc(sub)}</div>` : '';
  return `<div class="srow srow--${key}">
    <div class="srow__meta"><div class="srow__name">${esc(label)}</div>${subHtml}</div>
    <div class="srow__actions">${acts.join('')}</div></div>`;
}

// The place to click into studying: flashcards for the 3 science sections,
// reasoning for all 4 (CARS included), and one interleaved-everything option.
function studyBlock(d) {
  const labels = d.section_labels || {};
  const rows = [];
  rows.push(`<div class="srow srow--all">
    <div class="srow__meta"><div class="srow__name">Interleaved review</div></div>
    <div class="srow__actions"><button class="btn btn--study" onclick="vpy('study:interleave')">${svg('layers')} Start mixed review</button></div></div>`);
  Object.keys(labels).forEach((k) => {
    rows.push(studyRow(k, labels[k], '', { flashcards: true, reason: true }));
  });
  rows.push(studyRow('cars', 'CARS', 'reading reasoning practice', { flashcards: false, reason: true }));
  return `<section class="section">
    <div class="section__head"><div class="section__title">Study &amp; practice</div></div>
    <div class="studygrid">${rows.join('')}</div>
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

function nextList(d) {
  if (d.next_topics && d.next_topics.length) return d.next_topics;
  return d.best_next ? [d.best_next] : [];
}

// One ranked topic at a time, with prev/next paging through the rest.
function renderNextTopic(d) {
  const list = nextList(d);
  if (!list.length) return '<div class="deco"></div><div class="nextblock__eyebrow">Study this next</div><div class="nextblock__title">All caught up</div>';
  if (nextIdx >= list.length) nextIdx = 0;
  const bn = list[nextIdx];
  const total = list.length;
  const state = bn.covered ? `${pct(bn.mastery)} recalled` : 'not studied yet';
  const subject = bn.subject || '';
  const brandKey = bookBrand(d);
  const book = subject ? BOOK_SETS[brandKey].books[subject] || '' : '';
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
  const where = subject ? `<div class="nextblock__where">
      ${readRow}
      ${focusRow}
    </div>` : '';
  const pager = total > 1 ? `<div class="nextpager">
      <button class="nextnav" ${nextIdx === 0 ? 'disabled' : ''} onclick="vnext(-1)" aria-label="Previous topic">${svg('back')}</button>
      <span class="nextpager__count">${nextIdx + 1} of ${total}</span>
      <button class="nextnav" ${nextIdx === total - 1 ? 'disabled' : ''} onclick="vnext(1)" aria-label="Next topic">${svg('fwd')}</button>
    </div>` : '';
  return `<div class="deco"></div>
    <div class="nextblock__head"><div class="nextblock__eyebrow">Study this next</div>${pager}</div>
    <div class="nextblock__title">${esc(bn.name)}</div>
    <div class="nextblock__meta">
      <span class="tag tag--accent">${esc((d.section_labels && d.section_labels[bn.section]) || bn.section)}</span>
      <span class="tag">${esc(state)}</span>
    </div>
    ${where}`;
}

function nextBlock(d) {
  nextIdx = 0;
  return `<div class="nextblock" id="nextblock">${renderNextTopic(d)}</div>`;
}

window.vnext = function (dir) {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  const list = nextList(d);
  nextIdx = Math.max(0, Math.min(list.length - 1, nextIdx + dir));
  const el = document.getElementById('nextblock');
  if (el) el.innerHTML = renderNextTopic(d);
};

// Switch the student's book set. Update the display in place (keeping the paged
// topic) and persist the choice; the host stores it without forcing a reload.
window.vbook = function (brand) {
  const d = window.__VANTAGE__ || (window.__VANTAGE_LIVE__ ? null : MOCK);
  if (!d) return;
  d.book_set = brand;
  const el = document.getElementById('nextblock');
  if (el) el.innerHTML = renderNextTopic(d);
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
  const input = `<input class="datein" type="date" value="${esc(p.exam_date || '')}" onchange="vpy('examdate:' + this.value)">`;
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
    <div class="plan__note">To stay on pace: clear today's flashcards and keep up your daily reasoning practice.</div>
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
      ${meta(c.how_sure, 'based on ' + c.n + ' questions', null)}
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
    <div class="cover" style="margin-top:0.85rem">right answers by how sure you felt, based on ${c.n} answers</div>
  </div></section>`;
}

// Diagnosis: which failure mode costs the most points, and where.
function mistakesPanel(d) {
  const m = d.mistakes;
  if (!m) return '';
  const head = '<div class="section__head"><div class="section__title">How you lose points</div></div>';
  if (m.abstained) {
    return `<section class="section">${head}<div class="coverblock">
      <div class="abstain__title">Not enough misses to diagnose</div>
      <p class="abstain__lead">When you miss a question, tag why. You'll see which kind of mistake costs you the most points.</p>
    </div></section>`;
  }
  const max = Math.max(...(m.items || []).map((x) => x.count), 1);
  const rows = (m.items || []).map((x) => `<div class="calibbar">
      <span class="calibbar__k">${esc(MISS_LABELS[x.reason] || x.reason)}</span>
      <div class="calibbar__track"><div class="calibbar__fill calibbar__fill--pred" style="width:${Math.round((x.count / max) * 100)}%"></div></div>
      <span class="calibbar__v">${x.count}</span></div>`).join('');
  const secLabel = (d.section_labels && d.section_labels[m.top_section]) || m.top_section || '';
  const topLabel = (MISS_LABELS[m.top_reason] || m.top_reason || '').toLowerCase();
  const lead = m.top_reason ? `Most points lost to <b>${esc(topLabel)}</b>${secLabel ? ', mostly in ' + esc(secLabel) : ''}.` : '';
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary">${lead}</div>
    <div class="calib">${rows}</div>
    <div class="cover" style="margin-top:0.85rem">based on ${m.n_wrong} missed questions</div>
  </div></section>`;
}

// Content before transfer: learn on flashcards first, then practice reasoning.
function planPanel(d) {
  const p = d.study_plan;
  if (!p || (!(p.study || []).length && !(p.practice || []).length)) return '';
  const chips = (list, empty) => (list && list.length ? list.slice(0, 5).map((x) => `<span class="planchip">${esc(x.name)}</span>`).join('') : `<span class="planempty">${empty}</span>`);
  return `<section class="section">
    <div class="section__head"><div class="section__title">Learn first, then practice</div></div>
    <div class="plansplit">
      <div class="plancol"><div class="plancol__h">Learn first, on flashcards</div><div class="planchips">${chips(p.study, 'nothing pressing')}</div></div>
      <div class="plancol plancol--ready"><div class="plancol__h">Ready to practice, with reasoning</div><div class="planchips">${chips(p.practice, 'study a bit more first')}</div></div>
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
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary"><b>${lead}</b></div>
    <div class="pacelist">${rows}</div>
    <div class="cover" style="margin-top:0.85rem">your typical time per question vs each section's time budget</div>
  </div></section>`;
}

// Project the readiness composite to exam day at your current rate of improvement.
function trajectoryPanel(d) {
  const t = d.trajectory;
  if (!t) return '';
  const head = '<div class="section__head"><div class="section__title">Score trajectory</div></div>';
  const input = `<input class="targetin" type="number" min="354" max="396" placeholder="target" value="${t.target || ''}" onchange="vpy('target:' + this.value)">`;
  if (t.abstained) {
    return `<section class="section">${head}<div class="coverblock">
      <div class="plan__setrow"><div class="plan__title">${esc(t.reason || 'Set a target score and an exam date.')}</div><div>Target: ${input}</div></div>
    </div></section>`;
  }
  const secLabel = (d.section_labels && d.section_labels[t.weakest_section]) || t.weakest_section || '';
  const verdict = t.on_pace ? 'On pace to hit your target.' : `Behind your target${secLabel ? ', focus on ' + esc(secLabel) : ''}.`;
  const wk = (t.per_week > 0 ? '+' : '') + t.per_week;
  return `<section class="section">${head}<div class="coverblock">
    <div class="calibsummary calibverdict--${t.on_pace ? 'ok' : 'off'}"><b>${verdict}</b></div>
    <div class="trajstats">
      <div class="trajstat"><span class="trajstat__num">${t.projected}</span><span class="trajstat__lbl">projected by exam day</span></div>
      <div class="trajstat"><span class="trajstat__num">${t.target}</span><span class="trajstat__lbl">your target</span></div>
      <div class="trajstat"><span class="trajstat__num">${wk}</span><span class="trajstat__lbl">points per week</span></div>
    </div>
    <div class="cover" style="margin-top:0.85rem">Covers your three section scores, not CARS yet. Change target: ${input}</div>
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
  <section class="section">
    <div class="card card--abstain">
      <div class="abstain__title">Couldn't load your scores</div>
      <p class="abstain__lead">${esc(msg)}</p>
      <button class="card__cta" onclick="vpy('refresh')">Refresh</button>
    </div>
  </section>`;
}

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
  const memReason = `based on ${d.memory.n} cards studied`;
  const perfReason = `based on ${d.performance.n} questions answered`;
  app.innerHTML = `
  <header class="masthead">
    <div class="masthead__deco"><span class="c1"></span><span class="c2"></span><span class="sq"></span></div>
    <div class="masthead__row">
      <div><div class="brand__mark">Vantage<span class="dot">.</span></div></div>
      <div class="toolbar">
        <button class="btn btn--ghost" onclick="vpy('refresh')">${svg('refresh')} Refresh</button>
        <button class="btn btn--ghost" onclick="vpy('back')">${svg('back')} Back to Anki</button>
      </div>
    </div>
    <div class="chips">
      <span class="chip">${svg('grid')} ${pct(d.coverage)} of the exam covered</span>
      <span class="chip">${svg('bolt')} ${d.n_reviews} reviews</span>
    </div>
  </header>

  ${planBlock(d)}

  <section class="section">
    <div class="scores">
      ${pctCard('memory', 'brain', 'Memory', 'how well you remember your cards', d.memory, d.coverage, memReason, memAbstain)}
      ${pctCard('perf', 'target', 'Performance', 'how well you apply it to new questions', d.performance, d.coverage, perfReason, perfAbstain)}
      ${readinessCard(d.readiness, d.section_labels, d)}
    </div>
  </section>

  ${studyBlock(d)}

  ${planPanel(d)}

  <section class="section">
    <div class="section__head"><div class="section__title">Exam coverage</div></div>
    <div class="coverage">${coverageBlock(d)}${nextBlock(d)}</div>
  </section>

  <div class="insights">
    ${calibrationBlock(d)}
    ${fluencyPanel(d)}
    ${confidencePanel(d)}
    ${mistakesPanel(d)}
    ${pacingPanel(d)}
    ${trajectoryPanel(d)}
  </div>

  <p class="giveup">No readiness score until you have ${d.thresholds.reviews} graded reviews, ${pct(d.thresholds.coverage)} of the exam covered, and some exam-style practice questions.</p>

  <div class="footmeta"><span>Scores updated ${esc(d.updated)}</span></div>`;
}

// Bridge to the app (desktop add-on or the AnkiDroid WebView). No-op in preview.
window.vpy = function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };

const MOCK = {
  coverage: 0.79, coverage_by_section: { chem_phys: 1.0, bio_biochem: 1.0, psych_soc: 0.42 },
  outline_version: 'aamc-approx-2023.v1', n_reviews: 240, n_cards_seen: 72, ai_used: false, updated: '2026-07-01 08:00',
  section_labels: { chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' },
  thresholds: { memory_cards: 20, performance_outcomes: 20, reviews: 200, coverage: 0.5 },
  best_next: { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', weight: 3, mastery: 0.0, covered: false, priority: 3.0,
    subject: 'Behavioral Sciences', topics: ['attribution', 'prejudice', 'stereotypes', 'social cognition'] },
  next_topics: [
    { concept_id: '8B', name: 'Social thinking', section: 'psych_soc', mastery: 0.0, covered: false, subject: 'Behavioral Sciences', topics: ['attribution', 'prejudice', 'stereotypes', 'social cognition'] },
    { concept_id: '1A', name: 'Structure and function of proteins and amino acids', section: 'bio_biochem', mastery: 0.22, covered: true, subject: 'Biochemistry', topics: ['amino acids', 'proteins', 'enzymes', 'protein structure'] },
    { concept_id: '5D', name: 'Structure, function, and reactivity of biological molecules', section: 'chem_phys', mastery: 0.31, covered: true, subject: 'Organic Chemistry', topics: ['organic chemistry', 'functional groups', 'reactions', 'stereochemistry'] },
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
    new_remaining: 0, new_per_day: 0, reasoning_target: 60, reasoning_done: 24, reasoning_remaining: 36, reasoning_per_day: 5 },
  confidence: { abstained: false, n: 24, insight: 'When you felt sure you were right 70%. Slow down on the ones you are sure about.',
    levels: [{ level: 'guess', n: 6, rate: 0.5 }, { level: 'unsure', n: 8, rate: 0.62 }, { level: 'sure', n: 10, rate: 0.7 }] },
  mistakes: { abstained: false, n_wrong: 8, top_reason: 'trap', top_section: 'psych_soc',
    items: [{ reason: 'trap', count: 4 }, { reason: 'content', count: 2 }, { reason: 'misread', count: 1 }, { reason: 'time', count: 1 }] },
  study_plan: { study: [{ name: 'Social inequality' }, { name: 'Electrochemistry and electrical circuits' }],
    practice: [{ name: 'Structure and function of proteins and amino acids' }, { name: 'Principles of bioenergetics and fuel molecule metabolism' }] },
  pacing: { abstained: false, n: 24, overall_on_pace: false, sections: [
    { section: 'chem_phys', n: 8, median_sec: 112, target_sec: 97, on_pace: false, projected_left: 9, spare_min: 0 },
    { section: 'bio_biochem', n: 8, median_sec: 78, target_sec: 97, on_pace: true, projected_left: 0, spare_min: 18.4 },
    { section: 'psych_soc', n: 8, median_sec: 70, target_sec: 97, on_pace: true, projected_left: 0, spare_min: 26.5 }] },
  trajectory: { abstained: false, projected: 388, target: 396, on_pace: false, per_week: 6.5, weakest_section: 'psych_soc', reason: '' },
};

// Exposed so the AnkiDroid host can re-render after injecting live collection data.
window.__vantageRender = render;
document.addEventListener('DOMContentLoaded', render);
