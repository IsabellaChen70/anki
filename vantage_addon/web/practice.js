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
          b: -0.8,
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
          b: -0.2,
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
          b: 0.8,
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
          b: -1.0,
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
          b: 1.2,
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
          b: 0.2,
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
          b: 0.0,
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
          b: -0.6,
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
          b: 0.4,
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
          b: 1.0,
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
          b: -0.2,
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
          b: 0.6,
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
          b: -1.2,
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
          b: -0.9,
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
          b: 0.3,
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
          b: -0.5,
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
          b: 1.3,
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
          b: 0.0,
          explain: "Attributing successes to oneself and failures to the situation is the self-serving bias.",
        },
      ],
    },
  };

  // Additional passages so practice can keep going past a single set. CARS ships
  // several here; a section with no extras simply reshuffles its one passage. Same
  // shape as a bank passage: { passage:{label,paragraphs}, questions:[{stem,choices,answer,explain}] }.
  const EXTRA_PASSAGES = {
    cars: [
      {
        passage: {
          label: 'Passage',
          paragraphs: [
            "When a forgery is exposed, the painting on the wall does not change; only our story about it does. Brushwork praised as luminous one day is called mechanical and cold the next. If the object is identical, our judgment was never really about the object at all, but about the name attached to it, about who we believed had stood before the canvas.",
            "Defenders of the outrage reply that provenance is part of the work: a painting is not merely a surface but a record of one person's choices at one moment, so to be deceived about the maker is to be deceived about what the work means. Yet this defense proves more than it intends. If meaning leans so heavily on the maker's identity, then our pleasure was always resting on a fact outside the frame, and the forger's real offense is to have shown us how little we trusted our own eyes.",
          ],
        },
        questions: [
          { stem: "The central claim of the passage is that exposing a forgery mainly reveals:", choices: ["that forged paintings are technically inferior", "that our judgments lean on the maker's identity more than on the work itself", "that provenance has no bearing on meaning", "that critics are usually incompetent"], answer: 1, explain: "The object is unchanged, so the reversal shows judgment tracked the attached name, not the surface." },
          { stem: "The praised brushwork later called \"mechanical and cold\" is offered to show that:", choices: ["forgers use cheap materials", "judgments flip even though the object is unchanged", "critics are unusually honest", "criticism is a science"], answer: 1, explain: "Identical object, reversed verdict: evidence the verdict followed the name, not the paint." },
          { stem: "The defenders' position is best stated as:", choices: ["a work's meaning includes the record of its actual maker's choices", "forgeries should hang beside originals", "aesthetic pleasure is purely about the surface", "provenance is irrelevant to meaning"], answer: 0, explain: "They hold provenance is part of the work, so deceiving about the maker deceives about meaning." },
          { stem: "The author replies that the defenders' view:", choices: ["settles the matter in their favor", "unintentionally concedes that pleasure depended on a fact outside the frame", "is irrelevant to forgery", "applies only to modern art"], answer: 1, explain: "\"Proves more than it intends\": if meaning leans on the maker, judgment leaned on an external fact all along." },
          { stem: "\"How little we trusted our own eyes\" most nearly suggests viewers:", choices: ["had poor eyesight", "deferred to authorship instead of judging the work directly", "secretly preferred forgeries", "never look at paintings closely"], answer: 1, explain: "The point is deference to the maker's name over independent aesthetic judgment." },
          { stem: "The author's attitude toward the outrage at forgeries is best described as:", choices: ["wholly sympathetic", "skeptical, treating it as self-undermining", "indifferent", "celebratory"], answer: 1, explain: "It \"should embarrass us,\" and the defense is turned against itself: a skeptical stance." },
        ],
      },
      {
        passage: {
          label: 'Passage',
          paragraphs: [
            "The dream of a history without a point of view is as old as history itself, and as unattainable. To narrate is to select; to select is to rank; and to rank is already to argue. The historian who claims to just present the facts has merely hidden the argument in the order of the sentences, in which events are named causes and which are left as background.",
            "This does not make history fiction. A novelist may invent a battle; a historian may not. Evidence can refute a claim, and a careless account can be shown to be wrong. But the constraint underdetermines the story: ten honest historians, given the same documents, will write ten different books, not because some are lying, but because significance is not printed on the surface of events. It is conferred by the questions the historian thought worth asking.",
          ],
        },
        questions: [
          { stem: "The passage primarily argues that history:", choices: ["involves interpretation yet stays constrained by evidence", "is indistinguishable from fiction", "should abandon the use of evidence", "can reach a view from nowhere with effort"], answer: 0, explain: "It denies pure objectivity (\"to narrate is to argue\") but insists evidence constrains (\"a historian may not\")." },
          { stem: "\"Hidden the argument in the order of the sentences\" implies claims of pure factuality:", choices: ["are usually correct", "conceal rather than remove interpretation", "merely need better grammar", "are impossible to write down"], answer: 1, explain: "The argument is hidden, not absent: framing events as cause vs background is itself interpretive." },
          { stem: "The contrast with the novelist mainly serves to:", choices: ["show history and fiction are the same", "mark the real constraint evidence places on history", "argue that novels are superior", "claim historians never make errors"], answer: 1, explain: "\"A novelist may invent a battle; a historian may not\" marks the evidential constraint." },
          { stem: "\"Significance is not printed on the surface of events\" most nearly means:", choices: ["events have no causes", "importance is assigned by the historian's questions, not read off directly", "documents are usually forged", "surfaces do not matter in art"], answer: 1, explain: "Significance is \"conferred by the questions the historian thought worth asking.\"" },
          { stem: "Ten honest historians writing ten different books is offered as evidence that:", choices: ["most historians are dishonest", "interpretation, not deceit, drives their divergence", "the documents are unreliable", "history is purely subjective"], answer: 1, explain: "\"Not because some are lying\": divergence comes from differing significant questions." },
          { stem: "The author would most likely describe objectivity in history as:", choices: ["fully achievable with enough discipline", "a limit that constrains without erasing perspective", "an illusion that frees historians to invent", "irrelevant to the discipline"], answer: 1, explain: "Evidence can refute yet underdetermines; perspective remains, a limit rather than an escape from viewpoint." },
        ],
      },
      {
        passage: {
          label: 'Passage',
          paragraphs: [
            "We have made boredom into an emergency. The empty minute, waiting in a line or riding an elevator, is now a wound to be dressed instantly with a glowing screen. We congratulate ourselves on never being bored, as if boredom were a disease we had finally cured. But something is lost when every gap is filled. Boredom, uncomfortable as it is, is the mind's signal that it is under-stimulated and free, and freedom is the condition in which it wanders somewhere new.",
            "Defenders of constant input will say their screens are not empty calories but nourishment: articles, lessons, conversations. Perhaps. Yet there is a difference between feeding the mind and merely occupying it, and the second is far easier to arrange. A mind never permitted to be idle is never permitted to be surprised by itself. The daydream, the half-formed connection, the idea that arrives only when we stop reaching for one, these require exactly the vacancy we now rush to abolish.",
          ],
        },
        questions: [
          { stem: "The main idea of the passage is that:", choices: ["boredom is a disease that technology has cured", "screens never provide anything of value", "filling every idle moment costs us the mental wandering boredom enables", "people should never use their phones"], answer: 2, explain: "The author prizes boredom as the vacancy in which the mind wanders somewhere new, lost when every gap is filled." },
          { stem: "\"A wound to be dressed instantly with a glowing screen\" chiefly conveys that people treat boredom as:", choices: ["a minor pleasure", "an injury demanding immediate relief", "a source of creativity", "an unavoidable illness"], answer: 1, explain: "The wound/dressing image casts the empty minute as something urgently to be fixed." },
          { stem: "The author concedes that screen content:", choices: ["is always worthless", "can genuinely nourish, at least sometimes", "is superior to daydreaming", "cures boredom permanently"], answer: 1, explain: "\"Perhaps.\" grants screens may be nourishment before drawing the feeding/occupying distinction." },
          { stem: "The distinction between feeding and \"merely occupying\" the mind is used to argue that:", choices: ["all screen use nourishes the mind", "occupation is easier to arrange and often substitutes for nourishment", "the mind cannot be fed", "boredom is always productive"], answer: 1, explain: "Nourishment is possible, but mere occupation is \"far easier to arrange,\" which is what usually happens." },
          { stem: "\"Never permitted to be surprised by itself\" most nearly means the mind is denied:", choices: ["external information", "the spontaneous, self-generated insight that idleness allows", "rest and sleep", "social connection"], answer: 1, explain: "The daydream and half-formed connection \"arrive only when we stop reaching\": self-surprise needs vacancy." },
          { stem: "The author's overall stance toward \"never being bored\" is:", choices: ["approving", "critical, viewing it as a hidden loss", "neutral", "celebratory"], answer: 1, explain: "The essay frames curing boredom as a loss of mental freedom, a critical stance." },
        ],
      },
    ],
  };

  // Authored bank injected by the host (render.py reads reasoning_bank.<section>.json).
  // When present it REPLACES the small built-in banks above; when absent we fall back
  // to them so practice still works. One source, identical on desktop and mobile.
  const INJECTED = (typeof window !== 'undefined' && window.__VANTAGE_REASONING_BANK__) || null;
  const hasInjected = (key) => !!(INJECTED && INJECTED[key] && Array.isArray(INJECTED[key].passages) && INJECTED[key].passages.length);

  const KEYS = ['A', 'B', 'C', 'D'];
  const CONF = [['guess', 'Guessing'], ['unsure', 'Unsure'], ['sure', 'Sure']];
  const REASONS = [
    ['content', "Didn't know the content"],
    ['misread', 'Misread the question'],
    ['trap', 'Fell for a trap answer'],
    ['time', 'Rushed the reasoning'],
    ['math', 'Arithmetic slip'],
  ];
  // Practice runs continuously: a section is a rotation of passages (each with its
  // questions), served one after another; when the rotation is exhausted we reshuffle
  // and keep going, so you can practice as far past the daily goal as you like.
  const state = {
    section: 'cars', title: BANKS.cars.title, rounds: [], pi: 0, qi: 0,
    selected: null, confidence: 'unsure', checked: false, results: [], reported: 0, t0: 0,
    // Practice (default) vs Test mode. phase: 'setup' | 'running' | 'summary'.
    mode: 'practice', phase: 'setup', test: null, testCount: 10, testMin: 15,
  };
  const SECTION_LABELS = { cars: 'CARS', chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' };
  const curPassage = () => state.rounds[state.pi];
  const curQuestion = () => state.rounds[state.pi].questions[state.qi];
  // Every item checked in THIS webview load -- survives moving between passages and
  // resets only when the dashboard reloads the page. Added to the day's persisted
  // count, it drives the "__ of __ today" reasoning goal.
  let answeredThisLoad = 0;

  const shuffle = (arr) => {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  };
  // Every passage available for a section: the bank's own passage plus any extras.
  function sectionPassages(key) {
    if (hasInjected(key)) {
      return INJECTED[key].passages.map((p) => ({
        passage: { label: p.label, paragraphs: p.paragraphs, source_ref: p.source_ref },
        questions: p.questions,
      }));
    }
    const src = BANKS[key] || BANKS.cars;
    return [{ passage: src.passage, questions: src.questions }].concat(EXTRA_PASSAGES[key] || []);
  }
  // One fresh cycle: passages in random order, questions within each ordered by the
  // ability frontier (a no-op unless items carry difficulty). Cloned so the shared
  // source stays pristine.
  function buildRounds(key) {
    return shuffle(sectionPassages(key)).map((r) => ({ passage: r.passage, questions: adaptiveOrder(r.questions, key) }));
  }
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  // In the tabbed dashboard, practice lives in its own pane; the standalone
  // preview page has no pane, so fall back to #app there.
  const pane = () => document.getElementById('pane-practice') || document.getElementById('app');

  // Dashboard data for the shared study launcher. studyBlock lives in dashboard.js,
  // which is loaded before this file in the tabbed page, so it (and MOCK) are in
  // scope here. Live collection data when present, else the offline-preview MOCK;
  // null on a live page with no data yet, or on the standalone practice preview
  // where dashboard.js is not loaded at all (the studyBlock guard handles that).
  function dashData() {
    if (typeof window === 'undefined') return null;
    if (window.__VANTAGE__) return window.__VANTAGE__;
    if (window.__VANTAGE_LIVE__) return null;
    return (typeof MOCK !== 'undefined') ? MOCK : null;
  }
  const fmtTime = (ms) => {
    const s = Math.max(0, Math.round(ms / 1000));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + ':' + (r < 10 ? '0' : '') + r;
  };

  // Make the Practice tab the active one (used when a Reasoning button on another
  // tab opens practice). Mirrors dashboard.js vtab's DOM work.
  function activate() {
    if (typeof document === 'undefined') return;
    window.__vtab = 'practice';
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('tab--on', t.dataset.tab === 'practice'));
    document.querySelectorAll('.tabpane').forEach((p) => {
      const on = p.id === 'pane-practice';
      p.hidden = !on;
      p.classList.toggle('tabpane--on', on);
    });
  }

  // ---- Setup screen: timed-test setup (section, question count, and timer) ----
  function renderSetup() {
    state.phase = 'setup';
    stopTimer();
    // The setup card builds a timed test, so force test mode. This keeps start()
    // launching a timed session even when the last thing the student did was an
    // untimed Reasoning session, which leaves state.mode = 'practice'.
    state.mode = 'test';
    const secOpts = ['cars', 'chem_phys', 'bio_biochem', 'psych_soc']
      .map((k) => `<option value="${k}"${k === state.section ? ' selected' : ''}>${esc(SECTION_LABELS[k])}</option>`)
      .join('');
    const cfg = `<label class="psetup__row"><span>Questions</span><input class="psetup__num" type="number" min="1" max="59" value="${state.testCount}" onchange="vpractice.setCount(this.value)"></label>
         <label class="psetup__row"><span>Time (minutes)</span><input class="psetup__num" type="number" min="1" max="180" value="${state.testMin}" onchange="vpractice.setMin(this.value)"></label>
         <div class="psetup__presets">
           <button class="pchip" onclick="vpractice.preset(10,15)">10 questions, 15 min</button>
           <button class="pchip" onclick="vpractice.preset(20,30)">20 questions, 30 min</button>
         </div>`;
    // Study launcher lives here on Practice (interleaved CTA at the top, then
    // Flashcards + Reasoning together per section). Reuses the dashboard's shared
    // studyBlock renderer and its existing handlers, unchanged; the card below it
    // builds a timed reasoning test.
    const d = dashData();
    const study = (d && typeof studyBlock === 'function') ? studyBlock(d) : '';
    // .psplit lays the two panels out: Study & practice (primary, wider) beside the
    // Timed test setup (secondary, narrower) on wide viewports, and stacked on narrow
    // ones (see practice.css). Layout only, no behavior change to either block.
    pane().innerHTML = `<div class="psplit">${study}<div class="wrap psetup">
      <div class="psplit__spacer" aria-hidden="true"><div class="section__title section__title--group">&nbsp;</div></div>
      <div class="psetup__card">
        <div class="psetup__title">Timed test</div>
        <label class="psetup__row"><span>Section</span><select class="psetup__sec" onchange="vpractice.setSection(this.value)">${secOpts}</select></label>
        ${cfg}
        <button class="pbtn pbtn--start" onclick="vpractice.start()">Start test</button>
      </div></div></div>`;
  }

  function beginSession(section, isTest) {
    const key = section && (hasInjected(section) || BANKS[section]) ? section : 'cars';
    state.section = key;
    const inj = INJECTED && INJECTED[key];
    state.title = (inj && inj.title) || (BANKS[key] || BANKS.cars).title;
    state.rounds = buildRounds(key);
    state.pi = 0; state.qi = 0;
    state.selected = null; state.confidence = 'unsure'; state.checked = false;
    state.results = []; state.reported = 0;
    state.mode = isTest ? 'test' : 'practice';
    state.phase = 'running';
    if (isTest) {
      const totalMs = Math.max(1, state.testMin) * 60000;
      state.test = { count: Math.max(1, state.testCount), totalMs, endTs: Date.now() + totalMs, answered: 0, correct: 0, timerId: null };
      startTimer();
    } else {
      state.test = null;
    }
    render();
  }

  // ---- Test countdown ----
  function startTimer() {
    stopTimer();
    if (!state.test) return;
    state.test.timerId = setInterval(() => {
      if (!state.test) return;
      const left = state.test.endTs - Date.now();
      const el = document.getElementById('ptimer');
      if (el) el.textContent = fmtTime(left);
      if (left <= 0) endTest();
    }, 1000);
  }
  function stopTimer() {
    if (state.test && state.test.timerId) { clearInterval(state.test.timerId); state.test.timerId = null; }
  }

  // Draw the current phase. Called on every advance and when the Practice tab is
  // re-opened (so a running session survives tab switches).
  function render() {
    if (state.phase === 'setup') return renderSetup();
    if (state.phase === 'summary') return renderSummary();
    if (state.mode === 'test') return renderTest();
    return renderPractice();
  }

  // Test mode: exam conditions -- a countdown, a progress count, and no feedback
  // until the summary. Selecting an answer just enables Next.
  function renderTest() {
    const p = curPassage();
    const q = curQuestion();
    const t = state.test;
    const last = t.answered + 1 >= t.count;
    pane().innerHTML = `<div class="wrap">
    <div class="top">
      <div class="top__title">${esc(state.title)} <span class="ptestbadge">Test</span></div>
      <div class="top__right">
        <span class="ptimer" id="ptimer">${fmtTime(t.endTs - Date.now())}</span>
        <span class="progress">${t.answered + 1} of ${t.count}</span>
        <button class="linkbtn" onclick="vpractice.endTest()">End test</button>
      </div>
    </div>
    <div class="grid">
      <section class="passage">
        <div class="passage__label">${esc(p.passage.label)}</div>
        <div class="passage__body">${p.passage.paragraphs.map((x) => `<p>${esc(x)}</p>`).join('')}</div>
        ${p.passage.source_ref ? `<div class="passage__src">Source: ${esc(p.passage.source_ref)}</div>` : ''}
      </section>
      <section class="qcard">
        <div class="qcard__stem">${esc(q.stem)}</div>
        <div class="choices">${q.choices.map((c, idx) => choiceHtml(c, idx)).join('')}</div>
        <div class="actions"><button class="pbtn" id="act" disabled onclick="vpractice.nextTest()">${last ? 'Finish test' : 'Next'}</button></div>
      </section>
    </div></div>`;
    state.t0 = Date.now();
  }

  function endTest() {
    stopTimer();
    flush();
    state.phase = 'summary';
    renderSummary();
  }

  // End-of-test summary: raw tally (a count of THIS test, not a modeled score),
  // time used, and the missed questions with their answers. The dashboard's
  // Performance/Readiness scores update from these answers and keep their own
  // give-up rules, so we never present a modeled score here.
  function renderSummary() {
    const t = state.test || { count: 0, answered: 0, correct: 0, totalMs: 0, endTs: Date.now() };
    const answered = t.answered;
    const correct = t.correct;
    const usedMs = Math.max(0, t.totalMs - Math.max(0, t.endTs - Date.now()));
    const pctv = answered > 0 ? Math.round((correct / answered) * 100) : 0;
    const misses = state.results.filter((r) => !r.correct);
    const scoreLine = answered > 0
      ? `<div class="psum__score"><span class="psum__num">${correct} of ${answered}</span><span class="psum__pct">${pctv}% correct</span></div>`
      : `<div class="psum__score"><span class="psum__num">No answers</span><span class="psum__pct">You ended before answering anything</span></div>`;
    const missList = misses.length
      ? `<div class="psum__misses"><div class="psum__mh">Review your misses</div>${misses.map((m) => `<div class="psum__miss">
          <div class="psum__mstem">${esc(m.stem)}</div>
          <div class="psum__ma">Answer: ${esc(m.answer)}</div>
          ${m.explain ? `<div class="psum__mx">${esc(m.explain)}</div>` : ''}</div>`).join('')}</div>`
      : (answered > 0 ? '<div class="psum__allright">You did not miss any. Nice work.</div>' : '');
    pane().innerHTML = `<div class="wrap psum">
    <div class="top">
      <div class="top__title">Test complete</div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button></div>
    </div>
    <div class="psum__body">
      ${scoreLine}
      <div class="psum__meta"><span>${answered} of ${t.count} answered</span><span>Time used ${fmtTime(usedMs)}</span></div>
      <div class="psum__note">These answers feed your Performance score. Open the Dashboard tab to see it update.</div>
      ${missList}
      <div class="psum__actions">
        <button class="pbtn pbtn--start" onclick="vpractice.newTest()">New test</button>
        <button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button>
      </div>
    </div></div>`;
  }

  // "__ of __ today": progress toward the day's reasoning goal. X = answered so far
  // today (the count persisted at the last dashboard load, plus everything answered
  // this load); Y = today's target from the study plan. Going over Y is intentional
  // -- the tally keeps rising, and returning to the dashboard recomputes so the
  // trajectory and scores reflect the extra practice. With no exam date (so no daily
  // goal yet) we fall back to a plain tally.
  function progressHtml() {
    const v = (typeof window !== 'undefined' && window.__VANTAGE__) || null;
    const sp = v && v.study_pace;
    const goal = sp && sp.has_exam_date ? (sp.reasoning_per_day || 0) : 0;
    if (!goal) return `<span class="progress">${answeredThisLoad} answered</span>`;
    const done = (sp.reasoning_today || 0) + answeredThisLoad;
    const met = done >= goal;
    return `<span class="progress${met ? ' progress--met' : ''}">${done} of ${goal} today</span>`;
  }

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

  function renderPractice() {
    const p = curPassage();
    const q = curQuestion();
    pane().innerHTML = `<div class="wrap">
    <div class="top">
      <div class="top__title">${esc(state.title)}</div>
      <div class="top__right">
        ${progressHtml()}
        <button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button>
      </div>
    </div>
    <div class="grid">
      <section class="passage">
        <div class="passage__label">${esc(p.passage.label)}</div>
        <div class="passage__body">${p.passage.paragraphs.map((x) => `<p>${esc(x)}</p>`).join('')}</div>
        ${p.passage.source_ref ? `<div class="passage__src">Source: ${esc(p.passage.source_ref)}</div>` : ''}
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

  // Persist everything answered but not yet reported. The host anchors each item to a
  // real card + revlog (so it syncs and feeds today's count) and turns misses into
  // spaced re-review cards. Called when a passage completes and when leaving practice,
  // so nothing is lost even though there is no end-of-set summary anymore.
  function flush() {
    const items = state.results.slice(state.reported);
    if (!items.length) return;
    state.reported = state.results.length;
    try {
      // Same performance pipeline as practice; `mode` tags test answers so they
      // are distinguishable in reporting without forking a separate scoring path.
      pycmd('vantage:practice2:' + encodeURIComponent(JSON.stringify({ section: state.section, mode: state.mode, items })));
    } catch (e) {
      console.log('practice2', items);
    }
  }

  function advance() {
    state.selected = null;
    state.confidence = 'unsure';
    state.checked = false;
    state.qi += 1;
    if (state.qi >= curPassage().questions.length) {
      // Passage finished: persist it, then move on. Never dead-end -- once the last
      // passage is done we reshuffle and keep going so practice continues past the goal.
      flush();
      state.qi = 0;
      state.pi += 1;
      if (state.pi >= state.rounds.length) { state.rounds = buildRounds(state.section); state.pi = 0; }
    }
    render();
  }

  window.vpractice = {
    // Open practice for a section directly (Reasoning buttons + "Start practice"
    // CTAs). Jumps to the Practice tab and skips the setup screen.
    open(section) { activate(); beginSession(section, false); },
    // Practice tab opened via the tab bar: keep a running session, else show setup.
    mount() { activate(); if (state.phase === 'running') render(); else renderSetup(); },
    setSection(k) { if (hasInjected(k) || BANKS[k]) state.section = k; },
    setCount(v) { const n = parseInt(v, 10); state.testCount = isNaN(n) ? 10 : Math.max(1, Math.min(59, n)); },
    setMin(v) { const n = parseInt(v, 10); state.testMin = isNaN(n) ? 15 : Math.max(1, Math.min(180, n)); },
    preset(c, m) { state.mode = 'test'; state.testCount = c; state.testMin = m; renderSetup(); },
    start() { beginSession(state.section, state.mode === 'test'); },
    newTest() { state.phase = 'setup'; renderSetup(); },
    endTest() { endTest(); },
    // Test mode: record the answer silently (no feedback), then advance; end when
    // the question count is reached. Persist per passage so nothing is lost midway.
    nextTest() {
      if (state.selected == null || !state.test) return;
      const q = curQuestion();
      const correct = state.selected === q.answer;
      state.results.push({
        correct, confidence: null, ms: Date.now() - (state.t0 || Date.now()),
        stem: q.stem, answer: q.choices[q.answer], explain: q.explain, concept: q.concept || null,
      });
      answeredThisLoad += 1;
      state.test.answered += 1;
      if (correct) state.test.correct += 1;
      if (state.test.answered >= state.test.count) { endTest(); return; }
      state.selected = null;
      state.qi += 1;
      if (state.qi >= curPassage().questions.length) {
        flush();
        state.qi = 0; state.pi += 1;
        if (state.pi >= state.rounds.length) { state.rounds = buildRounds(state.section); state.pi = 0; }
      }
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
      const q = curQuestion();
      const lastInPassage = state.qi === curPassage().questions.length - 1;
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
        concept: q.concept || null,
      };
      state.results.push(rec);
      answeredThisLoad += 1;  // feeds the "__ of __ today" reasoning goal
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
        act.textContent = lastInPassage ? (state.rounds.length > 1 ? 'Next passage' : 'Keep going') : 'Next question';
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
    // Leave practice: persist anything not yet reported, then return to the dashboard
    // (which recomputes so the extra practice shows in the scores and today's count).
    finish() { stopTimer(); flush(); vpy('refresh'); },
  };

  window.vpy = window.vpy || function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };
})();
