/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Vantage reasoning practice. Passage-based application questions, the same
   tagged application-item type the Performance and Readiness scores read. Opens
   inside the dashboard via window.vpractice.open(section); results are reported
   through vpy so the host can fold them into the per-section Performance score.
   Four banks: CARS reading reasoning, plus one science-reasoning set each for
   Chem/Phys, Bio/Biochem, and Psych/Soc. */
(function () {
  const BANKS = {
    cars: {
      title: 'CARS practice',
      passage: {
        label: 'Passage',
        paragraphs: [
          "Every translation is an argument about what a text is for. The translator who renders a poem line by line, keeping its literal sense, treats meaning as cargo to be carried across intact. Another, who reworks the rhythm and lets a metaphor shift to keep the music alive, treats the poem as an experience to be reproduced in a reader who will never see the original. Neither is simply right. The first risks delivering a faithful corpse: accurate, and dead on the page. The second risks writing a new poem and signing someone else's name to it.",
          "What both share is a refusal to pretend the problem away. The worst translations are not the boldest but the most complacent, the ones that assume a word in one language has a twin waiting in another. Languages are not codes for one fixed set of ideas; they carve the world at different joints. To translate honestly is to choose, again and again, which loss to accept. The reader who wants a translation with no loss at all is asking for the original, and the original is the one thing they cannot read.",
        ],
      },
      questions: [
        {
          stem: "The central claim of the passage is that translation:",
          choices: [
            "should always preserve a text's literal meaning",
            "is impossible and not worth attempting",
            "means choosing which losses to accept, with no loss-free option",
            "is easiest when two languages share common roots",
          ],
          answer: 2,
          explain: "The author rejects both extremes as not simply right and lands on translation as a repeated choice of which loss to accept.",
        },
        {
          stem: "By a faithful corpse, the author most nearly means a translation that is:",
          choices: [
            "accurate in wording but lifeless as a reading experience",
            "altered to sound more beautiful than the original",
            "revised so often it lost its author",
            "focused on music at the expense of sense",
          ],
          answer: 0,
          explain: "It pairs with accurate, and dead on the page: literal fidelity that loses the living experience of the text.",
        },
        {
          stem: "The author regards translators who assume a word has a twin waiting in another language as:",
          choices: [
            "admirably cautious",
            "the most complacent, and the worst",
            "bold but forgivable",
            "rare in current practice",
          ],
          answer: 1,
          explain: "The passage calls these the most complacent and ties them to the worst translations.",
        },
        {
          stem: "The final sentence about wanting no loss at all mainly serves to:",
          choices: [
            "offer a practical tip for picking a translation",
            "show that the demand for a loss-free translation defeats itself",
            "concede that translation is usually pointless",
            "open a separate argument about how people read",
          ],
          answer: 1,
          explain: "Wanting zero loss means wanting the original, which the reader cannot read, so the demand collapses on itself.",
        },
        {
          stem: "The phrase languages carve the world at different joints most directly supports the idea that:",
          choices: [
            "grammar rules are essentially the same across languages",
            "different languages divide meaning in non-matching ways",
            "translation is a mechanical, rule-based process",
            "older languages are harder to translate",
          ],
          answer: 1,
          explain: "If languages carve the world differently, their words do not map one-to-one, which is why a loss-free translation is impossible.",
        },
        {
          stem: "The author would most likely call treating language as a code for one fixed set of ideas:",
          choices: [
            "the safest approach for a translator",
            "a mistake that produces complacent translations",
            "necessary for scientific texts",
            "the only honest way to translate",
          ],
          answer: 1,
          explain: "The code assumption is exactly what the author ties to the most complacent, and worst, translations.",
        },
      ],
    },

    chem_phys: {
      title: 'Chem/Phys reasoning',
      passage: {
        label: 'Experiment',
        paragraphs: [
          "A biochemist prepares a buffer by dissolving equal molar amounts of acetic acid (pKa = 4.76) and its conjugate base, sodium acetate, in water. She measures the pH as 4.76.",
          "She then adds a small volume of concentrated HCl and stirs; the pH falls only slightly, to 4.70. Adding the same amount of HCl to pure water instead produces a far larger drop in pH.",
        ],
      },
      questions: [
        {
          stem: "The pH barely changes because the added H+ is consumed mainly by:",
          choices: [
            "acetic acid molecules",
            "acetate ions acting as a base",
            "water autoionization",
            "chloride ions",
          ],
          answer: 1,
          explain: "In a buffer, the conjugate base (acetate) neutralizes added strong acid, so the free H+ concentration barely rises.",
        },
        {
          stem: "The initial pH equals the pKa because, at equal concentrations of acid and conjugate base:",
          choices: [
            "the log term in the Henderson-Hasselbalch equation is zero",
            "the solution is effectively pure water",
            "the acid is now fully dissociated",
            "Kw becomes equal to 1",
          ],
          answer: 0,
          explain: "pH = pKa + log([A-]/[HA]); when [A-] = [HA], log(1) = 0, so pH = pKa.",
        },
        {
          stem: "To instead prepare a buffer at pH 5.76 from the same acid, the ratio [acetate]/[acetic acid] should be about:",
          choices: [
            "1 to 10",
            "1 to 1",
            "10 to 1",
            "100 to 1",
          ],
          answer: 2,
          explain: "5.76 = 4.76 + log(ratio) gives log(ratio) = 1, so the ratio is 10 to 1 (more conjugate base than acid).",
        },
        {
          stem: "Adding a small amount of strong base (OH-) to the original equimolar buffer would:",
          choices: [
            "raise the pH sharply, as it would in pure water",
            "change the pH only slightly, consumed by acetic acid",
            "have no measurable effect at all",
            "immediately destroy the buffer",
          ],
          answer: 1,
          explain: "The weak acid neutralizes added base, so pH shifts little: a buffer resists change in both directions.",
        },
        {
          stem: "A reaction has dH = +40 kJ/mol and dS = +120 J/(mol*K). It becomes spontaneous when:",
          choices: [
            "the temperature is high enough that T*dS exceeds dH",
            "the temperature is as low as possible",
            "never, because positive dH forbids spontaneity",
            "a catalyst is added",
          ],
          answer: 0,
          explain: "dG = dH - T*dS; with both positive, raising T makes T*dS outweigh dH, so dG turns negative (spontaneous).",
        },
        {
          stem: "Adding a catalyst speeds the reaction because it:",
          choices: [
            "shifts the equilibrium toward products",
            "lowers the activation energy for both directions",
            "raises the system's temperature",
            "increases the enthalpy change",
          ],
          answer: 1,
          explain: "A catalyst opens a lower-activation-energy path (forward and reverse equally); it speeds the rate without changing dG or the equilibrium position.",
        },
      ],
    },

    bio_biochem: {
      title: 'Bio/Biochem reasoning',
      passage: {
        label: 'Experiment',
        paragraphs: [
          "An enzyme's initial reaction rate is measured across a range of substrate concentrations, producing a hyperbolic curve with a defined Vmax and Km.",
          "Compound X is added and the run repeated: Vmax is unchanged, but the apparent Km increases. In a separate run, compound Y lowers Vmax while leaving Km unchanged.",
        ],
      },
      questions: [
        {
          stem: "Compound X is acting as a(n):",
          choices: [
            "competitive inhibitor",
            "noncompetitive inhibitor",
            "irreversible denaturant",
            "allosteric activator",
          ],
          answer: 0,
          explain: "Unchanged Vmax with increased Km is the signature of competitive inhibition, which competes with substrate at the active site.",
        },
        {
          stem: "The effect of compound X can be overcome by:",
          choices: [
            "lowering the temperature",
            "adding much more substrate",
            "removing all cofactors",
            "raising the pH sharply",
          ],
          answer: 1,
          explain: "Excess substrate outcompetes a competitive inhibitor, so the original Vmax is still reachable.",
        },
        {
          stem: "Compound Y (lower Vmax, unchanged Km) most likely binds:",
          choices: [
            "the active site only",
            "a site away from the active site, regardless of substrate",
            "the substrate molecule itself",
            "nowhere; it only changes the pH",
          ],
          answer: 1,
          explain: "Noncompetitive inhibitors bind an allosteric site and cut Vmax without changing substrate affinity (Km).",
        },
        {
          stem: "If the same reaction is run with far less enzyme but still-excess substrate, the measured Vmax will:",
          choices: [
            "decrease, because Vmax depends on enzyme amount",
            "increase without limit",
            "stay identical to the first run",
            "become equal to Km",
          ],
          answer: 0,
          explain: "Vmax = kcat * [enzyme], so less enzyme lowers Vmax; Km (substrate affinity) does not depend on enzyme amount.",
        },
        {
          stem: "A single-base DNA change leaves the encoded protein sequence unchanged. This is best explained by:",
          choices: [
            "the redundancy (degeneracy) of the genetic code",
            "a frameshift mutation",
            "an error in RNA splicing",
            "a nonsense mutation",
          ],
          answer: 0,
          explain: "Several codons code for the same amino acid, so a silent substitution leaves the protein intact.",
        },
        {
          stem: "Under anaerobic conditions, a muscle cell keeps glycolysis running mainly by:",
          choices: [
            "using the electron transport chain",
            "fermenting pyruvate to lactate to regenerate NAD+",
            "speeding up the Krebs cycle",
            "beta-oxidizing fatty acids",
          ],
          answer: 1,
          explain: "Without O2 the ETC stalls; lactate fermentation reoxidizes NADH to NAD+ so glycolysis (and its 2 ATP) can continue.",
        },
      ],
    },

    psych_soc: {
      title: 'Psych/Soc reasoning',
      passage: {
        label: 'Study',
        paragraphs: [
          "Researchers give three groups the same 40-item word list. Group A studies it in one massed hour. Group B studies for the same total time, but spread across four days. Group C reads the list once, then repeatedly tests itself.",
          "One week later, Group B recalls far more words than Group A, and Group C recalls more than Group A despite spending less total time reading.",
        ],
      },
      questions: [
        {
          stem: "Group B's advantage over Group A best illustrates the:",
          choices: [
            "spacing effect",
            "primacy effect",
            "fundamental attribution error",
            "bystander effect",
          ],
          answer: 0,
          explain: "Distributing study across days rather than massing it improves long-term retention: the spacing effect.",
        },
        {
          stem: "Group C doing better through repeated self-testing demonstrates the:",
          choices: [
            "testing effect (retrieval practice)",
            "mere-exposure effect",
            "framing effect",
            "availability heuristic",
          ],
          answer: 0,
          explain: "Actively retrieving information strengthens memory more than re-reading it: the testing, or retrieval-practice, effect.",
        },
        {
          stem: "Which change would most likely improve Group C even further?",
          choices: [
            "read the list two more times",
            "add correct-answer feedback after each self-test",
            "switch to studying it all at once",
            "shorten the delay before the final test",
          ],
          answer: 1,
          explain: "Feedback lets learners correct mistakes, adding to the gains from retrieval practice.",
        },
        {
          stem: "A fourth group recalls the first several words best of all. That edge for early items is the:",
          choices: [
            "primacy effect",
            "recency effect",
            "spacing effect",
            "framing effect",
          ],
          answer: 0,
          explain: "Stronger recall for early list items is the primacy effect: they received more rehearsal into long-term memory.",
        },
        {
          stem: "To be sure the spacing benefit is not just the passage of time, the design should add:",
          choices: [
            "a group that spaces study but is tested sooner",
            "a group matched on total study time that studies massed",
            "more words to the list",
            "a longer final delay for everyone",
          ],
          answer: 1,
          explain: "Holding total study time constant and varying only massed vs spaced isolates spacing as the cause.",
        },
        {
          stem: "One participant blames a low score on a noisy room but credits a high score to their intelligence. This is the:",
          choices: [
            "self-serving bias",
            "fundamental attribution error",
            "availability heuristic",
            "bystander effect",
          ],
          answer: 0,
          explain: "Attributing successes to oneself and failures to the situation is the self-serving bias.",
        },
      ],
    },
  };

  const KEYS = ['A', 'B', 'C', 'D'];
  const CONF = [['guess', 'Guessing'], ['unsure', 'Unsure'], ['sure', 'Sure']];
  const REASONS = [
    ['content', "Didn't know the content"],
    ['misread', 'Misread the question'],
    ['trap', 'Fell for a trap answer'],
    ['time', 'Rushed the reasoning'],
    ['math', 'Arithmetic slip'],
  ];
  const state = { section: 'cars', bank: BANKS.cars, i: 0, selected: null, confidence: 'unsure', checked: false, results: [], t0: 0 };
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const app = () => document.getElementById('app');

  // Optional adaptive ordering: when the dashboard has surfaced a per-section
  // ability estimate and the items themselves carry difficulty metadata, serve
  // the most informative item first (the one nearest the student's current
  // frontier). With no estimate, or items that carry no difficulty, we keep the
  // bank order, so the existing practice flow is untouched and no difficulty is
  // ever invented for an item that does not have one.
  function adaptiveOrder(questions, section) {
    const list = questions.slice();
    const v = (typeof window !== 'undefined' && window.__VANTAGE__) || null;
    const irt = v && v.readiness && v.readiness.irt && v.readiness.irt[section];
    const theta = irt && typeof irt.theta === 'number' ? irt.theta : null;
    if (theta === null || !list.some((q) => typeof q.b === 'number')) return list;
    const info = (q) => {
      const a = typeof q.a === 'number' ? q.a : 1;
      const p = 1 / (1 + Math.exp(-a * (theta - q.b)));
      return a * a * p * (1 - p);
    };
    return list
      .map((q, i) => ({ q, i, score: typeof q.b === 'number' ? info(q) : -1 }))
      .sort((x, y) => y.score - x.score || x.i - y.i)
      .map((e) => e.q);
  }

  function choiceHtml(text, idx) {
    return `<button class="choice" data-idx="${idx}" aria-pressed="false" onclick="vpractice.choose(${idx})">
      <span class="choice__key">${KEYS[idx]}</span><span>${esc(text)}</span></button>`;
  }

  function confHtml() {
    const chips = CONF.map(([v, label]) =>
      `<button class="conf ${state.confidence === v ? 'conf--on' : ''}" data-c="${v}" onclick="vpractice.setConf('${v}')">${label}</button>`,
    ).join('');
    return `<div class="confrow"><span class="confrow__label">How sure are you?</span><div class="confchips">${chips}</div></div>`;
  }

  function render() {
    const bank = state.bank;
    const q = bank.questions[state.i];
    const total = bank.questions.length;
    app().innerHTML = `<div class="wrap">
    <div class="top">
      <div class="top__title">${esc(bank.title)}</div>
      <div class="top__right">
        <span class="progress">Question ${state.i + 1} of ${total}</span>
        <button class="linkbtn" onclick="vpy('refresh')">Back to dashboard</button>
      </div>
    </div>
    <div class="pbar"><div class="pbar__fill" style="width:${Math.round((state.i / total) * 100)}%"></div></div>
    <div class="grid">
      <section class="passage">
        <div class="passage__label">${esc(bank.passage.label)}</div>
        <div class="passage__body">${bank.passage.paragraphs.map((p) => `<p>${esc(p)}</p>`).join('')}</div>
      </section>
      <section class="qcard">
        <div class="qcard__stem">${esc(q.stem)}</div>
        <div class="choices">${q.choices.map((c, idx) => choiceHtml(c, idx)).join('')}</div>
        ${confHtml()}
        <div class="feedback" id="fb" hidden></div>
        <div class="explain" id="ex" hidden></div>
        <div class="missrow" id="miss" hidden>
          <div class="missrow__q">Why did you miss it?</div>
          <div class="missbtns">${REASONS.map(([v, label]) => `<button class="missbtn" onclick="vpractice.miss('${v}')">${esc(label)}</button>`).join('')}</div>
        </div>
        <div class="actions"><button class="pbtn" id="act" disabled onclick="vpractice.check()">Check answer</button></div>
      </section>
    </div></div>`;
    state.t0 = Date.now();
  }

  function showSummary() {
    const bank = state.bank;
    const total = bank.questions.length;
    const correct = state.results.filter((r) => r.correct).length;
    app().innerHTML = `<div class="wrap">
    <div class="top"><div class="top__title">${esc(bank.title)}</div></div>
    <div class="summary">
      <div class="summary__score">${correct} of ${total} correct</div>
      <div class="summary__sub">Your scores update as you practice. The ones you missed come back for review later.</div>
      <div class="summary__actions">
        <button class="pbtn" onclick="vpractice.restart()">Practice again</button>
        <button class="pbtn pbtn--ghost" onclick="vpy('refresh')">Back to dashboard</button>
      </div>
    </div></div>`;
    // Report every item: confidence, correctness, miss reason, and the text of
    // misses (so the host records outcomes and makes spaced re-review cards).
    try {
      pycmd('vantage:practice2:' + encodeURIComponent(JSON.stringify({ section: state.section, items: state.results })));
    } catch (e) {
      console.log('practice2', state.results);
    }
  }

  function advance() {
    state.i += 1;
    state.selected = null;
    state.confidence = 'unsure';
    state.checked = false;
    if (state.i >= state.bank.questions.length) showSummary();
    else render();
  }

  window.vpractice = {
    open(section) {
      const key = section && BANKS[section] ? section : 'cars';
      state.section = key;
      // Clone the bank so the shared source stays pristine, and apply the
      // ability-frontier ordering (a no-op unless items carry difficulty).
      const src = BANKS[key];
      state.bank = { title: src.title, passage: src.passage, questions: adaptiveOrder(src.questions, key) };
      state.i = 0; state.selected = null; state.confidence = 'unsure'; state.checked = false; state.results = [];
      render();
    },
    setConf(v) {
      if (state.checked) return;
      state.confidence = v;
      document.querySelectorAll('.conf').forEach((el) => el.classList.toggle('conf--on', el.dataset.c === v));
    },
    choose(idx) {
      if (state.checked) return;
      state.selected = idx;
      document.querySelectorAll('.choice').forEach((el) => {
        el.setAttribute('aria-pressed', el.dataset.idx === String(idx) ? 'true' : 'false');
      });
      document.getElementById('act').disabled = false;
    },
    check() {
      if (state.checked || state.selected == null) return;
      const q = state.bank.questions[state.i];
      const total = state.bank.questions.length;
      state.checked = true;
      const correct = state.selected === q.answer;
      // Report the question text on every item (not just misses): the host anchors
      // each answered question to a real Anki card + revlog so the outcome syncs.
      const rec = {
        correct,
        confidence: state.confidence,
        ms: Date.now() - (state.t0 || Date.now()),
        stem: q.stem,
        answer: q.choices[q.answer],
        explain: q.explain,
      };
      state.results.push(rec);
      document.querySelectorAll('.choice').forEach((el, idx) => {
        el.disabled = true;
        el.setAttribute('aria-pressed', 'false');
        if (idx === q.answer) el.classList.add('choice--correct');
        else if (idx === state.selected) el.classList.add('choice--wrong');
      });
      document.querySelectorAll('.conf').forEach((el) => { el.disabled = true; });
      const fb = document.getElementById('fb');
      fb.textContent = correct ? 'Correct' : 'Not quite';
      fb.className = 'feedback ' + (correct ? 'feedback--ok' : 'feedback--no');
      fb.hidden = false;
      const ex = document.getElementById('ex');
      ex.textContent = q.explain;
      ex.hidden = false;
      const act = document.getElementById('act');
      if (correct) {
        act.textContent = state.i === total - 1 ? 'See results' : 'Next question';
        act.onclick = () => vpractice.next();
      } else {
        act.hidden = true;  // a miss reason (one tap) advances instead
        document.getElementById('miss').hidden = false;
      }
    },
    miss(reason) {
      const last = state.results[state.results.length - 1];
      if (last && !last.correct) last.reason = reason;
      advance();
    },
    next() { advance(); },
    restart() { this.open(state.section); },
  };

  window.vpy = window.vpy || function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };
})();
