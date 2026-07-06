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
    // Once the student picks a section (a Reasoning button or the dropdown) this
    // latches true, and the exam-countdown default suggestion stops touching
    // state.section -- a manual choice is never overridden.
    sectionManual: false,
    selected: null, confidence: 'unsure', checked: false, results: [], reported: 0, t0: 0,
    // Practice (default) vs Test mode. phase: 'setup' | 'running' | 'summary' | 'sldone'.
    mode: 'practice', phase: 'setup', test: null, testCount: 10, testMin: 15,
    // A second-look session re-serves previously-missed questions (feedback style),
    // and ends when its due list is done instead of reshuffling forever.
    secondLook: false,
    // Feature 3: time-capped untimed practice (from the "Study for N minutes"
    // chooser). 0 = no cap. Distinct from Test mode's own state.test countdown.
    practiceEndTs: 0, practiceTimerId: null,
    // Full-length exam: chains Test mode across sections. null unless one is running;
    // examScope/examPace hold the setup-card choices until the exam starts.
    exam: null, examScope: 'full', examPace: 'real',
  };
  const SECTION_LABELS = { cars: 'CARS', chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' };

  // ---- Full-length exam structure (real AAMC MCAT test day) --------------------
  // Per-section (questions, minutes) mirror anki.vantage.scoring.SECTION_TIMING
  // (pylib/anki/vantage/scoring.py; also vantage_core/scoring.py and, on the phone,
  // mobile_scoring.js), so the exam and the pacing coach use ONE set of numbers.
  // The fixed section order and the optional between-section break minutes are the
  // AAMC published test-day structure ("What's on the MCAT Exam?",
  // students-residents.aamc.org): Chem/Phys, a 10 minute break, CARS, a 30 minute
  // mid-exam break, Bio/Biochem, a 10 minute break, then Psych/Soc. These are the
  // exam flow's config (this file keeps JS behaviour config as module constants);
  // nothing here touches any score.
  const EXAM_SECTION_TIMING = { chem_phys: [59, 95], cars: [53, 90], bio_biochem: [59, 95], psych_soc: [59, 95] };
  const EXAM_FULL_ORDER = ['chem_phys', 'cars', 'bio_biochem', 'psych_soc'];
  const EXAM_SCIENCE_ORDER = ['chem_phys', 'bio_biochem', 'psych_soc'];
  // Minutes of the optional break that FOLLOWS each section on test day (the last
  // section has none). Keyed by the section it comes after, so both the full and the
  // science-only order pick up the right breaks without inventing any: after CARS is
  // the 30 minute mid-exam break, the others are 10 minutes.
  const EXAM_BREAK_AFTER_MIN = { chem_phys: 10, cars: 30, bio_biochem: 10 };
  // A shortened "quick run" so a student (or a test) can walk the whole flow in a few
  // minutes. Clearly labelled in the UI as shortened; it never claims to be real
  // timing, so the real per-section budgets above stay the source of truth.
  const EXAM_SHORT = { count: 3, min: 1, breakMin: 0.2 };

  // Pure: the ordered plan for one exam (each section plus the optional break after
  // it). Headless and deterministic, so the section chaining is unit-testable in Node
  // with no DOM. `includeCars` false runs the three science sections only.
  function examSectionBudget(section, shortened) {
    if (shortened) return [EXAM_SHORT.count, EXAM_SHORT.min];
    return EXAM_SECTION_TIMING[section] || [10, 15];
  }
  function buildExamPlan(opts) {
    opts = opts || {};
    const order = (opts.includeCars === false ? EXAM_SCIENCE_ORDER : EXAM_FULL_ORDER).slice();
    const shortened = !!opts.shortened;
    return order.map((section, i) => {
      const budget = examSectionBudget(section, shortened);
      const last = i === order.length - 1;
      const breakAfterMin = last ? 0 : (shortened ? EXAM_SHORT.breakMin : (EXAM_BREAK_AFTER_MIN[section] || 0));
      return { section, count: budget[0], minutes: budget[1], breakAfterMin };
    });
  }
  // Pure: given a plan and the index of the section that just ended, what comes next
  // -- a timed break before the next section, or the final summary. One source for
  // the chaining, used by the live flow and the tests.
  function examNextPhase(plan, idx) {
    if (idx + 1 >= plan.length) return { phase: 'summary' };
    return { phase: 'break', nextIdx: idx + 1, breakMin: plan[idx].breakAfterMin };
  }
  // Pure: the honest cross-section summary. Each section is its own raw tally (correct
  // of the ones you answered), NEVER blended into a single exam score, and a section
  // with nothing answered abstains instead of showing a fabricated number. Totals are
  // plain sums of those facts, not a modeled or scaled score.
  function aggregateExamSummary(sections) {
    const rows = (sections || []).map((s) => {
      const answered = s.answered || 0;
      const count = s.count || 0;
      if (answered <= 0) {
        return { section: s.section, abstained: true, notStarted: !!s.notStarted, answered: 0, count, correct: 0, pct: null };
      }
      return {
        section: s.section, abstained: false, notStarted: false, answered, count,
        correct: s.correct || 0, pct: Math.round(((s.correct || 0) / answered) * 100),
      };
    });
    const scored = rows.filter((r) => !r.abstained);
    const totalAnswered = scored.reduce((a, r) => a + r.answered, 0);
    const totalCorrect = scored.reduce((a, r) => a + r.correct, 0);
    return {
      rows,
      anyScored: scored.length > 0,
      totalAnswered,
      totalCorrect,
      totalPct: totalAnswered > 0 ? Math.round((totalCorrect / totalAnswered) * 100) : null,
    };
  }
  // Minutes -> "6 hours 15 minutes" for the honest structure line on the setup card.
  function fmtHrMin(mins) {
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    if (h && m) return `${h} hour${h > 1 ? 's' : ''} ${m} minutes`;
    if (h) return `${h} hour${h > 1 ? 's' : ''}`;
    return `${m} minutes`;
  }
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

  // ---- Second look: re-serve previously-missed questions after a delay ----
  // The host schedules each missed question on a real, FSRS-scheduled card and,
  // once due, hands back the list here (section + stable qid + the exact stem).
  // We re-serve the REAL question from the bank, so it is a genuine re-attempt,
  // not a stored flashcard copy.
  function secondLookData() {
    const d = dashData();
    return (d && d.second_look) || null;
  }
  // Find a bank question (with its passage) by exact stem within a section, so the
  // re-attempt shows the passage, choices, and all. Null when the question is no
  // longer in the bank (never fabricate one).
  function findByStem(section, stem) {
    const passages = sectionPassages(section);
    for (let i = 0; i < passages.length; i++) {
      const qs = passages[i].questions || [];
      for (let j = 0; j < qs.length; j++) {
        if (qs[j].stem === stem) return { passage: passages[i].passage, question: qs[j] };
      }
    }
    return null;
  }
  // The due second looks we can actually serve (their question still exists). Only
  // these drive the count and the Start button, so it is never a dead action.
  function servableDue() {
    const sl = secondLookData();
    const due = (sl && sl.due) || [];
    return due.filter((it) => it && it.stem && findByStem(it.section, it.stem));
  }
  // One round per due question: its passage plus just that question, cloned and
  // tagged with the stable qid + section so its result records back distinctly.
  function buildSecondLookRounds(due) {
    const rounds = [];
    for (let i = 0; i < due.length; i++) {
      const found = findByStem(due[i].section, due[i].stem);
      if (!found) continue;
      const q = Object.assign({}, found.question, { __qid: due[i].qid, __section: due[i].section });
      rounds.push({ passage: found.passage, questions: [q] });
    }
    return rounds;
  }
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  // In the tabbed dashboard, practice lives in its own pane; the standalone
  // preview page has no pane, so fall back to #app there.
  const pane = () => document.getElementById('pane-practice') || document.getElementById('app');

  // ---- Source-checked explanation for a missed question --------------------
  // The host injects window.__VANTAGE_EXPLANATIONS__ (built offline by
  // vantage_tools/ai/explanations.py): only explanations that PASSED the shared
  // card gate (SourceRef required, grounding check, quality gate), keyed by section
  // then exact stem, each with its text, source citation, and locator. On a miss we
  // show the verified explanation for THIS question if one exists, and otherwise
  // show nothing -- the same honest abstain the rest of the app uses, never an
  // ungrounded or unverified explanation. Pure lookup, exported for Node tests.
  function pickExplanation(map, section, stem) {
    if (!map || !section || !stem) return null;
    const bySection = map[section];
    if (!bySection) return null;
    const e = bySection[stem];
    if (!e || !e.text) return null;
    return e;
  }
  function gatedExplanation(section, stem) {
    const map = (typeof window !== 'undefined' && window.__VANTAGE_EXPLANATIONS__) || null;
    return pickExplanation(map, section, stem);
  }
  function srcExplainHtml(e) {
    const loc = e.locator ? ` <span class="srcex__loc">(${esc(e.locator)})</span>` : '';
    const src = e.source ? `<div class="srcex__src">Source: ${esc(e.source)}${loc}</div>` : '';
    return `<div class="srcex__eyebrow">Explanation, checked against a source</div>
      <div class="srcex__text">${esc(e.text)}</div>${src}`;
  }

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

  // ---- Flag a question / card for later (Feature 4) ----------------------------
  // The host injects d.flagged (native flag column). We seed a local Set of flagged
  // reasoning stems once, then toggle it optimistically as the student flags, and
  // tell the host to write the native Anki flag on the question's anchor card.
  function flaggedData() { const d = dashData(); return (d && d.flagged) || null; }
  function flaggedStems() {
    if (!window.__vFlagStems) {
      const set = new Set();
      const fd = flaggedData();
      ((fd && fd.reasoning) || []).forEach((r) => { if (r && r.stem) set.add(r.stem); });
      window.__vFlagStems = set;
    }
    return window.__vFlagStems;
  }
  function isFlagged(q) { return !!(q && q.stem && flaggedStems().has(q.stem)); }
  function flagBtnHtml(q) {
    const on = isFlagged(q);
    return `<button class="pflag${on ? ' pflag--on' : ''}" title="Flag to revisit"
      aria-pressed="${on ? 'true' : 'false'}" onclick="vpractice.flag()">${on ? '\u2605' : '\u2606'} Flag</button>`;
  }

  // The exam-countdown-aware DEFAULT reasoning split the backend computed
  // (study_pace.reasoning_focus). Null when there is no exam date or nothing to
  // split. This is only ever a SUGGESTION.
  function focusData() {
    const d = dashData();
    const sp = d && d.study_pace;
    const f = sp && sp.reasoning_focus;
    return (f && f.has_focus) ? f : null;
  }

  // Pre-select the rebalanced default section, but ONLY while the student has not
  // made a manual choice this session. Mirrors scoring.resolve_focus_section: a
  // manual choice always wins. Never forces a section that has no servable items.
  function applyDefaultSection() {
    if (state.sectionManual) return;
    const f = focusData();
    if (!f || !f.default_section) return;
    const k = f.default_section;
    if (hasInjected(k) || BANKS[k]) state.section = k;
  }

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
    stopPracticeTimer();  // Feature 3: never leave a stale practice ticker running
    // The setup card builds a timed test, so force test mode. This keeps start()
    // launching a timed session even when the last thing the student did was an
    // untimed Reasoning session, which leaves state.mode = 'practice'.
    state.mode = 'test';
    // Lead with the exam-countdown default section unless the student has chosen
    // one; runs before secOpts so the dropdown pre-selects the suggestion.
    applyDefaultSection();
    const secOpts = ['cars', 'chem_phys', 'bio_biochem', 'psych_soc']
      .map((k) => `<option value="${k}"${k === state.section ? ' selected' : ''}>${esc(SECTION_LABELS[k])}</option>`)
      .join('');
    const cfg = `<label class="psetup__row"><span>Questions</span><input class="psetup__num" type="number" min="1" max="59" value="${state.testCount}" onchange="vpractice.setCount(this.value)"></label>
         <label class="psetup__row"><span>Time (minutes)</span><input class="psetup__num" type="number" min="1" max="180" value="${state.testMin}" onchange="vpractice.setMin(this.value)"></label>
         <div class="psetup__presets">
           <button class="pchip" onclick="vpractice.preset(10,15)">10 questions, 15 min</button>
           <button class="pchip" onclick="vpractice.preset(20,30)">20 questions, 30 min</button>
         </div>`;
    // Two labeled zones on the Practice tab. Study is the shared studyBlock (the
    // interleaved review CTA plus the per-section cards, each carrying its
    // Flashcards / Reasoning launchers and color-coded flashcards/reasoning progress
    // bars), reused with its own handlers unchanged. The auto Mixed/Blocked choice
    // still happens server-side at launch (surfaced in the reviewer's deck title),
    // not on these cards. Test yourself groups the two
    // exam-conditions cards as siblings: the section-scoped Timed test and the
    // Full-length exam sit together in one grid (side by side on wide viewports,
    // stacked on narrow ones; see .ptests in practice.css). Grouping and styling
    // only, no behavior change to any control. The second-look queue stays above
    // both, its own labeled card when any re-checks are due.
    const d = dashData();
    const study = (d && typeof studyBlock === 'function') ? studyBlock(d) : '';
    const timedCard = `<div class="psetup__card">
        <div class="psetup__title">Timed test</div>
        <label class="psetup__row"><span>Section</span><select class="psetup__sec" onchange="vpractice.setSection(this.value)">${secOpts}</select></label>
        ${cfg}
        <button class="pbtn pbtn--start" onclick="vpractice.start()">Start test</button>
      </div>`;
    // Feature 4: the "Flagged for review" launcher sits right after studyBlock (which
    // carries F2/F5's CTAs and F3's chooser), completing the top-to-bottom study
    // area. It lives here, not in studyBlock, because it needs practice.js findByStem.
    pane().innerHTML = `${secondLookCard()}${study}${flaggedCard()}<section class="section">
      <div class="section__head"><div class="section__title section__title--group">Test yourself</div></div>
      <div class="ptests">${timedCard}${examCard()}</div>
    </section>`;
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
      state.practiceEndTs = 0;  // Test mode has its own timer; no practice cap
      const totalMs = Math.max(1, state.testMin) * 60000;
      state.test = { count: Math.max(1, state.testCount), totalMs, endTs: Date.now() + totalMs, answered: 0, correct: 0, timerId: null };
      startTimer();
    } else {
      state.test = null;
      startPracticeTimer();  // Feature 3: a session cap set by open() (0 = no cap)
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

  // ---- Practice session cap (Feature 3): a countdown for untimed practice opened
  // with a "Study for N minutes" choice. Display only; the stop is enforced in
  // advance() so the current question is always fully resolved first. ----
  function startPracticeTimer() {
    stopPracticeTimer();
    if (!state.practiceEndTs) return;
    state.practiceTimerId = setInterval(() => {
      const el = document.getElementById('pptimer');
      if (el) el.textContent = fmtTime(state.practiceEndTs - Date.now());
    }, 1000);
  }
  function stopPracticeTimer() {
    if (state.practiceTimerId) { clearInterval(state.practiceTimerId); state.practiceTimerId = null; }
  }

  // Draw the current phase. Called on every advance and when the Practice tab is
  // re-opened (so a running session survives tab switches).
  function render() {
    if (state.phase === 'setup') return renderSetup();
    if (state.phase === 'sldone') return renderSecondLookDone();
    if (state.phase === 'break') return renderExamBreak();
    if (state.phase === 'summary') return state.exam ? renderExamSummary() : renderSummary();
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
    // In a full-length exam the same timed engine runs; only the framing differs
    // (an exam badge, a "section X of N" marker, and End exam instead of End test).
    const ex = state.exam;
    const badge = ex ? 'Full-length exam' : 'Test';
    const sectionCounter = ex ? `<span class="progress progress--sec">Section ${ex.idx + 1} of ${ex.order.length}</span>` : '';
    const endHandler = ex ? 'vpractice.endExam()' : 'vpractice.endTest()';
    const endLabel = ex ? 'End exam' : 'End test';
    pane().innerHTML = `<div class="wrap">
    <div class="top">
      <div class="top__title">${esc(state.title)} <span class="ptestbadge">${badge}</span></div>
      <div class="top__right">
        <span class="ptimer" id="ptimer">${fmtTime(t.endTs - Date.now())}</span>
        ${sectionCounter}
        <span class="progress">${t.answered + 1} of ${t.count}</span>
        ${flagBtnHtml(q)}
        <button class="linkbtn" onclick="${endHandler}">${endLabel}</button>
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
    // In an exam, a finished section leads to the break (then the next section) or
    // the cross-section summary, not the single-test summary.
    if (state.exam) { examCaptureSection(false); return examAfterSection(); }
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

  // Recap for a reasoning practice block. Reasoning practice loops, so its natural
  // end is the student leaving; this shows a real summary from THIS session's
  // answers (state.results): count answered, accuracy, and best streak. It never
  // runs for the timed test or full-length exam (those keep their own completion
  // screens) or a second look (finishSecondLook handles that).
  function renderSessionRecap() {
    const rs = state.results || [];
    const total = rs.length;
    const right = rs.filter((r) => r.correct).length;
    const pct = total ? Math.round((right / total) * 100) : 0;
    let best = 0, run = 0;
    for (let i = 0; i < rs.length; i++) { run = rs[i].correct ? run + 1 : 0; if (run > best) best = run; }
    const saved = total - right; // each miss is saved for a second look
    // One honest, non-jargon touch: a streak worth celebrating, else what is saved
    // for another look. Never a raw concept id.
    let touch = '';
    if (best >= 3) touch = `<div class="psum__touch">Best streak: ${best} in a row</div>`;
    else if (saved > 0) touch = `<div class="psum__touch">${saved} saved for another look</div>`;
    pane().innerHTML = `<div class="wrap psum">
    <div class="top">
      <div class="top__title">Session recap</div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button></div>
    </div>
    <div class="psum__body">
      <div class="psum__score"><span class="psum__num">${right} of ${total}</span><span class="psum__pct">right this session, ${pct}%</span></div>
      ${touch}
      <div class="psum__note">Nice work. Your answers are saved and your dashboard scores update to match. Anything you missed comes back for a second look in a few days.</div>
      <div class="psum__actions"><button class="pbtn pbtn--start" onclick="vpractice.finish()">Done</button></div>
    </div></div>`;
    if (total >= 3 && pct >= 80) confettiBurst();
  }

  // A brief one-shot confetti burst (no library, self-cleaning, honors reduced
  // motion). Exposed as window.__vConfetti so the flashcard reviewer reuses it.
  function confettiBurst() {
    try { if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return; } catch (e) { /* no matchMedia */ }
    const host = document.createElement('div');
    host.className = 'confetti';
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#7c3aed'];
    for (let i = 0; i < 28; i++) {
      const bit = document.createElement('span');
      bit.className = 'confetti__bit';
      bit.style.left = (Math.random() * 100) + '%';
      bit.style.background = colors[i % colors.length];
      bit.style.animationDelay = (Math.random() * 0.25).toFixed(2) + 's';
      host.appendChild(bit);
    }
    (document.body || document.documentElement).appendChild(host);
    setTimeout(function () { host.remove(); }, 2600);
  }
  if (typeof window !== 'undefined') window.__vConfetti = confettiBurst;

  function renderPractice() {
    const p = curPassage();
    const q = curQuestion();
    pane().innerHTML = `<div class="wrap">
    <div class="top">
      <div class="top__title">${esc(state.title)}</div>
      <div class="top__right">
        ${state.practiceEndTs ? `<span class="ptimer" id="pptimer">${fmtTime(state.practiceEndTs - Date.now())}</span>` : ''}
        ${flagBtnHtml(q)}
        ${progressHtml()}
        <button class="linkbtn" onclick="vpractice.endPractice()">Back to dashboard</button>
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
        <div class="srcex" id="srcex" hidden></div>
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
    // Feature 3 time cap: the question just resolved was already recorded via
    // check() -> state.results (flushed on passage boundaries). If the clock is up,
    // end the session now with the normal practice summary instead of the next item.
    if (state.practiceEndTs && Date.now() >= state.practiceEndTs) {
      finishTimedPractice();
      return;
    }
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
      if (state.pi >= state.rounds.length) {
        // A second-look session ends when its due list is done, rather than
        // reshuffling into an endless loop like fresh practice.
        if (state.secondLook) { finishSecondLook(); return; }
        state.rounds = buildRounds(state.section); state.pi = 0;
      }
    }
    render();
  }

  // A second-look session: re-serve the due, previously-missed questions (feedback
  // style so the student sees the explanation again), ending when the list is done.
  function beginSecondLook() {
    const rounds = buildSecondLookRounds(servableDue());
    if (!rounds.length) { renderSetup(); return; }  // nothing servable right now
    state.section = rounds[0].questions[0].__section || state.section;
    state.title = 'Second look';
    state.rounds = rounds;
    state.pi = 0; state.qi = 0;
    state.selected = null; state.confidence = 'unsure'; state.checked = false;
    state.results = []; state.reported = 0;
    state.mode = 'second_look';  // renders like practice; tags the batch for the host
    state.secondLook = true;
    state.phase = 'running';
    state.test = null;
    render();
  }

  function finishSecondLook() {
    flush();
    state.secondLook = false;
    state.phase = 'sldone';
    renderSecondLookDone();
  }

  // Feature 3: end a time-capped practice session cleanly. The current question was
  // already resolved and recorded (advance() calls this right after it). Shows a real
  // tally, feeds Performance via flush(), and leaves the phase safe for a re-mount
  // (setup), so switching tabs and coming back never shows a stale/empty summary.
  function finishTimedPractice() {
    stopPracticeTimer();
    flush();
    state.practiceEndTs = 0;
    state.phase = 'setup';
    const total = state.results.length;
    const right = state.results.filter((r) => r.correct).length;
    pane().innerHTML = `<div class="wrap psum">
    <div class="top">
      <div class="top__title">Time's up</div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button></div>
    </div>
    <div class="psum__body">
      <div class="psum__score"><span class="psum__num">${right} of ${total}</span><span class="psum__pct">right this session</span></div>
      <div class="psum__note">These answers feed your Performance score. Open the Dashboard tab to see it update.</div>
      <div class="psum__actions">
        <button class="pbtn pbtn--start" onclick="vpractice.finish()">Done</button>
      </div>
    </div></div>`;
  }

  // Close-out for a second look: a raw tally (not a modeled score) of how many
  // stuck this time, and an honest note on what happens to the rest.
  function renderSecondLookDone() {
    const total = state.results.length;
    const right = state.results.filter((r) => r.correct).length;
    pane().innerHTML = `<div class="wrap psum">
    <div class="top">
      <div class="top__title">Second look done</div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button></div>
    </div>
    <div class="psum__body">
      <div class="psum__score"><span class="psum__num">${right} of ${total}</span><span class="psum__pct">right this time</span></div>
      <div class="psum__note">These are questions you missed before. The ones you got right are cleared. Any you missed again come back for another look in a few days.</div>
      <div class="psum__actions">
        <button class="pbtn pbtn--start" onclick="vpractice.finish()">Done</button>
      </div>
    </div></div>`;
  }

  // The second-look launcher, shown above fresh practice on the setup screen. Its
  // own labeled queue when questions are due; a quiet status otherwise. Hidden
  // entirely when there is nothing to show. All raw counts, never a modeled score.
  function secondLookCard() {
    const sl = secondLookData();
    if (!sl) return '';
    const ready = servableDue();
    const corrected = sl.corrected || 0;
    const failing = sl.still_failing || 0;
    const scheduled = sl.scheduled_count || 0;
    if (!ready.length && !scheduled && !corrected && !failing) return '';
    const chips = [];
    if (corrected) chips.push(`${corrected} fixed`);
    if (failing) chips.push(`${failing} still to fix`);
    if (scheduled) chips.push(`${scheduled} coming up`);
    const status = chips.length ? `<div class="slcard__status">${chips.join(' \u00b7 ')}</div>` : '';
    if (ready.length) {
      const q = ready.length === 1 ? 'question' : 'questions';
      return `<div class="slcard slcard--due">
        <div class="slcard__body">
          <div class="slcard__eyebrow">Second look</div>
          <div class="slcard__title">${ready.length} ${q} ready for another look</div>
          <div class="slcard__sub">You missed these before. Try them again to see if it stuck.</div>
          ${status}
        </div>
        <button class="pbtn pbtn--start slcard__btn" onclick="vpractice.openSecondLook()">Start second look</button>
      </div>`;
    }
    return `<div class="slcard">
      <div class="slcard__body">
        <div class="slcard__eyebrow">Second look</div>
        <div class="slcard__title">Nothing to re-check right now</div>
        <div class="slcard__sub">Questions you miss come back here in a few days to check the fix stuck.</div>
        ${status}
      </div></div>`;
  }

  // Feature 4: the "Flagged for review" launcher, mounted right after studyBlock on
  // the Practice tab. Its own labeled card when the student has flagged anything;
  // hidden entirely when empty (no dead entry point). Flashcards go to the flagged
  // reviewer pool; flagged reasoning questions are re-served here in practice.
  function flaggedCard() {
    const fd = flaggedData();
    if (!fd) return '';
    const cards = fd.card_count || 0;
    const qs = ((fd.reasoning) || []).filter((r) => r && r.stem && findByStem(r.section, r.stem));
    if (!cards && !qs.length) return '';
    const parts = [];
    if (cards) parts.push(`${cards} flashcard${cards === 1 ? '' : 's'}`);
    if (qs.length) parts.push(`${qs.length} question${qs.length === 1 ? '' : 's'}`);
    const cardBtn = cards ? '<button class="pbtn pbtn--start slcard__btn" onclick="vpy(\'study:flagged\')">Study flagged cards</button>' : '';
    const qBtn = qs.length ? '<button class="pbtn pbtn--start slcard__btn" onclick="vpractice.openFlagged()">Review flagged questions</button>' : '';
    return `<div class="slcard slcard--due">
      <div class="slcard__body">
        <div class="slcard__eyebrow">Flagged for review</div>
        <div class="slcard__title">${parts.join(' and ')} to revisit</div>
        <div class="slcard__sub">You flagged these while studying. Come back to them when you want.</div>
      </div>
      <div class="slcard__actions" style="display:flex;gap:0.6rem;flex-wrap:wrap">${cardBtn}${qBtn}</div>
    </div>`;
  }

  // ---- Full-length exam: chain Test mode across sections with timed breaks ------
  // Reuses the Test-mode engine wholesale (beginSession / renderTest / nextTest /
  // startTimer and the same flush pipeline). This block only decides the running
  // ORDER: which section starts next, the timed break between them, and the honest
  // cross-section close-out. No feedback ever appears until the very end, exactly as
  // in a single timed test.

  // Point the existing timed-test engine at one section of the exam.
  function beginExamSection(idx) {
    const ex = state.exam;
    if (!ex) return;
    ex.idx = idx;
    const section = ex.order[idx];
    const budget = examSectionBudget(section, ex.shortened);
    state.testCount = budget[0];
    state.testMin = budget[1];
    beginSession(section, true);  // real Test mode: timed, no feedback until the end
  }

  // Snapshot the section that just ended, BEFORE the engine is pointed at the next
  // one (which resets state.test and state.results).
  function examCaptureSection(notStarted) {
    const ex = state.exam;
    if (!ex) return;
    const t = state.test || {};
    const usedMs = Math.max(0, (t.totalMs || 0) - Math.max(0, (t.endTs || Date.now()) - Date.now()));
    const misses = state.results
      .filter((r) => !r.correct)
      .map((m) => ({ stem: m.stem, answer: m.answer, explain: m.explain }));
    ex.sections.push({
      section: state.section,
      count: t.count || 0,
      answered: t.answered || 0,
      correct: t.correct || 0,
      usedMs,
      misses,
      notStarted: !!notStarted,
    });
  }

  // A section ended (its questions ran out, or its clock hit zero): a timed break and
  // then the next section, or the final summary. examNextPhase is the one decision.
  function examAfterSection() {
    const ex = state.exam;
    const next = examNextPhase(ex.plan, ex.idx);
    if (next.phase === 'summary') return examToSummary();
    ex.pendingIdx = next.nextIdx;
    ex.breakMin = next.breakMin;
    const breakMs = Math.max(0, Math.round(next.breakMin * 60000));
    if (breakMs <= 0) { beginExamSection(ex.pendingIdx); return; }
    ex.breakEndTs = Date.now() + breakMs;
    state.phase = 'break';
    renderExamBreak();
    startBreakTimer();
  }

  function examToSummary() {
    stopTimer();
    stopBreakTimer();
    state.phase = 'summary';
    renderExamSummary();
  }

  // The break countdown between sections. Like the section timer, it ticks once a
  // second; when it reaches zero the next section starts on its own.
  function startBreakTimer() {
    stopBreakTimer();
    const ex = state.exam;
    if (!ex) return;
    ex.breakTimerId = setInterval(() => {
      if (!state.exam || state.phase !== 'break') return;
      const left = state.exam.breakEndTs - Date.now();
      const el = document.getElementById('pbreaktimer');
      if (el) el.textContent = fmtTime(left);
      if (left <= 0) startPendingSection();
    }, 1000);
  }
  function stopBreakTimer() {
    if (state.exam && state.exam.breakTimerId) { clearInterval(state.exam.breakTimerId); state.exam.breakTimerId = null; }
  }

  // Leave the break for the next section (the clock ran out, or the student chose to
  // start early). Breaks are optional on the real exam, so skipping is expected.
  function startPendingSection() {
    const ex = state.exam;
    if (!ex || ex.pendingIdx == null) return;
    stopBreakTimer();
    const idx = ex.pendingIdx;
    ex.pendingIdx = null;
    beginExamSection(idx);
  }

  // Honest one-line description of what the chosen exam will run, built from the plan
  // so it can never drift from the real per-section budgets.
  function examStructureLine(scope, pace) {
    const plan = buildExamPlan({ includeCars: scope !== 'science', shortened: pace === 'quick' });
    const labels = plan.map((s) => SECTION_LABELS[s.section] || s.section).join(', ');
    const q = plan.reduce((a, s) => a + s.count, 0);
    if (pace === 'quick') {
      return `Quick run: ${labels}. ${q} questions total with shortened timing and short breaks, so you can try the flow.`;
    }
    const mins = plan.reduce((a, s) => a + s.minutes, 0);
    const breaks = plan.reduce((a, s) => a + s.breakAfterMin, 0);
    return `${labels}. ${q} questions, about ${fmtHrMin(mins)} of testing plus ${breaks} minutes of optional breaks.`;
  }

  // The full-length exam setup card. Rendered as a bare card so it sits beside the
  // Timed test card in the "Test yourself" grid (renderSetup); same box styling.
  function examCard() {
    const scope = state.examScope || 'full';
    const pace = state.examPace || 'real';
    const chip = (on, val, handler, text) =>
      `<button class="pchip${on ? ' pchip--on' : ''}" onclick="vpractice.${handler}('${val}')">${text}</button>`;
    return `<div class="pexam__card">
      <div class="pexam__title">Full-length exam</div>
      <div class="pexam__struct">${esc(examStructureLine(scope, pace))}</div>
      <div class="pexam__opts">
        <div class="pexam__opt"><span class="pexam__optlabel">Sections</span><div class="pchips">
          ${chip(scope === 'full', 'full', 'setExamScope', 'Full exam with CARS')}
          ${chip(scope === 'science', 'science', 'setExamScope', 'Science only')}
        </div></div>
        <div class="pexam__opt"><span class="pexam__optlabel">Timing</span><div class="pchips">
          ${chip(pace === 'real', 'real', 'setExamPace', 'Real timing')}
          ${chip(pace === 'quick', 'quick', 'setExamPace', 'Quick run')}
        </div></div>
      </div>
      <button class="pbtn pbtn--start" onclick="vpractice.startExam()">Start full-length exam</button>
    </div>`;
  }

  // The timed break between two sections: a real countdown the student can also skip.
  function renderExamBreak() {
    const ex = state.exam;
    if (!ex || ex.pendingIdx == null) return renderSetup();
    const nextSection = ex.order[ex.pendingIdx];
    const nextLabel = SECTION_LABELS[nextSection] || nextSection;
    const left = ex.breakEndTs - Date.now();
    pane().innerHTML = `<div class="wrap pbreak">
    <div class="top">
      <div class="top__title">Break <span class="ptestbadge">Full-length exam</span></div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.endExam()">End exam</button></div>
    </div>
    <div class="pbreak__body">
      <div class="pbreak__timer" id="pbreaktimer">${fmtTime(left)}</div>
      <div class="pbreak__next">Next up: ${esc(nextLabel)}, section ${ex.pendingIdx + 1} of ${ex.order.length}</div>
      <div class="pbreak__note">Breaks are optional on the real exam. Take a breather. The next section starts on its own when the timer runs out, or you can start it now.</div>
      <div class="pbreak__actions"><button class="pbtn pbtn--start" onclick="vpractice.examSkipBreak()">Start next section now</button></div>
    </div></div>`;
  }

  // The honest cross-section close-out. Each section is its own raw tally (or an
  // honest abstain when nothing was answered); nothing is blended into one score, and
  // no readiness is shown here (that stays the dashboard's job, with its give-up rule).
  function renderExamSummary() {
    const ex = state.exam || { sections: [], order: [] };
    const agg = aggregateExamSummary(ex.sections);
    const rows = agg.rows.map((r) => {
      const label = SECTION_LABELS[r.section] || r.section;
      if (r.abstained) {
        const why = r.notStarted ? 'Not reached' : 'No answers recorded';
        return `<div class="pxrow pxrow--abstain">
          <div class="pxrow__sec">${esc(label)}</div>
          <div class="pxrow__tally">${why}</div>
          <div class="pxrow__sub">Too little to show a number honestly</div></div>`;
      }
      return `<div class="pxrow">
        <div class="pxrow__sec">${esc(label)}</div>
        <div class="pxrow__tally">${r.correct} of ${r.answered} <span class="pxrow__pct">${r.pct}%</span></div>
        <div class="pxrow__sub">answered ${r.answered} of ${r.count}</div></div>`;
    }).join('');
    const totalLine = agg.anyScored
      ? `<div class="psum__score"><span class="psum__num">${agg.totalCorrect} of ${agg.totalAnswered}</span><span class="psum__pct">${agg.totalPct}% correct across the sections you answered</span></div>`
      : `<div class="psum__score"><span class="psum__num">No answers</span><span class="psum__pct">You ended before answering anything</span></div>`;
    const allMisses = [];
    ex.sections.forEach((s) => (s.misses || []).forEach((m) => allMisses.push(m)));
    const missList = allMisses.length
      ? `<div class="psum__misses"><div class="psum__mh">Review your misses</div>${allMisses.map((m) => `<div class="psum__miss">
          <div class="psum__mstem">${esc(m.stem)}</div>
          <div class="psum__ma">Answer: ${esc(m.answer)}</div>
          ${m.explain ? `<div class="psum__mx">${esc(m.explain)}</div>` : ''}</div>`).join('')}</div>`
      : '';
    pane().innerHTML = `<div class="wrap psum">
    <div class="top">
      <div class="top__title">Full-length exam complete</div>
      <div class="top__right"><button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button></div>
    </div>
    <div class="psum__body">
      ${totalLine}
      <div class="pxrows">${rows}</div>
      <div class="psum__note">Each section above is a raw tally of what you answered, not a single exam score. Your memory, performance, and readiness update from these answers on the Dashboard tab, where a section with too little data stays in the not enough data yet state.</div>
      ${missList}
      <div class="psum__actions">
        <button class="pbtn pbtn--start" onclick="vpractice.newExam()">New exam</button>
        <button class="linkbtn" onclick="vpractice.finish()">Back to dashboard</button>
      </div>
    </div></div>`;
  }

  const vpractice = {
    // Open practice for a section directly (Reasoning buttons + "Start practice"
    // CTAs). Jumps to the Practice tab and skips the setup screen.
    open(section) {
      state.sectionManual = true;
      // Feature 3: honor the shared "Study for N minutes" choice for this session.
      const m = Math.max(0, parseInt(window.__vSessionMin, 10) || 0);
      state.practiceEndTs = m > 0 ? Date.now() + m * 60000 : 0;
      activate();
      beginSession(section, false);
    },
    // Re-serve the due second looks (previously-missed questions) as a distinct,
    // labeled session, separate from fresh practice.
    openSecondLook() { activate(); beginSecondLook(); },
    // Feature 4: re-serve the flagged reasoning questions as a distinct session.
    // Ends when the list is done (no reschedule); never time-capped.
    openFlagged() {
      activate();
      const fd = flaggedData();
      const rounds = [];
      ((fd && fd.reasoning) || []).forEach((r) => {
        const found = findByStem(r.section, r.stem);
        if (found) rounds.push({ passage: found.passage, questions: [Object.assign({}, found.question, { __section: r.section })] });
      });
      if (!rounds.length) { renderSetup(); return; }
      state.title = 'Flagged questions'; state.rounds = rounds; state.pi = 0; state.qi = 0;
      state.selected = null; state.confidence = 'unsure'; state.checked = false;
      state.results = []; state.reported = 0; state.mode = 'practice'; state.secondLook = false;
      state.phase = 'running'; state.test = null; state.practiceEndTs = 0;
      render();
    },
    // Feature 4: flag/unflag the current question. Optimistic UI, then tell the host
    // to write the native flag on its anchor card (created on demand if needed).
    flag() {
      const q = curQuestion();
      if (!q || !q.stem) return;
      const on = !isFlagged(q);
      if (on) flaggedStems().add(q.stem); else flaggedStems().delete(q.stem);
      const btn = document.querySelector('.pflag');
      if (btn) {
        btn.classList.toggle('pflag--on', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.textContent = (on ? '\u2605' : '\u2606') + ' Flag';
      }
      try {
        pycmd('vantage:flagq:' + encodeURIComponent(JSON.stringify({
          section: q.__section || state.section, stem: q.stem, answer: q.choices[q.answer],
          explain: q.explain, concept: q.concept || null, skill: q.skill || null, on,
        })));
      } catch (e) { console.log('flagq', q.stem, on); }
    },
    // Practice tab opened via the tab bar: keep a running session (a test, an exam
    // section, or a break) alive across tab switches, show the exam summary if one
    // just finished, else the setup screen.
    mount() {
      activate();
      if (state.phase === 'running' || state.phase === 'break') render();
      else if (state.phase === 'summary' && state.exam) renderExamSummary();
      else renderSetup();
    },
    setSection(k) { if (hasInjected(k) || BANKS[k]) { state.section = k; state.sectionManual = true; } },
    setCount(v) { const n = parseInt(v, 10); state.testCount = isNaN(n) ? 10 : Math.max(1, Math.min(59, n)); },
    setMin(v) { const n = parseInt(v, 10); state.testMin = isNaN(n) ? 15 : Math.max(1, Math.min(180, n)); },
    preset(c, m) { state.mode = 'test'; state.testCount = c; state.testMin = m; renderSetup(); },
    start() { beginSession(state.section, state.mode === 'test'); },
    newTest() { state.phase = 'setup'; renderSetup(); },
    endTest() { endTest(); },
    // ---- Full-length exam controls ----
    setExamScope(v) { state.examScope = v === 'science' ? 'science' : 'full'; renderSetup(); },
    setExamPace(v) { state.examPace = v === 'quick' ? 'quick' : 'real'; renderSetup(); },
    // Build the plan from the chosen scope/pace and start the first section. Every
    // section then runs through the same Test-mode engine, one after another.
    startExam() {
      activate();
      const includeCars = state.examScope !== 'science';
      const shortened = state.examPace === 'quick';
      const plan = buildExamPlan({ includeCars, shortened });
      state.exam = {
        plan, order: plan.map((s) => s.section), idx: 0, shortened,
        sections: [], pendingIdx: null, breakMin: 0, breakEndTs: 0, breakTimerId: null, aborted: false,
      };
      beginExamSection(0);
    },
    examSkipBreak() { startPendingSection(); },
    // End the whole exam early: keep what was answered, mark any sections not reached
    // as such, and go straight to the honest cross-section summary.
    endExam() {
      const ex = state.exam;
      if (!ex) return endTest();
      const inBreak = state.phase === 'break';
      stopTimer();
      stopBreakTimer();
      if (!inBreak) { flush(); examCaptureSection(false); }
      ex.aborted = true;
      let startFrom = inBreak ? ex.pendingIdx : ex.idx + 1;
      if (startFrom == null) startFrom = ex.order.length;
      for (let i = startFrom; i < ex.order.length; i++) {
        ex.sections.push({ section: ex.order[i], count: ex.plan[i].count, answered: 0, correct: 0, usedMs: 0, misses: [], notStarted: true });
      }
      examToSummary();
    },
    newExam() { state.exam = null; state.phase = 'setup'; renderSetup(); },
    // Test mode: record the answer silently (no feedback), then advance; end when
    // the question count is reached. Persist per passage so nothing is lost midway.
    nextTest() {
      if (state.selected == null || !state.test) return;
      const q = curQuestion();
      const correct = state.selected === q.answer;
      state.results.push({
        correct, confidence: null, ms: Date.now() - (state.t0 || Date.now()),
        stem: q.stem, answer: q.choices[q.answer], explain: q.explain,
        concept: q.concept || null, skill: q.skill || null,
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
        skill: q.skill || null,
      };
      // A re-served second look carries its stable qid + section so the host records
      // the RE-ATTEMPT distinctly from the original miss (and reschedules on a miss).
      if (q.__qid) { rec.second_look = true; rec.qid = q.__qid; rec.section = q.__section; }
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
      // On a miss, offer a source-checked explanation of the correct answer, but
      // only when a verified one exists for this exact question; otherwise show
      // nothing. A second look carries the section on the question (q.__section).
      const sx = document.getElementById('srcex');
      if (sx) {
        const e = correct ? null : gatedExplanation(q.__section || state.section, q.stem);
        if (e) {
          sx.innerHTML = srcExplainHtml(e);
          sx.hidden = false;
        } else {
          sx.hidden = true;
          sx.innerHTML = '';
        }
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
    // Leave an ACTIVE reasoning practice block: reasoning practice loops, so this
    // is its natural end. Show a real session recap first (only for fresh practice
    // with answers). The timed test / full-length exam keep their own screens and
    // never route here; a second look (mode 'second_look') just returns.
    endPractice() {
      stopTimer();
      stopPracticeTimer();  // Feature 3: clear any session cap ticker
      flush();
      if (state.mode === 'practice' && (state.results || []).length > 0) {
        state.phase = 'recap';
        renderSessionRecap();
      } else {
        vpy('refresh');
      }
    },
    finish() { stopTimer(); stopPracticeTimer(); flush(); vpy('refresh'); },
  };

  if (typeof window !== 'undefined') {
    window.vpractice = vpractice;
    window.vpy = window.vpy || function (cmd) { try { pycmd('vantage:' + cmd); } catch (e) { console.log('vpy', cmd); } };
  }
  // Test-only surface: the pure section-chaining and summary logic, exported so Node
  // unit tests can drive it headlessly (no DOM). The running app always uses
  // window.vpractice above; these exports are never referenced in the browser.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      vpractice,
      buildExamPlan, examNextPhase, aggregateExamSummary,
      pickExplanation,
      EXAM_SECTION_TIMING, EXAM_BREAK_AFTER_MIN, EXAM_FULL_ORDER, EXAM_SCIENCE_ORDER, EXAM_SHORT,
    };
  }
})();
