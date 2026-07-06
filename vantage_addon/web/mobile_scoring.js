/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Vantage on-device scoring (mobile). A faithful port of the pure Python core
   (anki.vantage scoring + outline + collect) so the phone computes the same
   honest scores from its OWN collection instead of showing a baked snapshot.

   The Kotlin Activity extracts raw (tags, retrievability) per card plus the
   graded-review count from the phone's collection and calls
   window.vantageComputeFromRaw(raw); the result feeds the same renderer the
   desktop uses. Memory is real; performance and readiness abstain until there
   are exam-style practice items, exactly as on desktop. */
(function () {
  const OUTLINE = {
    version: 'aamc-approx-2023.v1',
    sections: { chem_phys: 'Chem/Phys', bio_biochem: 'Bio/Biochem', psych_soc: 'Psych/Soc' },
    concepts: [
      { id: '4A', section: 'chem_phys', weight: 3, name: 'Translational motion, forces, work, energy, equilibrium', aliases: ['kinematics', 'forces', 'work_energy', 'equilibrium', 'mechanics'] },
      { id: '4B', section: 'chem_phys', weight: 2, name: 'Importance of fluids for circulation of blood, gas movement', aliases: ['fluids', 'hydrostatics', 'gases', 'circulation'] },
      { id: '4C', section: 'chem_phys', weight: 2, name: 'Electrochemistry and electrical circuits', aliases: ['electrochemistry', 'circuits', 'electrostatics'] },
      { id: '4D', section: 'chem_phys', weight: 1, name: 'How light and sound interact with matter', aliases: ['optics', 'light', 'sound', 'waves'] },
      { id: '4E', section: 'chem_phys', weight: 3, name: 'Atoms, nuclear decay, electronic structure', aliases: ['atomic_structure', 'periodic_table', 'nuclear', 'quantum'] },
      { id: '5A', section: 'chem_phys', weight: 2, name: 'Unique nature of water and its solutions', aliases: ['water', 'solutions', 'acid_base', 'ph', 'buffers'] },
      { id: '5B', section: 'chem_phys', weight: 3, name: 'Nature of molecules and intermolecular interactions', aliases: ['bonding', 'intermolecular', 'molecular_structure'] },
      { id: '5C', section: 'chem_phys', weight: 2, name: 'Separation and purification methods', aliases: ['chromatography', 'distillation', 'separation', 'spectroscopy'] },
      { id: '5D', section: 'chem_phys', weight: 4, name: 'Structure, function, and reactivity of biological molecules', aliases: ['organic_chemistry', 'functional_groups', 'reactions', 'stereochemistry'] },
      { id: '5E', section: 'chem_phys', weight: 3, name: 'Principles of chemical thermodynamics and kinetics', aliases: ['thermodynamics', 'kinetics', 'enthalpy', 'entropy', 'gibbs'] },
      { id: '1A', section: 'bio_biochem', weight: 5, name: 'Structure and function of proteins and amino acids', aliases: ['amino_acids', 'proteins', 'enzymes', 'protein_structure'] },
      { id: '1B', section: 'bio_biochem', weight: 3, name: 'Transmission of genetic information from gene to protein', aliases: ['transcription', 'translation', 'central_dogma', 'gene_expression'] },
      { id: '1C', section: 'bio_biochem', weight: 2, name: 'Transmission of heritable information and its variation', aliases: ['genetics', 'inheritance', 'evolution', 'meiosis'] },
      { id: '1D', section: 'bio_biochem', weight: 4, name: 'Principles of bioenergetics and fuel molecule metabolism', aliases: ['metabolism', 'bioenergetics', 'glycolysis', 'krebs', 'oxidative_phosphorylation'] },
      { id: '2A', section: 'bio_biochem', weight: 4, name: 'Assemblies of molecules, cells, and groups of cells', aliases: ['cell_biology', 'membranes', 'organelles', 'cell_theory'] },
      { id: '2B', section: 'bio_biochem', weight: 2, name: 'Structure, growth, physiology, genetics of prokaryotes and viruses', aliases: ['prokaryotes', 'bacteria', 'viruses', 'microbiology'] },
      { id: '2C', section: 'bio_biochem', weight: 3, name: 'Processes of cell division, differentiation, and specialization', aliases: ['cell_cycle', 'mitosis', 'differentiation', 'stem_cells'] },
      { id: '3A', section: 'bio_biochem', weight: 4, name: 'Structure and function of the nervous and endocrine systems', aliases: ['nervous_system', 'endocrine', 'neurons', 'hormones'] },
      { id: '3B', section: 'bio_biochem', weight: 4, name: 'Structure and function of the main organ systems', aliases: ['physiology', 'organ_systems', 'circulatory', 'respiratory', 'renal', 'immune'] },
      { id: '6A', section: 'psych_soc', weight: 2, name: 'Sensing the environment', aliases: ['sensation', 'perception', 'senses', 'vision', 'hearing'] },
      { id: '6B', section: 'psych_soc', weight: 3, name: 'Making sense of the environment', aliases: ['cognition', 'memory', 'attention', 'consciousness', 'intelligence'] },
      { id: '6C', section: 'psych_soc', weight: 2, name: 'Responding to the world', aliases: ['emotion', 'stress', 'motivation'] },
      { id: '7A', section: 'psych_soc', weight: 3, name: 'Individual influences on behavior', aliases: ['learning', 'conditioning', 'personality', 'biological_bases'] },
      { id: '7B', section: 'psych_soc', weight: 3, name: 'Social processes that influence human behavior', aliases: ['social_influence', 'conformity', 'groups', 'socialization'] },
      { id: '7C', section: 'psych_soc', weight: 2, name: 'Attitude and behavior change', aliases: ['attitudes', 'persuasion', 'behavior_change'] },
      { id: '8A', section: 'psych_soc', weight: 2, name: 'Self-identity', aliases: ['self_concept', 'identity', 'self_esteem'] },
      { id: '8B', section: 'psych_soc', weight: 3, name: 'Social thinking', aliases: ['attribution', 'prejudice', 'stereotypes', 'social_cognition'] },
      { id: '8C', section: 'psych_soc', weight: 3, name: 'Social interactions', aliases: ['social_interaction', 'attraction', 'aggression', 'altruism'] },
      { id: '9A', section: 'psych_soc', weight: 3, name: 'Understanding social structure', aliases: ['social_structure', 'institutions', 'culture', 'social_theory'] },
      { id: '9B', section: 'psych_soc', weight: 2, name: 'Demographic characteristics and processes', aliases: ['demographics', 'population', 'migration'] },
      { id: '10A', section: 'psych_soc', weight: 3, name: 'Social inequality', aliases: ['inequality', 'stratification', 'poverty', 'healthcare_disparities'] },
    ],
  };
  const CFG = {
    min_cards_memory: 20, min_outcomes_performance: 20,
    giveup_min_reviews: 200, giveup_min_coverage: 0.5,
    memory_high_max_width: 0.06, memory_high_min_n: 100,
    perf_high_max_width: 0.1, perf_high_min_n: 60,
    ready_high_max_width: 4, ready_high_min_coverage: 0.65,
    min_outcomes_readiness: 5, projection_prior_strength: 8,
    map_low_ability: 0.4, map_low_scale: 118, map_high_ability: 0.9, map_high_scale: 132,
    section_scale_min: 118, section_scale_max: 132,
    min_outcomes_calibration: 15, calibration_well_within: 0.1,
    pace_reasoning_target: 60, pace_reasoning_per_concept: 10, pace_reasoning_floor: 3,
    // Exam-countdown-aware default reasoning split (mirrors ScoringConfig
    // pace_focus_*). As days-to-exam shrinks, the DEFAULT per-section reasoning
    // target leans toward heavy AND under-covered sections; never overrides a
    // manual choice. CARS has no outline weight, so it is left out.
    pace_focus_horizon_days: 60, pace_focus_max: 1.0, pace_focus_gap_floor: 0.05,
    // Automatic maturity-gated topic interleaving (mirrors ScoringConfig
    // interleave_*). A section studies Blocked until enough of its review-stage
    // cards are mature (c.ivl >= interleave_mature_ivl_days), then Mixed; too few
    // graduated cards -> stay Blocked. Deterministic, so it matches the Python core.
    interleave_mature_ivl_days: 21, interleave_mature_fraction: 0.6, interleave_min_review_cards: 12,
    min_confidence_items: 10, overconfident_sure_max: 0.85, underconfident_guess_min: 0.55,
    min_mistakes: 4, content_ready_recall: 0.8,
    // CARS pacing: per-passage reading pace vs the exam's per-passage budget
    // (mirrors ScoringConfig.cars_exam_passages / min_pace_cars). The per-passage
    // budget is derived from SECTION_TIMING.cars and this passage count, never a
    // hard-coded seconds literal.
    cars_exam_passages: 9, min_pace_cars: 12,
    // score trajectory: project readiness to exam day (mirrors ScoringConfig.min_trajectory_days)
    min_trajectory_days: 2,
    seed: 42, resample_iters: 2000, ci_mass: 0.9,
    // paraphrase test / fluency illusion (section-level and per-concept). Mirrors
    // ScoringConfig.min_outcomes_transfer* and fluency_gap_threshold.
    min_outcomes_transfer: 10, fluency_gap_threshold: 0.15, min_outcomes_transfer_card: 3,
    // --- IRT latent-ability readiness (2PL, EAP over a fixed quadrature grid) ---
    // Mirrors the ScoringConfig irt_* fields exactly. When readiness_use_irt is on
    // (the desktop default), the IRT score feeds the dashboard whenever it clears
    // every honesty gate; otherwise the classic ability->scale path is the
    // fallback. Deterministic (fixed grid, no PRNG) so mobile == desktop.
    readiness_use_irt: true,
    irt_default_difficulty: 0, irt_default_discrimination: 1,
    irt_prior_mean: 0, irt_prior_sd: 1, irt_grid_points: 61,
    irt_theta_min: -4, irt_theta_max: 4,
    irt_scale_midpoint: 125, irt_scale_per_theta: 3, irt_min_information: 4,
  };

  // AAMC content category -> the standard MCAT prep-book subject.
  const SUBJECT_BY_CONCEPT = {
    '4A': 'Physics and Math', '4B': 'Physics and Math', '4D': 'Physics and Math',
    '4C': 'General Chemistry', '4E': 'General Chemistry', '5A': 'General Chemistry',
    '5B': 'General Chemistry', '5E': 'General Chemistry',
    '5C': 'Organic Chemistry', '5D': 'Organic Chemistry',
    '1A': 'Biochemistry', '1B': 'Biochemistry', '1D': 'Biochemistry',
    '1C': 'Biology', '2A': 'Biology', '2B': 'Biology', '2C': 'Biology', '3A': 'Biology', '3B': 'Biology',
    '6A': 'Behavioral Sciences', '6B': 'Behavioral Sciences', '6C': 'Behavioral Sciences',
    '7A': 'Behavioral Sciences', '7B': 'Behavioral Sciences', '7C': 'Behavioral Sciences',
    '8A': 'Behavioral Sciences', '8B': 'Behavioral Sciences', '8C': 'Behavioral Sciences',
    '9A': 'Behavioral Sciences', '9B': 'Behavioral Sciences', '10A': 'Behavioral Sciences',
  };

  const byId = {};
  OUTLINE.concepts.forEach((c) => { byId[c.id.toLowerCase()] = c; });
  const aliasToId = {};
  OUTLINE.concepts.forEach((c) => (c.aliases || []).forEach((a) => { if (!(a in aliasToId)) aliasToId[a] = c.id; }));

  const tokensOf = (tag) => tag.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  function matchTag(tag) {
    const tks = tokensOf(tag);
    if (!tks.length) return null;
    const set = new Set(tks);
    for (const c of OUTLINE.concepts) if (set.has(c.id.toLowerCase())) return c.id;
    const joined = tks.join('_');
    for (const a in aliasToId) {
      if (set.has(a)) return aliasToId[a];
      if (a.includes('_') && joined.includes(a)) return aliasToId[a];
    }
    return null;
  }
  const totalWeight = () => OUTLINE.concepts.reduce((s, c) => s + c.weight, 0);
  function weightedCoverage(covered) {
    const t = totalWeight();
    if (t <= 0) return 0;
    let g = 0;
    for (const c of OUTLINE.concepts) if (covered.has(c.id)) g += c.weight;
    return g / t;
  }
  function coverageBySection(covered) {
    const out = {};
    for (const s in OUTLINE.sections) {
      let sw = 0, g = 0;
      for (const c of OUTLINE.concepts) if (c.section === s) { sw += c.weight; if (covered.has(c.id)) g += c.weight; }
      out[s] = sw > 0 ? g / sw : 0;
    }
    return out;
  }

  // --- depth-aware (topic-grain) coverage, ported from outline.py so the phone's
  // "% of the exam covered" equals desktop's topic_coverage (the honest display
  // number) instead of the category-level coverage that saturates at 100%. The topic
  // grain (topics per concept + aliases + deck_topic_map) is inlined by
  // render.build_mobile_page into window.__VANTAGE_TOPICS__ from the SAME
  // aamc_outline.json / deck_topic_map.json the desktop uses, so there is no drift.
  const TOPICS = (typeof window !== 'undefined' && window.__VANTAGE_TOPICS__) || null;
  const conceptTopicIds = Object.create(null); // concept id -> [topic id, ...]
  const topicAliasToId = Object.create(null);  // alias (lower) -> topic id, first-wins
  const deckTopicMap = Object.create(null);    // normalized deck/tag path -> topic id
  if (TOPICS) {
    for (const c of (TOPICS.concepts || [])) {
      const ids = [];
      for (const t of (c.topics || [])) {
        ids.push(t.id);
        for (const a of (t.aliases || [])) {
          const al = String(a).toLowerCase();
          if (!(al in topicAliasToId)) topicAliasToId[al] = t.id;
        }
      }
      conceptTopicIds[c.id] = ids;
    }
    const dm = TOPICS.deck_topic_map || {};
    for (const k in dm) if (Object.prototype.hasOwnProperty.call(dm, k)) deckTopicMap[k] = dm[k];
  }
  // Map one raw tag to a TOPIC id (or null). Mirrors Outline._match_topic_uncached:
  // the exact normalized deck/tag path wins, else the first topic alias (insertion
  // order) that is a whole token, or a multi-word alias found in the "_"-joined tag.
  function matchTagTopic(tag) {
    const tks = tokensOf(tag);
    if (!tks.length) return null;
    const joined = tks.join('_');
    if (joined in deckTopicMap) return deckTopicMap[joined];
    const set = new Set(tks);
    for (const alias in topicAliasToId) {
      if (set.has(alias)) return topicAliasToId[alias];
      if (alias.indexOf('_') >= 0 && joined.indexOf(alias) >= 0) return topicAliasToId[alias];
    }
    return null;
  }
  // One category's fractional credit: covered-topic fraction when it has topics, else
  // 1.0 if the category itself is covered (matches outline._category_topic_credit).
  function categoryTopicCredit(concept, coveredT, coveredC) {
    const ids = conceptTopicIds[concept.id];
    if (ids && ids.length) {
      let n = 0;
      for (const tid of ids) if (coveredT.has(tid)) n += 1;
      return n / ids.length;
    }
    return coveredC.has(concept.id) ? 1 : 0;
  }
  function topicWeightedCoverage(coveredT, coveredC) {
    const t = totalWeight();
    if (t <= 0) return 0;
    let g = 0;
    for (const c of OUTLINE.concepts) g += c.weight * categoryTopicCredit(c, coveredT, coveredC);
    return g / t;
  }
  function topicCoverageBySection(coveredT, coveredC) {
    const out = {};
    for (const s in OUTLINE.sections) {
      let sw = 0, g = 0;
      for (const c of OUTLINE.concepts) if (c.section === s) { sw += c.weight; g += c.weight * categoryTopicCredit(c, coveredT, coveredC); }
      out[s] = sw > 0 ? g / sw : 0;
    }
    return out;
  }

  const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
  const round4 = (x) => Math.round(x * 10000) / 10000;
  const round3 = (x) => Math.round(x * 1000) / 1000;
  const round2 = (x) => Math.round(x * 100) / 100;
  const round1 = (x) => Math.round(x * 10) / 10;
  // Best-effort float; null for a missing/malformed value (config is untrusted).
  // Mirrors collect._as_float, used for optional IRT item difficulty/discrimination.
  const asFloat = (x) => { const v = typeof x === 'number' ? x : parseFloat(x); return Number.isFinite(v) ? v : null; };
  // Central 90% two-sided z; shared by the normal-approximation intervals below
  // and the section range, matching the Python core's z.
  const Z90 = 1.6448536269514722;
  // Deterministic normal-approximation CI for a mean (mirrors the Python core's
  // switch off the percentile bootstrap): mean +/- z * standard error, clamped
  // to [0, 1]. sd uses the sample (n-1) denominator and is 0 for a single value.
  function normalMeanCI(vals) {
    const n = vals.length;
    const mean = vals.reduce((a, b) => a + b, 0) / n;
    let sd = 0;
    if (n >= 2) {
      let ss = 0;
      for (const x of vals) ss += (x - mean) * (x - mean);
      sd = Math.sqrt(ss / (n - 1));
    }
    const se = sd / Math.sqrt(n);
    return { point: mean, low: clamp(mean - Z90 * se, 0, 1), high: clamp(mean + Z90 * se, 0, 1) };
  }
  function memoryScore(rValues) {
    const n = rValues.length;
    if (n < CFG.min_cards_memory) {
      return { abstained: true, how_sure: 'insufficient', n, reasons: [`only ${n} cards with a memory state (need >= ${CFG.min_cards_memory})`], point: null, low: null, high: null };
    }
    const b = normalMeanCI(rValues.map((r) => clamp(r, 0, 1)));
    const width = b.high - b.low;
    const how = width <= CFG.memory_high_max_width && n >= CFG.memory_high_min_n ? 'high' : width <= 2 * CFG.memory_high_max_width ? 'medium' : 'low';
    return {
      abstained: false, how_sure: how, n,
      reasons: [`mean retrievability ${Math.round(b.point * 100)}% over ${n} seen cards`, `range width ${Math.round(width * 100)}%`],
      point: round3(b.point), low: round3(b.low), high: round3(b.high),
    };
  }
  function wilson(k, n) {
    const z = 1.6448536269514722; // central 90%
    const p = k / n;
    const denom = 1 + (z * z) / n;
    const center = (p + (z * z) / (2 * n)) / denom;
    const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
    return { point: p, low: clamp(center - half, 0, 1), high: clamp(center + half, 0, 1) };
  }
  function performanceScore(perf) {
    const n = perf.n || 0;
    const k = perf.k || 0;
    if (n < CFG.min_outcomes_performance) {
      return { abstained: true, how_sure: 'insufficient', n, reasons: [`only ${n} application-item outcomes (need >= ${CFG.min_outcomes_performance})`], point: null, low: null, high: null };
    }
    const b = wilson(k, n);
    const width = b.high - b.low;
    const how = width <= CFG.perf_high_max_width && n >= CFG.perf_high_min_n ? 'high' : width <= 2 * CFG.perf_high_max_width ? 'medium' : 'low';
    return { abstained: false, how_sure: how, n, reasons: [`${k}/${n} application items correct (${Math.round(b.point * 100)}%)`], point: round3(b.point), low: round3(b.low), high: round3(b.high) };
  }

  // Documented, anchored, monotonic transform ability(0..1) -> 118..132, then
  // clamped to the section scale. Mirrors scoring.map_ability_to_scale.
  function mapAbilityToScale(ability) {
    const spanA = CFG.map_high_ability - CFG.map_low_ability;
    const spanS = CFG.map_high_scale - CFG.map_low_scale;
    const scaled = CFG.map_low_scale + ((ability - CFG.map_low_ability) / spanA) * spanS;
    return clamp(scaled, CFG.section_scale_min, CFG.section_scale_max);
  }

  // Readiness: a per-section projection onto the 118..132 scale, gated and ranged,
  // mirroring scoring.readiness. Abstains unless there are enough graded reviews,
  // enough of the exam covered, AND enough exam-style practice outcomes. Each
  // usable science section blends its reasoning accuracy (evidence) with its
  // recall (a weak prior of strength kappa); CARS is never modeled. The range is
  // a deterministic normal approximation of each section's posterior spread
  // (exact Monte-Carlo parity with desktop is not feasible on-device), summed to
  // the partial composite.
  function readinessScore(outcomes, sectionRecall, coverage, nReviews, totalOutcomes) {
    const reasons = [];
    if (nReviews < CFG.giveup_min_reviews)
      reasons.push(`${CFG.giveup_min_reviews} graded reviews (you have ${nReviews})`);
    if (coverage < CFG.giveup_min_coverage)
      reasons.push(`${Math.round(CFG.giveup_min_coverage * 100)}% of the exam covered (you have ${Math.round(coverage * 100)}%)`);
    if (totalOutcomes < CFG.min_outcomes_performance)
      reasons.push(`${CFG.min_outcomes_performance} exam-style practice questions answered (you have ${totalOutcomes})`);
    if (reasons.length) {
      return { abstained: true, how_sure: 'insufficient', n: nReviews, reasons, sections: {}, cars_modeled: false };
    }

    const kappa = CFG.projection_prior_strength;
    const kn = { chem_phys: { k: 0, n: 0 }, bio_biochem: { k: 0, n: 0 }, psych_soc: { k: 0, n: 0 } };
    for (const o of outcomes) {
      if (!(o.section in kn)) continue; // science sections only, never CARS
      kn[o.section].n += 1;
      if (o.correct) kn[o.section].k += 1;
    }

    const sections = {};
    let point = 0, low = 0, high = 0, widthSum = 0, usable = 0, weakest = null, weakestPt = Infinity;
    for (const s of ['chem_phys', 'bio_biochem', 'psych_soc']) {
      const k = kn[s].k, n = kn[s].n;
      if (n < CFG.min_outcomes_readiness) continue;
      const m = clamp(sectionRecall[s] || 0, 0, 1); // 0 if the section has no recall yet
      const ability = (k + m * kappa) / (n + kappa);
      const std = Math.sqrt((ability * (1 - ability)) / (n + kappa));
      const sp = mapAbilityToScale(ability);
      const sl = mapAbilityToScale(ability - Z90 * std);
      const sh = mapAbilityToScale(ability + Z90 * std);
      sections[s] = { point: round1(sp), low: round1(sl), high: round1(sh) };
      point += sp; low += sl; high += sh; widthSum += sh - sl; usable += 1;
      if (sp < weakestPt) { weakestPt = sp; weakest = s; }
    }

    if (!usable) {
      return { abstained: true, how_sure: 'insufficient', n: nReviews, reasons: [`at least ${CFG.min_outcomes_readiness} practice questions in one science section`], sections: {}, cars_modeled: false };
    }

    const avgWidth = widthSum / usable;
    const how = avgWidth <= CFG.ready_high_max_width && coverage >= CFG.ready_high_min_coverage ? 'high' : avgWidth <= 2 * CFG.ready_high_max_width ? 'medium' : 'low';
    const reasonsOut = [
      `projected across ${usable} of 3 science sections`,
      `${Math.round(coverage * 100)}% of the exam covered`,
    ];
    if (weakest) reasonsOut.push(`weakest section so far: ${OUTLINE.sections[weakest]} (${kn[weakest].k}/${kn[weakest].n} questions)`);
    return {
      abstained: false, how_sure: how, n: nReviews, cars_modeled: false,
      point: round1(point), low: round1(low), high: round1(high),
      sections, reasons: reasonsOut,
    };
  }

  // --------------------------------------------------------------------------- //
  // IRT latent-ability readiness (2PL item-response model, EAP over a fixed grid)
  // A faithful, deterministic port of scoring.irt_* (irt_prob, irt_information,
  // _irt_grid, irt_estimate, theta_to_scale, irt_readiness). Expected A Posteriori
  // over a FIXED quadrature grid with a normal prior -- no PRNG anywhere -- so the
  // phone reproduces theta, its posterior SD, and every section/composite band
  // bit-for-bit against the desktop core (the parity mandate). Ability is estimated
  // from WHICH items were right (each with a difficulty b and discrimination a),
  // not merely how many, and the per-item Fisher information gives a first-class
  // abstain gate (too little information -> no number).
  // --------------------------------------------------------------------------- //

  // Inverse standard-normal CDF (Acklam's rational approximation). The IRT path
  // uses THIS for its z (as scoring.irt_readiness does via _inv_norm_cdf), not the
  // Z90 literal, so z == scoring._inv_norm_cdf(0.95) to full precision and the
  // section/composite bands agree with desktop.
  function invNormCdf(p) {
    if (!(p > 0 && p < 1)) throw new Error('p must be in (0,1)');
    const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239e0];
    const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
    const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0, -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0];
    const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0, 3.754408661907416e0];
    const plow = 0.02425, phigh = 1 - plow;
    let q, r;
    if (p < plow) {
      q = Math.sqrt(-2 * Math.log(p));
      return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    }
    if (p > phigh) {
      q = Math.sqrt(-2 * Math.log(1 - p));
      return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    }
    q = p - 0.5; r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }

  // 2PL probability of a correct response: logistic in a * (theta - b).
  function irtProb(theta, a, b) { return 1 / (1 + Math.exp(-a * (theta - b))); }
  // Fisher information one 2PL item carries at theta: a^2 * p * (1 - p).
  function irtInformation(theta, a, b) { const p = irtProb(theta, a, b); return a * a * p * (1 - p); }
  function normalPdf(x, mu, sd) { const z = (x - mu) / sd; return Math.exp(-0.5 * z * z) / (sd * Math.sqrt(2 * Math.PI)); }
  // The fixed (node, prior-weight) quadrature grid: evenly spaced nodes over
  // [theta_min, theta_max] with the normal-prior density as each weight. The
  // absolute normalization cancels in the EAP ratio, so this rebuilds the same
  // grid desktop uses (_irt_grid).
  function irtGrid() {
    const n = CFG.irt_grid_points;
    const lo = CFG.irt_theta_min, hi = CFG.irt_theta_max;
    const step = (hi - lo) / (n - 1);
    const g = [];
    for (let i = 0; i < n; i++) {
      const x = lo + step * i;
      g.push([x, normalPdf(x, CFG.irt_prior_mean, CFG.irt_prior_sd)]);
    }
    return g;
  }
  // EAP estimate of latent ability from 2PL responses (irt_estimate). posterior is
  // prior(theta) * prod_i P_i^u_i (1-P_i)^(1-u_i), evaluated on the fixed grid in
  // log-space with a max-subtraction so a long item list can't underflow. Returns
  // theta (posterior mean), theta_sd (its SD), information (2PL test info at theta).
  // items: [{ correct: 0|1, a, b }]. Fully deterministic (no PRNG).
  function nowStamp() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function irtEstimate(items) {
    const grid = irtGrid();
    const logPost = [];
    for (let gi = 0; gi < grid.length; gi++) {
      const x = grid[gi][0], w = grid[gi][1];
      let ll = w > 0 ? Math.log(w) : -Infinity;
      for (let ii = 0; ii < items.length; ii++) {
        const it = items[ii];
        const p = clamp(irtProb(x, it.a, it.b), 1e-12, 1 - 1e-12);
        ll += it.correct ? Math.log(p) : Math.log(1 - p);
      }
      logPost.push(ll);
    }
    let maxLl = -Infinity;
    for (let i = 0; i < logPost.length; i++) if (logPost[i] > maxLl) maxLl = logPost[i];
    const weights = logPost.map((lp) => Math.exp(lp - maxLl));
    let total = 0; for (let i = 0; i < weights.length; i++) total += weights[i];
    if (total <= 0) return { theta: CFG.irt_prior_mean, theta_sd: CFG.irt_prior_sd, information: 0, n: items.length };
    let theta = 0; for (let i = 0; i < grid.length; i++) theta += grid[i][0] * weights[i]; theta /= total;
    let varSum = 0; for (let i = 0; i < grid.length; i++) { const dv = grid[i][0] - theta; varSum += weights[i] * dv * dv; } varSum /= total;
    const sd = Math.sqrt(Math.max(0, varSum));
    let info = 0; for (let i = 0; i < items.length; i++) info += irtInformation(theta, items[i].a, items[i].b);
    return { theta, theta_sd: sd, information: info, n: items.length };
  }
  // Documented monotonic transform theta -> 118..132 as midpoint + per_theta*theta,
  // clamped to the section band (theta = 0 -> the scale midpoint). Mirrors theta_to_scale.
  function thetaToScale(theta) {
    const scaled = CFG.irt_scale_midpoint + CFG.irt_scale_per_theta * theta;
    return clamp(scaled, CFG.section_scale_min, CFG.section_scale_max);
  }
  // Readiness via 2PL IRT latent ability (irt_readiness): per science section plus a
  // labeled 3-section partial composite, each with an honest range. Same honesty
  // gates as the classic path (give-up rule + minimum total items + a per-section
  // minimum item COUNT). A section the student aces carries little Fisher
  // information, so IRT can't pin its score -- that shows as a wide range, not a
  // dropped section. Section range is thetaToScale(theta +/- z*sd) (monotone map),
  // and the composite range propagates the independent section bands. CARS is never
  // modeled. sectionItems: { section: [{ correct, a, b }] }.
  function irtReadiness(sectionItems, coverage, nReviews, totalItems) {
    const reasons = [];
    if (nReviews < CFG.giveup_min_reviews)
      reasons.push(`${CFG.giveup_min_reviews} graded reviews (you have ${nReviews})`);
    if (coverage < CFG.giveup_min_coverage)
      reasons.push(`${Math.round(CFG.giveup_min_coverage * 100)}% of the exam covered (you have ${Math.round(coverage * 100)}%)`);
    if (totalItems < CFG.min_outcomes_performance)
      reasons.push(`${CFG.min_outcomes_performance} exam-style practice questions answered (you have ${totalItems})`);
    if (reasons.length) {
      return { abstained: true, how_sure: 'insufficient', n: nReviews, reasons, sections: {}, cars_modeled: false };
    }
    const z = invNormCdf(1 - (1 - CFG.ci_mass) / 2);
    const sections = {};
    const est = {};
    const usable = [];
    // Score the three science sections plus CARS: CARS joins the composite (lifting
    // it toward the full 4-section 472-528 scale) only once it has enough answered
    // reasoning items; the activation gate above keys on the science sections.
    for (const s of ['chem_phys', 'bio_biochem', 'psych_soc', 'cars']) {
      const items = sectionItems[s] || [];
      // include a section once it has enough answered items (matches the classic
      // count gate); a section the student aces yields little Fisher information,
      // so IRT can't pin the score -> a wide honest range, not a dropped section.
      if (items.length < CFG.min_outcomes_readiness) continue;
      const e = irtEstimate(items);
      sections[s] = {
        point: round1(thetaToScale(e.theta)),
        low: round1(thetaToScale(e.theta - z * e.theta_sd)),
        high: round1(thetaToScale(e.theta + z * e.theta_sd)),
      };
      est[s] = e;
      usable.push(s);
    }
    if (!usable.length) {
      return {
        abstained: true, how_sure: 'insufficient', n: nReviews, sections: {}, cars_modeled: false,
        reasons: ['not enough exam-style practice in one science section yet to estimate a score'],
      };
    }
    const compLo = usable.length * CFG.section_scale_min;
    const compHi = usable.length * CFG.section_scale_max;
    let compPoint = 0; for (const s of usable) compPoint += sections[s].point;
    let sig2 = 0; for (const s of usable) { const w = (sections[s].high - sections[s].low) / (2 * z); sig2 += w * w; }
    const compSigma = Math.sqrt(sig2);
    const point = round1(compPoint);
    const low = round1(clamp(compPoint - z * compSigma, compLo, compHi));
    const high = round1(clamp(compPoint + z * compSigma, compLo, compHi));
    let widthSum = 0; for (const s of usable) widthSum += sections[s].high - sections[s].low;
    const avgWidth = widthSum / usable.length;
    const how = avgWidth <= CFG.ready_high_max_width && coverage >= CFG.ready_high_min_coverage ? 'high' : avgWidth <= 2 * CFG.ready_high_max_width ? 'medium' : 'low';
    const reasonsOut = [
      `projected across ${usable.length} section(s)`,
      `${Math.round(coverage * 100)}% of the exam covered`,
    ];
    let weakest = null, weakestPt = Infinity;
    for (const s of usable) if (sections[s].point < weakestPt) { weakestPt = sections[s].point; weakest = s; }
    if (weakest) reasonsOut.push(`weakest section so far: ${OUTLINE.sections[weakest] || (weakest === 'cars' ? 'CARS' : weakest)} (${est[weakest].n} questions)`);
    const r4 = (x) => Math.round(x * 1e4) / 1e4;
    const carsModeled = usable.indexOf('cars') !== -1;
    return {
      abstained: false, how_sure: how, n: nReviews, cars_modeled: carsModeled,
      point, low, high, sections, reasons: reasonsOut,
      // Parity with desktop _readiness: expose the IRT metadata so the readiness
      // card shows practice-question wording AND practice.js adaptiveOrder can read
      // each section's latent theta to serve the most-informative item first.
      model: 'irt_2pl_eap',
      modeled_sections: usable.slice(),
      scale_note: carsModeled ? 'full 4-section 472-528 composite' : `${usable.length}-section partial of the 472-528 scale; CARS not yet scored`,
      irt: usable.reduce((o, s) => {
        o[s] = { theta: r4(est[s].theta), theta_sd: r4(est[s].theta_sd), information: r4(est[s].information), n: est[s].n };
        return o;
      }, {}),
    };
  }

  // --------------------------------------------------------------------------- //
  // paraphrase test (transfer gap: memory vs application on the same material).
  // transferGap mirrors scoring.transfer_gap (per section); conceptTransferGaps
  // mirrors scoring.concept_transfer_gaps (per concept -- the "fluency illusion"
  // list). A large positive gap means the student recalls the fact but cannot yet
  // use it. Reported only with a memory signal AND enough application items.
  // --------------------------------------------------------------------------- //
  function transferGap(sectionRecall, sectionApp) {
    const out = {};
    for (const s of ['chem_phys', 'bio_biochem', 'psych_soc']) {
      const recall = sectionRecall[s];
      const outs = sectionApp[s] || [];
      if (recall === undefined || recall === null || outs.length < CFG.min_outcomes_transfer) continue;
      const application = outs.reduce((a, b) => a + b, 0) / outs.length;
      const r = clamp(recall, 0, 1);
      const gap = r - application;
      out[s] = {
        section: s, recall: round3(r), application: round3(application),
        gap: round3(gap), n_app: outs.length, fluency_risk: gap >= CFG.fluency_gap_threshold,
      };
    }
    return out;
  }
  // Card-level paraphrase test, per concept: recall vs application accuracy, worst
  // fluency illusion first (gap descending, then concept id). conceptRecall keys the
  // iteration, so a concept with application items but no memory signal is excluded.
  function conceptTransferGaps(conceptRecall, conceptApp, conceptSection) {
    const out = [];
    for (const cid in conceptRecall) {
      const outs = conceptApp[cid] || [];
      if (outs.length < CFG.min_outcomes_transfer_card) continue;
      const application = outs.reduce((a, b) => a + b, 0) / outs.length;
      const r = clamp(conceptRecall[cid], 0, 1);
      const gap = r - application;
      const c = byId[cid.toLowerCase()];
      out.push({
        concept_id: cid, name: (c && c.name) || cid, section: conceptSection[cid] || (c && c.section) || '',
        recall: round3(r), application: round3(application), gap: round3(gap),
        n_app: outs.length, fluency_risk: gap >= CFG.fluency_gap_threshold,
      });
    }
    // worst fluency illusion first, then a stable tiebreak by concept id (matches
    // Python's sort key (-gap, concept_id), using the rounded gap).
    out.sort((x, y) => (y.gap - x.gap) || (x.concept_id < y.concept_id ? -1 : x.concept_id > y.concept_id ? 1 : 0));
    return out;
  }

  function nextTopics(covered, conceptR, top) {
    const items = OUTLINE.concepts.map((c) => {
      const rs = conceptR[c.id] || [];
      const mastery = rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 0;
      return {
        concept_id: c.id, name: c.name, section: c.section, weight: c.weight,
        mastery: round3(mastery), covered: covered.has(c.id), priority: round3(c.weight * (1 - mastery)),
        subject: SUBJECT_BY_CONCEPT[c.id] || '',
        topics: (c.aliases || []).slice(0, 4).map((a) => a.replace(/_/g, ' ')),
      };
    });
    items.sort((a, b) => b.priority - a.priority);
    return items.slice(0, top || 6);
  }

  function calibration(pairs) {
    const n = pairs.length;
    if (n < CFG.min_outcomes_calibration) {
      return { abstained: true, how_sure: 'insufficient', n, bins: [] };
    }
    const meanPred = pairs.reduce((s, p) => s + p[0], 0) / n;
    const meanObs = pairs.reduce((s, p) => s + p[1], 0) / n;
    const well = Math.abs(meanPred - meanObs) <= CFG.calibration_well_within;
    const how = n >= 60 ? 'high' : n >= 2 * CFG.min_outcomes_calibration ? 'medium' : 'low';
    return {
      abstained: false, how_sure: how, n,
      mean_predicted: round3(meanPred), mean_observed: round3(meanObs), well_calibrated: well, bins: [],
    };
  }

  function confidenceCalibration(outcomes) {
    const ok = ['guess', 'unsure', 'sure'];
    const labeled = outcomes.filter((o) => ok.includes(o.confidence));
    const n = labeled.length;
    if (n < CFG.min_confidence_items) return { abstained: true, n, levels: [] };
    const by = { guess: [], unsure: [], sure: [] };
    labeled.forEach((o) => by[o.confidence].push(o.correct ? 1 : 0));
    const rate = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
    const levels = [];
    for (const lvl of ok) if (by[lvl].length) levels.push({ level: lvl, n: by[lvl].length, rate: round3(rate(by[lvl])) });
    let insight = 'Your confidence lines up with your results.';
    if (by.sure.length >= 3 && rate(by.sure) < CFG.overconfident_sure_max) {
      insight = `When you felt sure you were right ${Math.round(rate(by.sure) * 100)}%. Slow down on the ones you are sure about.`;
    } else if (by.guess.length >= 3 && rate(by.guess) > CFG.underconfident_guess_min) {
      insight = `You got ${Math.round(rate(by.guess) * 100)}% of your guesses right. Trust your reasoning more, and move faster.`;
    }
    return { abstained: false, n, levels, insight };
  }

  function mistakeTaxonomy(outcomes) {
    const reasons = ['content', 'misread', 'trap', 'time', 'math'];
    const wrong = outcomes.filter((o) => !o.correct && reasons.includes(o.reason));
    const n = wrong.length;
    if (n < CFG.min_mistakes) return { abstained: true, n_wrong: n, items: [] };
    const by = {};
    wrong.forEach((o) => { by[o.reason] = (by[o.reason] || 0) + 1; });
    const items = Object.keys(by).map((r) => ({ reason: r, count: by[r] })).sort((a, b) => b.count - a.count);
    const top = items[0].reason;
    const sec = {};
    wrong.filter((o) => o.reason === top).forEach((o) => { sec[o.section] = (sec[o.section] || 0) + 1; });
    const topSection = Object.keys(sec).sort((a, b) => sec[b] - sec[a])[0] || null;
    return { abstained: false, n_wrong: n, items, top_reason: top, top_section: topSection };
  }

  // Second axis of the miss diagnosis: which AAMC reasoning skill the misses test.
  // Byte-for-byte the same shape/gate as mistakeTaxonomy (port of scoring.skill_taxonomy);
  // the skill comes off each outcome (the anchor card's vantage::skill:: tag).
  function skillTaxonomy(outcomes) {
    const skills = ['concepts', 'reasoning', 'research', 'data'];
    const wrong = outcomes.filter((o) => !o.correct && skills.includes(o.skill));
    const n = wrong.length;
    if (n < CFG.min_mistakes) return { abstained: true, n_wrong: n, items: [] };
    const by = {};
    wrong.forEach((o) => { by[o.skill] = (by[o.skill] || 0) + 1; });
    const items = Object.keys(by).map((k) => ({ skill: k, count: by[k] })).sort((a, b) => b.count - a.count);
    const top = items[0].skill;
    const sec = {};
    wrong.filter((o) => o.skill === top).forEach((o) => { sec[o.section] = (sec[o.section] || 0) + 1; });
    const topSection = Object.keys(sec).sort((a, b) => sec[b] - sec[a])[0] || null;
    return { abstained: false, n_wrong: n, items, top_skill: top, top_section: topSection };
  }

  function studyPlanJS(covered, conceptR) {
    const study = [], practice = [];
    for (const c of OUTLINE.concepts) {
      const rs = conceptR[c.id] || [];
      const recall = rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null;
      if (recall === null || recall < CFG.content_ready_recall) {
        study.push({ concept_id: c.id, name: c.name, section: c.section, recall: recall === null ? null : round3(recall), priority: c.weight * (1 - (recall || 0)) });
      } else {
        practice.push({ concept_id: c.id, name: c.name, section: c.section, recall: round3(recall), priority: c.weight });
      }
    }
    study.sort((a, b) => b.priority - a.priority);
    practice.sort((a, b) => b.priority - a.priority);
    return { study: study.slice(0, 5), practice: practice.slice(0, 5) };
  }

  const SECTION_TIMING = { chem_phys: [59, 95], bio_biochem: [59, 95], psych_soc: [59, 95], cars: [53, 90] };
  function median(xs) {
    const s = xs.slice().sort((a, b) => a - b);
    const n = s.length, m = n >> 1;
    return n % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function pacingCoach(outcomes) {
    const timed = outcomes.filter((o) => o.ms && o.ms > 0);
    if (timed.length < 8) return { abstained: true, n: timed.length, sections: [] };
    const by = {};
    timed.forEach((o) => { (by[o.section] = by[o.section] || []).push(o.ms / 1000); });
    const sections = [];
    for (const s in by) {
      const vals = by[s];
      if (vals.length < 3 || !SECTION_TIMING[s]) continue;
      const med = median(vals);
      const q = SECTION_TIMING[s][0], limit = SECTION_TIMING[s][1] * 60, target = limit / q;
      if (med <= target) {
        sections.push({ section: s, n: vals.length, median_sec: Math.round(med * 10) / 10, target_sec: Math.round(target * 10) / 10, on_pace: true, projected_left: 0, spare_min: Math.round(((limit - med * q) / 60) * 10) / 10 });
      } else {
        sections.push({ section: s, n: vals.length, median_sec: Math.round(med * 10) / 10, target_sec: Math.round(target * 10) / 10, on_pace: false, projected_left: Math.max(0, q - Math.floor(limit / med)), spare_min: 0 });
      }
    }
    if (!sections.length) return { abstained: true, n: timed.length, sections: [] };
    // Attach the CARS-only per-passage view (a speed signal, never a score). It runs
    // off the same outcomes and reuses SECTION_TIMING.cars; it stays an honest abstain
    // until CARS has enough timed questions of its own (mirrors scoring.pacing_coach).
    return { abstained: false, n: timed.length, sections, overall_on_pace: sections.every((x) => x.on_pace), cars: carsPacing(outcomes) };
  }

  // CARS pace stated the way the section is timed: minutes per PASSAGE. A faithful
  // port of scoring.cars_pacing. CARS is pure reading comprehension, so a student
  // paces it by the passage, not the single question. Reuses the exact CARS budget
  // pacingCoach uses (SECTION_TIMING.cars = 53 q / 90 min) and the same robust median,
  // then re-expresses that per-question pace as projected minutes per passage against
  // the exam's per-passage budget (90 min / cars_exam_passages). Deterministic, and
  // MUST match scoring.cars_pacing bit-for-bit. Abstains (give-up rule) until
  // CFG.min_pace_cars timed CARS questions exist, never a placeholder pace.
  function carsPacing(outcomes) {
    const timed = outcomes.filter((o) => o.section === 'cars' && o.ms && o.ms > 0).map((o) => o.ms / 1000);
    const n = timed.length;
    if (n < CFG.min_pace_cars) {
      return {
        abstained: true, n,
        median_sec: 0, target_sec: 0, per_passage_min: 0, target_passage_min: 0,
        over_budget_pct: 0, on_pace: true,
        reasons: [`only ${n} timed CARS questions (need >= ${CFG.min_pace_cars})`],
      };
    }
    const q = SECTION_TIMING.cars[0], mins = SECTION_TIMING.cars[1];
    const passages = Math.max(1, CFG.cars_exam_passages);
    const questionsPerPassage = q / passages;
    const targetSec = (mins * 60) / q; // per-question budget (matches SectionPace)
    const targetPassageMin = mins / passages; // per-passage budget in minutes
    const med = median(timed);
    const perPassageMin = (med * questionsPerPassage) / 60;
    const overBudgetPct = Math.round(((perPassageMin - targetPassageMin) / targetPassageMin) * 100);
    const onPace = med <= targetSec;
    const reasons = [
      `typical ${Math.round(med)}s per CARS question over ${n} timed questions`,
      `about ${perPassageMin.toFixed(1)} min per passage vs a ${Math.round(targetPassageMin)} min budget`,
    ];
    return {
      abstained: false, n,
      median_sec: Math.round(med * 10) / 10,
      target_sec: Math.round(targetSec * 10) / 10,
      per_passage_min: Math.round(perPassageMin * 10) / 10,
      target_passage_min: Math.round(targetPassageMin * 10) / 10,
      over_budget_pct: overBudgetPct,
      on_pace: onPace,
      reasons,
    };
  }

  function studyPace(raw, reasoningDone, conceptsToPractice, cardsStudied, reasoningToday) {
    const target = CFG.pace_reasoning_target;
    const remaining = Math.max(0, target - reasoningDone);
    const base = {
      reviews_due: raw.reviews_due || 0, new_remaining: raw.new_remaining || 0,
      reasoning_target: target, reasoning_done: reasoningDone, reasoning_today: reasoningToday || 0, reasoning_remaining: remaining,
    };
    const exam = raw.exam_date;
    if (!exam) return Object.assign({ has_exam_date: false, message: 'Set your exam date to get a daily study target.' }, base);
    const today = raw.today || new Date().toISOString().slice(0, 10);
    const dl = Math.round((Date.parse(exam) - Date.parse(today)) / 86400000);
    if (isNaN(dl)) return Object.assign({ has_exam_date: false, message: 'Could not read the exam date.' }, base);
    if (dl < 0) return Object.assign({ has_exam_date: true, exam_date: exam, days_left: dl, passed: true, message: 'Your exam date has passed. Set a new one to get a plan.' }, base);
    const div = Math.max(1, dl);
    // Daily reasoning goal derives from real exam breadth (concepts left x a
    // per-concept budget) with a floor; mirrors scoring.study_pace on desktop.
    const prep = (conceptsToPractice || 0) * (CFG.pace_reasoning_per_concept || 10);
    const reasoningPerDay = Math.max(CFG.pace_reasoning_floor || 3, Math.ceil(prep / div));
    // Flashcards: FSRS due today, ramping to a full pass by exam day as time shrinks.
    const flashcardsPerDay = Math.max(raw.reviews_due || 0, Math.ceil(((raw.new_remaining || 0) + (cardsStudied || 0)) / div));
    // "Before exam day" totals that scale with the date (mirrors scoring.study_pace).
    return Object.assign({
      has_exam_date: true, exam_date: exam, days_left: dl, passed: false, flashcards_per_day: flashcardsPerDay,
      new_per_day: Math.ceil((raw.new_remaining || 0) / div), reasoning_per_day: reasoningPerDay,
      flashcards_to_exam: flashcardsPerDay * dl, reasoning_to_exam: reasoningPerDay * dl, message: '',
    }, base);
  }

  // --------------------------------------------------------------------------- //
  // exam-countdown-aware default reasoning split (study-plan rebalancing). A
  // faithful, deterministic port of scoring.reasoning_focus / _largest_remainder
  // / resolve_focus_section. Planning logic, separate from the scores: it only
  // decides the DEFAULT per-section reasoning split, and it takes NO manual-choice
  // argument, so it can never override one. Same integer targets and default
  // section as the desktop core on identical inputs (the parity mandate).
  // --------------------------------------------------------------------------- //

  // Hamilton / largest-remainder apportionment: floor each quota, then hand the
  // leftover to the largest fractional parts, ties broken by key. Always sums to
  // `total`. `shares` is an array of [key, share]. Matches scoring._largest_remainder.
  function largestRemainder(shares, total) {
    const out = {};
    shares.forEach((kv) => { out[kv[0]] = 0; });
    if (total <= 0 || !shares.length) return out;
    const quotas = shares.map((kv) => [kv[0], kv[1] * total]);
    quotas.forEach((kq) => { out[kq[0]] = Math.floor(kq[1]); });
    let used = 0; quotas.forEach((kq) => { used += out[kq[0]]; });
    const leftover = total - used;
    const order = quotas.slice().sort((a, b) => {
      const fa = a[1] - Math.floor(a[1]), fb = b[1] - Math.floor(b[1]);
      if (fb !== fa) return fb - fa;                                  // larger fraction first
      return a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0);               // tie-break by key asc
    });
    for (let i = 0; i < Math.max(0, leftover); i++) out[order[i % order.length][0]] += 1;
    return out;
  }

  // reasoningFocus(perDay, sectionWeight, sectionCoverage, daysToExam) -> the same
  // shape render.py serializes for study_pace.reasoning_focus. `sectionWeight` maps
  // a section to its raw AAMC exam weight (0 = excluded, e.g. CARS); `sectionCoverage`
  // maps a section to coverage in 0..1; `daysToExam` may be null.
  function reasoningFocus(perDay, sectionWeight, sectionCoverage, daysToExam) {
    const pd = Math.max(0, Math.trunc(perDay || 0));
    const secs = Object.keys(sectionWeight).filter((s) => sectionWeight[s] > 0).sort();
    let totalW = 0; secs.forEach((s) => { totalW += sectionWeight[s]; });
    if (!secs.length || totalW <= 0) {
      return { has_focus: false, per_day: pd, days_to_exam: daysToExam == null ? null : daysToExam, concentration: 0, default_section: null, by_section: [] };
    }
    const base = {}, gap = {}, raw = {};
    secs.forEach((s) => {
      base[s] = sectionWeight[s] / totalW;
      const cov = Number(sectionCoverage[s]) || 0;
      gap[s] = Math.min(1, Math.max(0, 1 - cov));
      raw[s] = base[s] * Math.max(CFG.pace_focus_gap_floor, gap[s]);
    });
    let rawTotal = 0; secs.forEach((s) => { rawTotal += raw[s]; });
    const prio = {};
    secs.forEach((s) => { prio[s] = rawTotal > 0 ? raw[s] / rawTotal : base[s]; });
    const horizon = Math.max(1, CFG.pace_focus_horizon_days);
    let k;
    if (daysToExam == null) k = 0;
    else {
      const frac = (horizon - Math.max(0, daysToExam)) / horizon;
      k = CFG.pace_focus_max * Math.min(1, Math.max(0, frac));
    }
    const blended = {};
    secs.forEach((s) => { blended[s] = (1 - k) * base[s] + k * prio[s]; });
    const alloc = largestRemainder(secs.map((s) => [s, blended[s]]), pd);
    const rows = secs.map((s) => ({
      section: s,
      weight: round4(base[s]),
      coverage: round4(Number(sectionCoverage[s]) || 0),
      gap: round4(gap[s]),
      share: round4(blended[s]),
      target: alloc[s],
    }));
    rows.sort((a, b) => (b.share - a.share) || (a.section < b.section ? -1 : (a.section > b.section ? 1 : 0)));
    return {
      has_focus: true, per_day: pd, days_to_exam: daysToExam == null ? null : daysToExam,
      concentration: round4(k), default_section: rows[0].section, by_section: rows,
    };
  }

  // resolveFocusSection(manual, focus) -> [section, isManual]. The one place the
  // "never override a manual choice" rule lives; mirrors scoring.resolve_focus_section.
  function resolveFocusSection(manual, focus) {
    if (manual) return [manual, true];
    return [focus ? focus.default_section : null, false];
  }

  // --------------------------------------------------------------------------- //
  // score trajectory (project the readiness composite to exam day). A faithful,
  // deterministic port of scoring.trajectory: an ordinary least-squares slope over
  // the dated { d, point } readiness snapshots, extrapolated to exam day and
  // clamped to the three-section band (3 x 118..132 = 354..396). Honesty-first
  // (the give-up rule): abstains until there are at least min_trajectory_days
  // DISTINCT days of history AND a target score AND an exam date, so a single point
  // never invents a trend. No PRNG. The regression x-values are Python
  // date.toordinal() ordinals (isoToOrdinal), so the least-squares sums run on
  // operands identical to the desktop core (both IEEE-754 doubles) and the
  // projected point matches bit-for-bit to rounding -- the parity mandate.
  // --------------------------------------------------------------------------- //

  // Proleptic-Gregorian ordinal of an ISO "YYYY-MM-DD" date, matching Python's
  // datetime.date.toordinal() exactly (0001-01-01 -> 1). Using the SAME integer
  // x-values as scoring.trajectory keeps the OLS accumulation bit-identical across
  // Python and JS, so the slope and projection agree to the last decimal. Returns
  // NaN for an unparseable date (config is untrusted).
  const DAYS_BEFORE_MONTH = [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  function isoToOrdinal(s) {
    const parts = String(s).split('-');
    if (parts.length !== 3) return NaN;
    const y = parseInt(parts[0], 10), mo = parseInt(parts[1], 10), d = parseInt(parts[2], 10);
    if (!Number.isInteger(y) || !Number.isInteger(mo) || !Number.isInteger(d) || mo < 1 || mo > 12) return NaN;
    const yy = y - 1;
    const daysBeforeYear = yy * 365 + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400);
    const isLeap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
    const daysBeforeMonth = DAYS_BEFORE_MONTH[mo] + (mo > 2 && isLeap ? 1 : 0);
    return daysBeforeYear + daysBeforeMonth + d;
  }

  // trajectory(history, target, daysToExam, weakest) -> the same shape as
  // scoring.trajectory's Trajectory dataclass (abstained / projected / target /
  // on_pace / per_week / weakest_section / reason). history is
  // [{ d: 'YYYY-MM-DD', point: number }]; daysToExam is an integer day count
  // (may be 0 or negative, exactly as collect.gather passes days_left), or null.
  function trajectory(history, target, daysToExam, weakest, nSections) {
    // The target lives on the scale of the sections currently modeled: 3 science
    // (354-396) or the full 472-528 once CARS is scored. A full-scale target is
    // never compared to a partial projection; if it's off-scale, we abstain and ask
    // for an in-scale one (mirrors scoring.trajectory).
    const n = Math.max(1, nSections || 3);
    const scaleLo = Math.round(n * CFG.section_scale_min);
    const scaleHi = Math.round(n * CFG.section_scale_max);
    if (daysToExam === null || daysToExam === undefined) {
      return { abstained: true, target: target || null, scale_lo: scaleLo, scale_hi: scaleHi, reason: 'set a target score and an exam date' };
    }
    if (!target) {
      return { abstained: true, target: target || null, scale_lo: scaleLo, scale_hi: scaleHi, reason: `set a target on the ${scaleLo}-${scaleHi} scale and an exam date` };
    }
    if (!(target >= scaleLo && target <= scaleHi)) {
      return { abstained: true, target, scale_lo: scaleLo, scale_hi: scaleHi, reason: `set a target on the ${scaleLo}-${scaleHi} scale for the sections you're modeling` };
    }
    // distinct-days gate: mirrors sorted({h["d"]}) then len < min_trajectory_days
    const days = new Set();
    for (const h of history) days.add(h.d);
    if (days.size < CFG.min_trajectory_days) {
      return { abstained: true, target, scale_lo: scaleLo, scale_hi: scaleHi, reason: 'your trajectory appears after a few days of study' };
    }
    // least-squares slope over ALL snapshots (not de-duplicated), accumulated in
    // input order to match the Python core's summation exactly.
    const pts = history.map((h) => [isoToOrdinal(h.d), Number(h.point)]);
    const m = pts.length;
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = 0; i < m; i++) { const x = pts[i][0], y = pts[i][1]; sx += x; sy += y; sxx += x * x; sxy += x * y; }
    const denom = m * sxx - sx * sx;
    const slope = denom ? (m * sxy - sx * sy) / denom : 0;
    // anchor on the most recent snapshot BY DATE, not input order (first on a tie,
    // like Python's max), so an out-of-order history still projects from the latest.
    let base = pts[0][1], baseOrd = pts[0][0];
    for (let i = 1; i < m; i++) if (pts[i][0] > baseOrd) { baseOrd = pts[i][0]; base = pts[i][1]; }
    // clamp the linear extrapolation to the current composite scale, so a steep
    // recent slope can't project an impossible number (only same-scale snapshots
    // feed this, so the base sits on the [scaleLo, scaleHi] band).
    const projected = Math.min(scaleHi, Math.max(scaleLo, base + slope * daysToExam));
    return {
      abstained: false,
      projected: round1(projected),
      target,
      on_pace: projected >= target, // uses the UNrounded projected, like desktop
      per_week: round2(slope * 7),
      weakest_section: weakest || null,
      scale_lo: scaleLo,
      scale_hi: scaleHi,
      reason: '',
    };
  }

  // Port of scoring.section_should_mix: decide whether a section's flashcards
  // study Mixed (topics interleaved, to train discrimination) or Blocked (grouped
  // by topic, for focused acquisition), from how many of its review-stage cards
  // have matured. Honest default is Blocked. Pure + deterministic, so desktop and
  // mobile reach the identical decision and reason string.
  function sectionShouldMix(matureCount, reviewCount) {
    if (reviewCount < CFG.interleave_min_review_cards) return { mixed: false, reason: 'not enough graduated cards yet' };
    if (matureCount < CFG.interleave_mature_fraction * reviewCount) return { mixed: false, reason: 'still consolidating' };
    return { mixed: true, reason: 'enough cards have matured' };
  }

  window.vantageComputeFromRaw = function (raw) {
    const covered = new Set();
    const coveredTopics = new Set();
    const rValues = [];
    const conceptR = {};
    for (const row of raw.cards) {
      const tags = row[0], r = row[1];
      const cc = new Set();
      for (const t of (tags || '').split(/\s+/)) {
        if (!t) continue;
        const cid = matchTag(t); if (cid) cc.add(cid);
        const tid = matchTagTopic(t); if (tid) coveredTopics.add(tid);
      }
      cc.forEach((cid) => covered.add(cid));
      if (r !== null && r !== undefined) {
        rValues.push(r);
        cc.forEach((cid) => { (conceptR[cid] = conceptR[cid] || []).push(r); });
      }
    }
    // Some decks (e.g. Pankow P/S subdecks) encode the topic in the DECK PATH, not in
    // card tags. The host passes those deck names (that have cards) in raw.deck_names;
    // match each via the exact deck_topic_map, mirroring collect.gather's deck_topic
    // loop, so their topics count toward coverage too.
    for (const name of (raw.deck_names || [])) {
      if (!name) continue;
      const j = tokensOf(name).join('_');
      if (j in deckTopicMap) coveredTopics.add(deckTopicMap[j]);
    }
    const coverage = weightedCoverage(covered);
    // Depth-aware coverage for DISPLAY (the header "% of the exam covered"), matching
    // desktop collect.gather's topic_coverage. `covered` is left untouched, so the
    // category-level coverage that gates memory/performance/readiness is unchanged.
    const topicCoverage = topicWeightedCoverage(coveredTopics, covered);
    const nReviews = raw.n_reviews || 0;

    // per-section recall (mean retrievability), used as the calibration predictor
    const sectionR = { chem_phys: [], bio_biochem: [], psych_soc: [] };
    for (const cid in conceptR) {
      const c = byId[cid.toLowerCase()];
      if (c && sectionR[c.section]) sectionR[c.section].push.apply(sectionR[c.section], conceptR[cid]);
    }
    const sectionRecall = {};
    for (const s in sectionR) if (sectionR[s].length) sectionRecall[s] = sectionR[s].reduce((a, b) => a + b, 0) / sectionR[s].length;

    // application outcomes: prefer the full array (section + correct), else the aggregate
    const outcomes = raw.perf_outcomes || [];
    const perfN = outcomes.length ? outcomes.length : (raw.perf && raw.perf.n) || 0;
    const perfK = outcomes.length ? outcomes.filter((o) => o.correct).length : (raw.perf && raw.perf.k) || 0;
    const calibPairs = [];
    for (const o of outcomes) if (o.section in sectionRecall) calibPairs.push([sectionRecall[o.section], o.correct ? 1 : 0]);

    // per science-section application outcomes (1/0), for readiness + the paraphrase test
    const sectionOutcomes = { chem_phys: [], bio_biochem: [], psych_soc: [] };
    for (const o of outcomes) if (o.section in sectionOutcomes) sectionOutcomes[o.section].push(o.correct ? 1 : 0);
    // Display-only twin that ALSO includes cars, so the CARS section card can show
    // its reasoning accuracy. Feeds NO score (sectionOutcomes above still drives
    // readiness / the paraphrase test); mirrors collect.gather's section_reason.
    const sectionReason = { chem_phys: [], bio_biochem: [], psych_soc: [], cars: [] };
    for (const o of outcomes) if (o.section in sectionReason) sectionReason[o.section].push(o.correct ? 1 : 0);
    // The readiness give-up gate counts SCIENCE-section outcomes only (CARS is never
    // modeled), matching collect.gather's total_outcomes / total_items. Performance
    // and study pace still use every outcome (perfN) as on desktop.
    let scienceTotal = 0;
    for (const s of ['chem_phys', 'bio_biochem', 'psych_soc']) scienceTotal += (sectionOutcomes[s] || []).length;

    // Readiness. The classic ability->scale projection is the honest fallback; the
    // 2PL IRT latent-ability path is the desktop default. IRT overrides the classic
    // result only when the flag is on AND it clears every honesty gate (give-up,
    // min items, per-section test information) -- exactly like collect.gather.
    let readinessOut = readinessScore(outcomes, sectionRecall, coverage, nReviews, scienceTotal);
    if (CFG.readiness_use_irt) {
      const sectionItems = { chem_phys: [], bio_biochem: [], psych_soc: [], cars: [] };
      for (const o of outcomes) {
        if (!(o.section in sectionItems)) continue;
        // difficulty/discrimination come from item metadata when present, else the
        // fixed 2PL prior -- matching collect.gather's IrtItem construction.
        const b = asFloat(o.difficulty);
        const a = asFloat(o.discrimination);
        sectionItems[o.section].push({
          correct: o.correct ? 1 : 0,
          b: b === null ? CFG.irt_default_difficulty : b,
          a: a === null ? CFG.irt_default_discrimination : a,
        });
      }
      const irt = irtReadiness(sectionItems, coverage, nReviews, scienceTotal);
      if (!irt.abstained) readinessOut = irt;
    }

    // Per-concept paraphrase test (the "fluency illusion" list): application outcomes
    // carry the linked concept (from the reasoning card's concept tag); recall is the
    // mean retrievability of that concept's studied cards. Mirrors collect.gather.
    const conceptApp = {};
    for (const o of outcomes) {
      const cid = o.concept;
      if (typeof cid === 'string' && cid) (conceptApp[cid] = conceptApp[cid] || []).push(o.correct ? 1 : 0);
    }
    const conceptRecallMean = {};
    for (const cid in conceptR) { const rs = conceptR[cid]; if (rs && rs.length) conceptRecallMean[cid] = rs.reduce((a, b) => a + b, 0) / rs.length; }
    const conceptSection = {};
    new Set(Object.keys(conceptRecallMean).concat(Object.keys(conceptApp))).forEach((cid) => {
      const c = byId[cid.toLowerCase()];
      if (c) conceptSection[cid] = c.section;
    });
    const fluencyItems = conceptTransferGaps(conceptRecallMean, conceptApp, conceptSection);
    const transfer = transferGap(sectionRecall, sectionOutcomes);

    const nextTops = nextTopics(covered, conceptR, 6);

    // Concepts not yet exam-ready (uncovered or recall below the content line):
    // real breadth left, drives the daily reasoning goal.
    let conceptsToPractice = 0;
    for (const c of OUTLINE.concepts) {
      const rs = conceptR[c.id] || [];
      const recall = rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 0;
      if (recall < CFG.content_ready_recall) conceptsToPractice += 1;
    }

    // Score trajectory: fold today's readiness into the dated snapshot history and
    // project it to exam day, mirroring collect.gather's HISTORY_CONFIG_KEY logic.
    // The host provides the stored history (raw.readiness_history), the target
    // (raw.target), and the exam date (raw.exam_date); it persists the returned
    // readiness_history_persist array back to config when it is non-null.
    const SCI = ['chem_phys', 'bio_biochem', 'psych_soc'];
    // weakest modeled section (min point), mirrors collect.gather's `weakest`.
    let weakestReady = null, weakestReadyPt = Infinity;
    if (!readinessOut.abstained && readinessOut.sections) {
      for (const s in readinessOut.sections) {
        const p = readinessOut.sections[s].point;
        if (p < weakestReadyPt) { weakestReadyPt = p; weakestReady = s; }
      }
    }
    // Only a LIVE, full 3-section composite is comparable day to day; a partial or
    // abstained readiness is never recorded (and never feeds the projection).
    const modeledSections = (!readinessOut.abstained && readinessOut.sections) ? Object.keys(readinessOut.sections) : [];
    // Full composite = live and covering at least all three science sections (CARS
    // optional). n_modeled tags the scale so a 3->4 section jump (once CARS is
    // scored) restarts the trend instead of mixing two scales.
    const isFullComposite = !readinessOut.abstained &&
      readinessOut.point !== undefined && readinessOut.point !== null &&
      SCI.every((s) => modeledSections.includes(s));
    const nModeled = modeledSections.length;

    // Stored history is user-writable and synced, so keep only well-formed
    // { d: <iso str>, point: <number> } points -- exactly collect.gather's guard.
    let history = [];
    if (Array.isArray(raw.readiness_history)) {
      for (const h of raw.readiness_history) {
        if (h && typeof h === 'object') {
          const d = h.d, point = asFloat(h.point);
          if (typeof d === 'string' && d && point !== null) {
            const nPt = (typeof h.n === 'number') ? Math.trunc(h.n) : 3;
            history.push({ d, point, n: nPt });
          }
        }
      }
    }
    const todayIso = raw.today || '';
    // Record today's point at most once per day and only when it is new or has
    // moved, so a routine refresh doesn't rewrite the collection (collect.gather).
    // readiness_history_persist is non-null ONLY when the host should write it back.
    let readinessHistoryPersist = null;
    if (isFullComposite && todayIso) {
      const point = round1(readinessOut.point);
      const existing = history.find((h) => h.d === todayIso);
      if (!existing || existing.point !== point || existing.n !== nModeled) {
        history = history.filter((h) => h.d !== todayIso);
        history.push({ d: todayIso, point, n: nModeled });
        readinessHistoryPersist = history;
      }
    }
    // Only project while readiness is a live full composite; otherwise abstain
    // rather than projecting from a stale snapshot (collect.gather's traj_history).
    // Feed only same-scale snapshots so adding CARS restarts the trend cleanly.
    const trajHistory = isFullComposite ? history.filter((h) => ((typeof h.n === 'number') ? h.n : 3) === nModeled) : [];
    const rawTarget = asFloat(raw.target);
    const targetScore = rawTarget ? Math.trunc(rawTarget) : null;
    // days to exam = exam ordinal - today ordinal, matching collect.gather's
    // (date.fromisoformat(exam) - date.fromisoformat(today)).days (may be negative).
    let daysToExam = null;
    if (typeof raw.exam_date === 'string' && raw.exam_date) {
      const eo = isoToOrdinal(raw.exam_date), to = isoToOrdinal(todayIso);
      if (Number.isFinite(eo) && Number.isFinite(to)) daysToExam = eo - to;
    }
    const trajectoryOut = trajectory(trajHistory, targetScore, daysToExam, weakestReady, nModeled || 3);

    // Exam-countdown-aware DEFAULT reasoning split, mirroring collect.gather: same
    // AAMC section weights, the same depth-aware coverage the dashboard shows, and
    // the same days-to-exam as the trajectory. Attached to study_pace so the mobile
    // payload shape matches desktop; a manual choice is never seen here.
    const sp = studyPace(raw, perfN, conceptsToPractice, rValues.length, raw.reasoning_today || 0);
    const sectionWeight = {};
    for (const s in OUTLINE.sections) {
      let sw = 0;
      for (const c of OUTLINE.concepts) if (c.section === s) sw += c.weight;
      sectionWeight[s] = sw;
    }
    sp.reasoning_focus = reasoningFocus(
      sp.reasoning_per_day || 0, sectionWeight, topicCoverageBySection(coveredTopics, covered), daysToExam,
    );

    return {
      coverage,
      coverage_by_section: coverageBySection(covered),
      topic_coverage: topicCoverage,
      topic_coverage_by_section: topicCoverageBySection(coveredTopics, covered),
      outline_version: OUTLINE.version,
      n_reviews: nReviews,
      n_cards_seen: rValues.length,
      ai_used: false,
      updated: raw.updated || nowStamp(),
      // Carried straight through from the host (col.ls, ms). Not a scoring number;
      // the shared masthead renders it as "Synced Xm ago" / "Never synced".
      last_sync_ms: (typeof raw.last_sync_ms === 'number' ? raw.last_sync_ms : 0),
      best_next: nextTops[0] || null,
      next_topics: nextTops,
      book_set: raw.book_set || 'kaplan',
      section_labels: OUTLINE.sections,
      // Per-section auto Mixed/Blocked status for the study launcher's read-only
      // label. Counts (c.ivl/c.queue) come from the host; the decision is the shared
      // sectionShouldMix port, so the label matches what the reviewer will do.
      section_maturity: Object.keys(raw.section_maturity || {}).reduce((acc, sec) => {
        const c = (raw.section_maturity || {})[sec] || {};
        const mature = c.mature || 0;
        const review = c.review || 0;
        const dec = sectionShouldMix(mature, review);
        acc[sec] = { mixed: dec.mixed, reason: dec.reason, mature, review };
        return acc;
      }, {}),
      thresholds: { memory_cards: CFG.min_cards_memory, performance_outcomes: CFG.min_outcomes_performance, reviews: CFG.giveup_min_reviews, coverage: CFG.giveup_min_coverage, readiness_per_section: CFG.min_outcomes_readiness },
      memory: memoryScore(rValues),
      performance: performanceScore({ n: perfN, k: perfK }),
      readiness: readinessOut,
      calibration: calibration(calibPairs),
      // reasoning_today (today's practice progress) is surfaced on desktop's practice
      // screen; the mobile app has no practice screen, so it stays 0 unless the host
      // provides raw.reasoning_today (kept for output-shape parity with desktop).
      study_pace: sp,
      confidence: confidenceCalibration(outcomes),
      mistakes: mistakeTaxonomy(outcomes),
      skills: skillTaxonomy(outcomes),
      study_plan: studyPlanJS(covered, conceptR),
      pacing: pacingCoach(outcomes),
      trajectory: trajectoryOut,
      // The full updated readiness-snapshot history for the host to persist to
      // HISTORY_CONFIG_KEY, or null when nothing changed (see collect.gather). The
      // renderer ignores this; only the AnkiDroid bridge reads it.
      readiness_history_persist: readinessHistoryPersist,
      // per-concept and per-section paraphrase test (the fluency illusion), matching
      // collect.gather's fluency_items / transfer so the mobile data equals desktop.
      fluency_items: fluencyItems,
      transfer,
      // Per science-section application outcomes (1/0), the twin of collect.gather's
      // section_outcomes. Read-only pass-through for the weak-spot quick jump; the
      // selection and give-up gate live in the shared dashboard.js.
      section_outcomes: sectionOutcomes,
      // Display-only twin that includes cars (see sectionReason above), so the CARS
      // card can show its accuracy; feeds no score. Read by dashboard.js.
      section_reason: sectionReason,
      // Per science-section mean FSRS recall R (0..1), the twin of collect.gather's
      // section_recall. Read-only pass-through so the Practice tab's per-section
      // Flashcards bar shows real recall; feeds no score. round3 to match desktop.
      section_recall: Object.keys(sectionRecall).reduce((acc, s) => { acc[s] = round3(sectionRecall[s]); return acc; }, {}),
      // What the student flagged to revisit, injected by the host bridge (native
      // flag column). Flashcard count + flagged reasoning questions to re-serve.
      flagged: { card_count: raw.flagged_card_count || 0, reasoning: raw.flagged_reasoning || [] },
    };
  };

  // Verification hook (inert; the dashboard never reads it). Exposes the pure
  // scoring ports so a parity harness can drive them with the SAME inputs as the
  // Python core (anki.vantage.scoring) and assert bit-for-bit-to-rounding equality
  // -- the desktop/mobile parity mandate. Kept read-only, like window.__vantageRender.
  window.__vantageScoring = {
    CFG, invNormCdf, irtProb, irtInformation, irtEstimate, thetaToScale,
    irtReadiness, conceptTransferGaps, transferGap, mapAbilityToScale,
    trajectory, isoToOrdinal, mistakeTaxonomy, skillTaxonomy, pacingCoach, carsPacing,
    reasoningFocus, resolveFocusSection, largestRemainder, sectionShouldMix,
  };
})();
