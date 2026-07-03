#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage paraphrase test: does the transfer-gap (memory vs application) machinery
surface the fluency illusion per SECTION and per CONCEPT, and abstain when data is thin?

WHAT IS UNDER TEST
    The Vantage transfer-gap functions in anki.vantage.scoring, reused as-is (no
    reimplementation):
      * scoring.transfer_gap        -> per-SECTION memory-vs-application gap
      * scoring.concept_transfer_gaps -> per-CONCEPT (card-level) gap
    plus their gates in ScoringConfig (min_outcomes_transfer=10,
    min_outcomes_transfer_card=3, fluency_gap_threshold=0.15). This harness feeds
    those functions and checks they reproduce the pre-registered structure below.

PRE-REGISTERED (written before looking at any result)
    METRIC. memory -> performance gap = recall_on_card - accuracy_on_reworded_items,
    computed by the scoring functions as gap = recall - application, and reported
    BOTH per SECTION and per CONCEPT (so one weak concept is not hidden inside a
    healthy section average).
    FLAG RULE. A concept is "fluency-illusion flagged" iff
        gap >= fluency_gap_threshold (0.15)  AND  it has >= min_outcomes_transfer_card
        (3) reworded outcomes.
    Concepts with fewer than 3 reworded outcomes are ABSTAINED (never scored), never
    guessed at. This is exactly scoring.concept_transfer_gaps' own behavior; the
    harness only checks it holds.

    LEARNER MODEL (the seeded, documented cohort that generates outcomes; there is no
    real cohort, so this validates the harness + the gap formulas, NOT a real cohort):
      * Each concept has one latent mastery m, drawn deterministically per concept id
        from the SEED, uniform on [MASTERY_MIN, MASTERY_MAX] = [0.62, 0.96] (studied
        concepts, so recall is generally high and the illusion is visible when it
        exists).
      * recall_on_card ~ Bernoulli(m). We log N_RECALL (30..50) recall reviews per
        concept and pass their observed mean retrievability (k/n) as the recall
        signal, matching "mean FSRS retrievability over the concept's recall cards".
      * reworded accuracy ~ Bernoulli(clamp(m - transfer_penalty)). TRANSFER_PENALTY
        = 0.30 is the pre-registered CONSTANT magnitude of the fluency illusion (the
        memory -> application drop). A seeded FLUENCY_PRONE_RATE = 0.5 of concepts are
        "transfer-prone" and take this penalty; the rest transfer cleanly (penalty 0).
        This is what yields BOTH gapped concepts (prone: expected gap ~ 0.30, flagged)
        and non-gapped / null concepts (clean: expected gap ~ 0, not flagged). A
        single global constant with no per-concept switch cannot produce a genuine
        high-recall / high-application null, which is the null we most want to show.
      * ABSTENTION DEMO. THIN_COUNT = 2 concepts (chosen by a seeded sample over the
        sorted concept ids) are deliberately starved to THIN_ATTEMPTS = 2 reworded
        outcomes (< 3), so the harness must abstain on them. Their few outcomes still
        fold into their section pool, illustrating why per-concept reporting matters.

    EXPECTATIONS (pre-registered, checked after the run):
      1. Every flagged concept should be a transfer-prone one and vice versa, modulo
         a little Bernoulli noise near the boundary. We report the confusion of the
         harness flag against the ground-truth prone label as a self-validation.
      2. CARS never appears in the per-SECTION numbers: scoring.transfer_gap iterates
         only the 3 modeled science sections (SECTIONS), so the section report is a
         labeled 3-of-4 partial. CARS concepts DO appear in the per-CONCEPT diagnostic
         (concept_transfer_gaps includes every linked concept); they are labeled and
         kept separate, not folded into any section or composite.

    This is a SIMULATED cohort. The absolute numbers validate the pipeline and the
    gap formulas, not any real student population.

Usage:
    out/pyenv/bin/python vantage_tools/evaluate_paraphrase.py
    (writes vantage_tools/paraphrase_results.json and docs/results-paraphrase.md)
"""

from __future__ import annotations

import hashlib
import json
import os
import random

from anki.vantage import scoring
from anki.vantage.scoring import ScoringConfig, clamp

# --- pre-registered constants (fixed before running) ------------------------- #
SEED = 20260702
TRANSFER_PENALTY = 0.30  # constant fluency-illusion magnitude (memory -> application)
FLUENCY_PRONE_RATE = 0.5  # seeded fraction of concepts subject to the illusion
MASTERY_MIN, MASTERY_MAX = 0.62, 0.96
N_RECALL_MIN, N_RECALL_MAX = 30, 50  # recall-card reviews logged per concept
N_ATTEMPT_MIN, N_ATTEMPT_MAX = 30, 60  # reworded-item attempts logged per concept
THIN_COUNT = 2  # concepts deliberately starved of reworded attempts (abstention demo)
THIN_ATTEMPTS = 2  # below min_outcomes_transfer_card (3): the harness must abstain

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATASET_PATH = os.path.join(HERE, "paraphrase_items.json")
RESULTS_PATH = os.path.join(HERE, "paraphrase_results.json")
DOCS_PATH = os.path.join(REPO_ROOT, "docs", "results-paraphrase.md")

SECTION_ORDER = ["chem_phys", "bio_biochem", "psych_soc", "cars"]
SECTION_LABEL = {
    "chem_phys": "Chem/Phys",
    "bio_biochem": "Bio/Biochem",
    "psych_soc": "Psych/Soc",
    "cars": "CARS",
}


def _rng_for(concept_id: str) -> random.Random:
    """Per-concept RNG seeded from SEED + concept id via sha256, so outcomes are
    deterministic and independent of dataset order and of PYTHONHASHSEED."""
    h = hashlib.sha256(f"{SEED}:{concept_id}".encode()).hexdigest()
    return random.Random(int(h, 16))


def dataset_hash(concepts: list) -> str:
    canonical = json.dumps(concepts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def simulate(concepts: list, thin_ids: set) -> dict:
    """Run the seeded learner model. Returns per-concept simulated evidence."""
    sim: dict = {}
    for c in concepts:
        cid = c["concept_id"]
        rng = _rng_for(cid)
        mastery = rng.uniform(MASTERY_MIN, MASTERY_MAX)
        prone = rng.random() < FLUENCY_PRONE_RATE
        penalty = TRANSFER_PENALTY if prone else 0.0
        app_p = clamp(mastery - penalty, 0.0, 1.0)
        # recall_on_card ~ Bernoulli(mastery); recall signal = observed retrievability
        n_recall = rng.randint(N_RECALL_MIN, N_RECALL_MAX)
        recall_k = sum(1 for _ in range(n_recall) if rng.random() < mastery)
        # reworded accuracy ~ Bernoulli(clamp(mastery - penalty))
        n_att = THIN_ATTEMPTS if cid in thin_ids else rng.randint(
            N_ATTEMPT_MIN, N_ATTEMPT_MAX
        )
        app = [1 if rng.random() < app_p else 0 for _ in range(n_att)]
        sim[cid] = {
            "section": c["section"],
            "recall_k": recall_k,
            "recall_n": n_recall,
            "recall": recall_k / n_recall,
            "app": app,
            "mastery": round(mastery, 4),
            "fluency_prone": prone,
            "penalty": penalty,
            "app_p": round(app_p, 4),
        }
    return sim


def build_scoring_inputs(sim: dict):
    """Assemble exactly the inputs scoring.transfer_gap and
    scoring.concept_transfer_gaps expect."""
    concept_recall = {cid: s["recall"] for cid, s in sim.items()}
    concept_app = {cid: s["app"] for cid, s in sim.items()}
    concept_section = {cid: s["section"] for cid, s in sim.items()}

    # section recall = pooled observed retrievability; section app = pooled outcomes
    rec_k: dict = {}
    rec_n: dict = {}
    sec_app: dict = {}
    for cid, s in sim.items():
        sec = s["section"]
        rec_k[sec] = rec_k.get(sec, 0) + s["recall_k"]
        rec_n[sec] = rec_n.get(sec, 0) + s["recall_n"]
        sec_app.setdefault(sec, []).extend(s["app"])
    section_recall = {sec: rec_k[sec] / rec_n[sec] for sec in rec_n}
    return concept_recall, concept_app, concept_section, section_recall, sec_app


def main() -> int:
    data = json.load(open(DATASET_PATH, encoding="utf-8"))
    concepts = data["concepts"]
    cfg = ScoringConfig()

    all_ids = sorted(c["concept_id"] for c in concepts)
    thin_ids = set(random.Random(SEED).sample(all_ids, THIN_COUNT))

    sim = simulate(concepts, thin_ids)
    (concept_recall, concept_app, concept_section,
     section_recall, section_app) = build_scoring_inputs(sim)

    # ---- reuse the shipped scoring functions (no reimplementation) ---------- #
    section_res = scoring.transfer_gap(section_recall, section_app, cfg)
    concept_res = scoring.concept_transfer_gaps(
        concept_recall, concept_app, concept_section, cfg
    )

    scored_ids = {t.concept_id for t in concept_res}
    abstained = [
        {
            "concept_id": cid,
            "section": sim[cid]["section"],
            "n_app": len(sim[cid]["app"]),
            "reason": (
                f"only {len(sim[cid]['app'])} reworded outcomes "
                f"(need >= {cfg.min_outcomes_transfer_card})"
            ),
        }
        for cid in all_ids
        if cid not in scored_ids
    ]

    # per-concept rows augmented with ground truth (for the self-validation)
    concept_rows = []
    for t in concept_res:
        truth = sim[t.concept_id]["fluency_prone"]
        concept_rows.append(
            {
                "concept_id": t.concept_id,
                "section": t.section,
                "recall": t.recall,
                "application": t.application,
                "gap": t.gap,
                "n_app": t.n_app,
                "fluency_risk": t.fluency_risk,
                "ground_truth_prone": truth,
                "mastery": sim[t.concept_id]["mastery"],
                "correct_flag": (t.fluency_risk == truth),
            }
        )

    # confusion of the harness flag vs the ground-truth prone label (scored only)
    tp = sum(1 for r in concept_rows if r["ground_truth_prone"] and r["fluency_risk"])
    fp = sum(
        1 for r in concept_rows if not r["ground_truth_prone"] and r["fluency_risk"]
    )
    fn = sum(
        1 for r in concept_rows if r["ground_truth_prone"] and not r["fluency_risk"]
    )
    tn = sum(
        1
        for r in concept_rows
        if not r["ground_truth_prone"] and not r["fluency_risk"]
    )
    n_scored = len(concept_rows)
    accuracy = (tp + tn) / n_scored if n_scored else 0.0

    flagged = [r["concept_id"] for r in concept_rows if r["fluency_risk"]]
    nulls = [r["concept_id"] for r in concept_rows if not r["fluency_risk"]]

    # "weak concept hidden in a healthy section": a science section NOT flagged at the
    # section level that nonetheless contains a flagged concept.
    hidden = []
    for sec, st in section_res.items():
        if not st.fluency_risk:
            inside = [
                r["concept_id"]
                for r in concept_rows
                if r["section"] == sec and r["fluency_risk"]
            ]
            if inside:
                hidden.append({"section": sec, "flagged_concepts": inside})

    dhash = dataset_hash(concepts)

    out = {
        "meta": {
            "seed": SEED,
            "dataset_path": os.path.relpath(DATASET_PATH, REPO_ROOT),
            "dataset_hash_sha256": dhash,
            "n_concepts": len(concepts),
            "transfer_penalty": TRANSFER_PENALTY,
            "fluency_prone_rate": FLUENCY_PRONE_RATE,
            "mastery_range": [MASTERY_MIN, MASTERY_MAX],
            "n_recall_range": [N_RECALL_MIN, N_RECALL_MAX],
            "n_attempt_range": [N_ATTEMPT_MIN, N_ATTEMPT_MAX],
            "thin_concepts": sorted(thin_ids),
            "thin_attempts": THIN_ATTEMPTS,
            "thresholds": {
                "min_outcomes_transfer": cfg.min_outcomes_transfer,
                "min_outcomes_transfer_card": cfg.min_outcomes_transfer_card,
                "fluency_gap_threshold": cfg.fluency_gap_threshold,
            },
            "cohort": (
                "simulated; validates the harness + gap formulas, not a real cohort"
            ),
        },
        "sections": {
            sec: {
                "label": SECTION_LABEL[sec],
                "recall": st.recall,
                "application": st.application,
                "gap": st.gap,
                "n_app": st.n_app,
                "fluency_risk": st.fluency_risk,
            }
            for sec, st in section_res.items()
        },
        "cars_section_excluded": "cars" not in section_res,
        "cars_note": (
            "scoring.transfer_gap models only the 3 science sections (SECTIONS), so "
            "CARS is never in the per-section numbers. CARS concepts still appear in "
            "the per-concept diagnostic below, labeled and separate."
        ),
        "concepts": concept_rows,
        "abstained_concepts": abstained,
        "summary": {
            "n_scored": n_scored,
            "n_flagged": len(flagged),
            "n_null": len(nulls),
            "n_abstained": len(abstained),
            "flagged_concepts": flagged,
            "null_concepts": nulls,
            "hidden_weak_concepts": hidden,
        },
        "validation": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "accuracy": round(accuracy, 4),
            "note": (
                "harness fluency_risk flag vs the seeded ground-truth transfer-prone "
                "label, over scored (non-abstained) concepts. Off-diagonal cells are "
                "Bernoulli noise near the 0.15 boundary."
            ),
        },
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")

    docs = build_docs(out)
    with open(DOCS_PATH, "w", encoding="utf-8") as fh:
        fh.write(docs)

    print_report(out)
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, REPO_ROOT)}")
    print(f"wrote {os.path.relpath(DOCS_PATH, REPO_ROOT)}")
    return 0


def print_report(out: dict) -> None:
    m = out["meta"]
    print(
        "Vantage paraphrase test: transfer gap (memory vs application), "
        "per section and per concept"
    )
    print(
        f"seed={m['seed']}  concepts={m['n_concepts']}  "
        f"transfer_penalty={m['transfer_penalty']}  "
        f"fluency_prone_rate={m['fluency_prone_rate']}"
    )
    print(f"dataset sha256={m['dataset_hash_sha256'][:16]}...")
    print(
        "cohort: SIMULATED (seeded learner model); validates the harness + gap "
        "formulas, not a real cohort\n"
    )

    print("PER-SECTION transfer gap (scoring.transfer_gap; 3 modeled science sections)")
    print(
        f"  {'section':<14}{'recall':>8}{'applied':>9}{'gap':>8}{'n_app':>7}"
        f"{'flag':>7}"
    )
    for sec in SECTION_ORDER:
        s = out["sections"].get(sec)
        if s is None:
            print(f"  {SECTION_LABEL[sec]:<14}{'excluded (CARS not modeled)':>40}")
            continue
        flag = "FLUENCY" if s["fluency_risk"] else "-"
        print(
            f"  {s['label']:<14}{s['recall']:>8.3f}{s['application']:>9.3f}"
            f"{s['gap']:>8.3f}{s['n_app']:>7d}{flag:>7}"
        )

    print(
        "\nPER-CONCEPT transfer gap (scoring.concept_transfer_gaps; worst gap first)"
    )
    print(
        f"  {'concept':<26}{'sec':<12}{'recall':>7}{'appl':>7}{'gap':>7}"
        f"{'n':>4}  flag  truth"
    )
    for r in out["concepts"]:
        flag = "FLAG" if r["fluency_risk"] else " -  "
        truth = "prone" if r["ground_truth_prone"] else "clean"
        mark = "" if r["correct_flag"] else "  <-- disagrees with truth"
        print(
            f"  {r['concept_id']:<26}{r['section']:<12}{r['recall']:>7.3f}"
            f"{r['application']:>7.3f}{r['gap']:>7.3f}{r['n_app']:>4d}  {flag}  "
            f"{truth}{mark}"
        )

    ab = out["abstained_concepts"]
    print(f"\nABSTAINED concepts ({len(ab)}; below min_outcomes_transfer_card=3):")
    if ab:
        for a in ab:
            print(f"  {a['concept_id']:<26}{a['section']:<12}n_app={a['n_app']}  {a['reason']}")
    else:
        print("  none")

    s = out["summary"]
    print(
        f"\nsummary: scored={s['n_scored']}  flagged={s['n_flagged']}  "
        f"null(no gap)={s['n_null']}  abstained={s['n_abstained']}"
    )
    print(f"  null (no-gap) concepts: {', '.join(s['null_concepts']) or 'none'}")
    if s["hidden_weak_concepts"]:
        for h in s["hidden_weak_concepts"]:
            print(
                f"  per-concept caught what per-section hid: {SECTION_LABEL[h['section']]}"
                f" section not flagged, but flagged concept(s): "
                f"{', '.join(h['flagged_concepts'])}"
            )
    else:
        print("  per-concept vs per-section: no hidden-weak-concept case this run")

    v = out["validation"]
    print(
        f"\nself-validation (flag vs seeded ground truth, scored only): "
        f"TP={v['tp']} FP={v['fp']} FN={v['fn']} TN={v['tn']}  "
        f"accuracy={v['accuracy']:.3f}"
    )


def build_docs(out: dict) -> str:
    m = out["meta"]
    s = out["summary"]
    v = out["validation"]
    lines = []
    lines.append("# Paraphrase test results (transfer gap: memory vs application)\n")
    lines.append(
        "Reproducible check that the Vantage transfer-gap functions surface the "
        "fluency illusion per section and per concept, and abstain when data is thin. "
        "Generated by `vantage_tools/evaluate_paraphrase.py`; re-running reproduces "
        "these numbers exactly.\n"
    )
    lines.append("## What is under test\n")
    lines.append(
        "- `scoring.transfer_gap` (per section) and `scoring.concept_transfer_gaps` "
        "(per concept), reused as shipped, with gates from `ScoringConfig` "
        f"(min_outcomes_transfer={m['thresholds']['min_outcomes_transfer']}, "
        f"min_outcomes_transfer_card={m['thresholds']['min_outcomes_transfer_card']}, "
        f"fluency_gap_threshold={m['thresholds']['fluency_gap_threshold']}).\n"
    )
    lines.append("## Pre-registration (metric + learner model)\n")
    lines.append(
        "- Metric: gap = recall_on_card - accuracy_on_reworded_items, reported per "
        "SECTION and per CONCEPT.\n"
        "- Flag rule: a concept is fluency-illusion flagged iff gap >= "
        f"{m['thresholds']['fluency_gap_threshold']} with >= "
        f"{m['thresholds']['min_outcomes_transfer_card']} reworded outcomes; fewer "
        "outcomes means abstain.\n"
        f"- Learner model (seeded, SEED={m['seed']}): per concept a latent mastery m "
        f"in {m['mastery_range']}; recall ~ Bernoulli(m) over "
        f"{m['n_recall_range']} reviews; reworded accuracy ~ "
        f"Bernoulli(clamp(m - transfer_penalty)) over {m['n_attempt_range']} attempts. "
        f"transfer_penalty = {m['transfer_penalty']} (constant illusion magnitude) is "
        f"applied to a seeded {m['fluency_prone_rate']:.0%} of concepts (transfer-prone); "
        "the rest transfer cleanly (penalty 0), producing both gapped and null "
        f"concepts. {m['thin_concepts']} are starved to {m['thin_attempts']} outcomes "
        "to force the abstention path.\n"
    )
    lines.append(
        "> This is a SIMULATED cohort. The numbers validate the pipeline and the gap "
        "formulas, not a real student population.\n"
    )
    lines.append("## Headline\n")
    lines.append(
        f"- {s['n_scored']} concepts scored, {s['n_flagged']} flagged for the fluency "
        f"illusion, {s['n_null']} null (no gap), {s['n_abstained']} abstained "
        "(insufficient data).\n"
        f"- Self-validation vs the seeded ground truth (scored concepts): TP={v['tp']}, "
        f"FP={v['fp']}, FN={v['fn']}, TN={v['tn']}, accuracy={v['accuracy']:.3f}.\n"
    )
    if s["hidden_weak_concepts"]:
        for h in s["hidden_weak_concepts"]:
            lines.append(
                f"- Per-concept caught what the section average hid: the "
                f"{SECTION_LABEL[h['section']]} section is not flagged, yet it contains "
                f"flagged concept(s): {', '.join(h['flagged_concepts'])}.\n"
            )
    lines.append("\n## Per-section transfer gap (3 modeled science sections)\n")
    lines.append("| section | recall | application | gap | n_app | flag |")
    lines.append("| --- | ---: | ---: | ---: | ---: | :---: |")
    for sec in SECTION_ORDER:
        row = out["sections"].get(sec)
        if row is None:
            lines.append(
                f"| {SECTION_LABEL[sec]} | - | - | - | - | excluded (CARS not modeled) |"
            )
            continue
        flag = "FLUENCY" if row["fluency_risk"] else "-"
        lines.append(
            f"| {row['label']} | {row['recall']:.3f} | {row['application']:.3f} | "
            f"{row['gap']:.3f} | {row['n_app']} | {flag} |"
        )
    lines.append(
        "\nCARS is structurally excluded here (scoring.transfer_gap iterates only the "
        "3 science sections), so this is a labeled 3-of-4 partial.\n"
    )
    lines.append("## Per-concept transfer gap (worst gap first)\n")
    lines.append("| concept | section | recall | application | gap | n_app | flag | truth |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | :---: | :---: |")
    for r in out["concepts"]:
        flag = "FLAG" if r["fluency_risk"] else "-"
        truth = "prone" if r["ground_truth_prone"] else "clean"
        lines.append(
            f"| {r['concept_id']} | {r['section']} | {r['recall']:.3f} | "
            f"{r['application']:.3f} | {r['gap']:.3f} | {r['n_app']} | {flag} | {truth} |"
        )
    lines.append("\n## Abstained concepts (insufficient reworded outcomes)\n")
    if out["abstained_concepts"]:
        lines.append("| concept | section | n_app | reason |")
        lines.append("| --- | --- | ---: | --- |")
        for a in out["abstained_concepts"]:
            lines.append(
                f"| {a['concept_id']} | {a['section']} | {a['n_app']} | {a['reason']} |"
            )
    else:
        lines.append("None.")
    lines.append("\n## Reproduce\n")
    lines.append("```\nout/pyenv/bin/python vantage_tools/evaluate_paraphrase.py\n```\n")
    lines.append(
        f"Dataset: `{m['dataset_path']}` (sha256 `{m['dataset_hash_sha256']}`). "
        f"Seed {m['seed']}. Deterministic.\n"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
