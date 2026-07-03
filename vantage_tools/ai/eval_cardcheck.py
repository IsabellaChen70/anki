#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Evaluate the AI card-check safety gate (Challenge 7f / spec-ai-cardgen.md sec 5).

Pipeline for the 50 candidate cards produced offline from the ONE chapter source
(`chapter_cardgen.py`, LLM OFF):

    generate 50 cards  ->  grounding checker (cutoff 0.5)  ->  three-way quality
    gate  ->  PUBLISH only correct_useful, BLOCK wrong + correct_but_bad_teaching

and reports, with REAL numbers:

  1. the THREE COUNTS the gate assigns: correct_useful / wrong / correct_but_bad_teaching.
  2. how many cards were blocked (wrong + bad_teaching) vs published.
  3. the GATE's ACCURACY against the generator's KNOWN intended labels
     (self-validation, a confusion count) -- reported honestly, including any
     card the gate labels differently from its intended verdict.
  4. traceability: every PUBLISHED card resolves to a real SourceRef span.

Honesty-first: the generator is deterministic with DESIGNED error modes (LLM off),
so these counts validate the SAFETY GATE -- does it catch wrong + bad cards and
block them -- not a specific vendor's card quality. Any misclassification is
printed, not hidden. The safety invariant that must hold: no card the gate
publishes is actually a wrong (unsupported) card.

PRE-REGISTERED (before scoring; see quality.py / checker.py):
    grounding coverage cutoff  = 0.5
    min answer content tokens  = 3
    duplicate trigram Jaccard  = 0.85

Re-run (deterministic):  out/pyenv/bin/python vantage_tools/ai/eval_cardcheck.py
Writes vantage_tools/ai/cardcheck_results.json ; exit 0 = safe (no wrong card
published, all published cards traceable), 1 otherwise.
"""

from __future__ import annotations

import json
import os

from chapter_cardgen import CHAPTER_SOURCE, DEFAULT_SEED, generate, intended_counts
from checker import COVERAGE_CUTOFF, GroundingChecker
from quality import (
    BAD_TEACHING,
    CORRECT_USEFUL,
    DUP_THRESHOLD,
    GROUNDING_CUTOFF,
    MIN_ANSWER_CONTENT_TOKENS,
    WRONG,
    QualityChecker,
)
from sources import load_corpus

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "cardcheck_results.json")

_VERDICTS = (CORRECT_USEFUL, WRONG, BAD_TEACHING)


def run(seed: int = DEFAULT_SEED) -> dict:
    corpus = load_corpus()
    checker = GroundingChecker(cutoff=COVERAGE_CUTOFF)
    gate = QualityChecker()
    cards = generate(seed=seed, corpus=corpus)

    accepted_answers: list[str] = []
    verdict_counts = {v: 0 for v in _VERDICTS}
    confusion: dict[str, dict[str, int]] = {
        v: {w: 0 for w in _VERDICTS} for v in _VERDICTS
    }
    rows: list[dict] = []
    published: list[dict] = []
    misclassified: list[dict] = []
    wrong_published = 0
    bad_published = 0

    for card in cards:
        grounding = checker.check_ref(card.claim, card.source_ref, corpus)
        qr = gate.classify(card.stem, card.answer, grounding, accepted_answers)
        intended = card.provenance["intended"]
        verdict_counts[qr.verdict] += 1
        confusion[intended][qr.verdict] += 1

        row = {
            "card_id": card.provenance["card_id"],
            "locator": card.source_ref.locator(),
            "intended": intended,
            "gate_verdict": qr.verdict,
            "reason": qr.reason,
            "coverage": round(grounding.coverage, 3),
            "answer_content_tokens": qr.answer_content_tokens,
            "max_dup_jaccard": qr.max_dup_jaccard,
            "match": qr.verdict == intended,
        }
        rows.append(row)
        if qr.verdict != intended:
            misclassified.append(row)

        if qr.published:
            published.append(
                {
                    "card_id": card.provenance["card_id"],
                    "locator": card.source_ref.locator(),
                    "citation": card.provenance["citation"],
                    "resolved": corpus.resolve(card.source_ref),
                    "answer": card.answer,
                }
            )
            accepted_answers.append(card.answer)
            if intended == WRONG:
                wrong_published += 1
            elif intended == BAD_TEACHING:
                bad_published += 1

    n = len(cards)
    gate_accuracy = sum(1 for r in rows if r["match"]) / n if n else 0.0
    blocked = verdict_counts[WRONG] + verdict_counts[BAD_TEACHING]

    # traceability: every published card must resolve to real span text.
    untraceable = [p for p in published if not p["resolved"].strip()]
    all_traceable = not untraceable

    # safety invariant: no genuinely-wrong card slipped through as published.
    safe = (wrong_published == 0) and all_traceable

    return {
        "seed": seed,
        "source": CHAPTER_SOURCE,
        "n_cards": n,
        "cutoff": COVERAGE_CUTOFF,
        "thresholds": {
            "grounding_cutoff": GROUNDING_CUTOFF,
            "min_answer_content_tokens": MIN_ANSWER_CONTENT_TOKENS,
            "duplicate_trigram_jaccard": DUP_THRESHOLD,
        },
        "intended_counts": intended_counts(),
        "gate_verdict_counts": verdict_counts,
        "published": len(published),
        "blocked": blocked,
        "gate_accuracy": gate_accuracy,
        "confusion": confusion,
        "misclassified": misclassified,
        "wrong_published": wrong_published,
        "bad_teaching_published": bad_published,
        "all_published_traceable": all_traceable,
        "untraceable_published": untraceable,
        "safe": safe,
        "rows": rows,
        "published_cards": published,
        "deterministic": True,
        "llm_off": True,
    }


def _print_report(res: dict) -> None:
    bar = "=" * 74
    print(bar)
    print("AI CARD-CHECK: three-way safety gate over 50 generated cards")
    print(bar)
    print(
        f"source: {res['source']}   seed: {res['seed']}   cards: {res['n_cards']}   "
        f"(deterministic, LLM OFF)"
    )
    t = res["thresholds"]
    print(
        f"pre-registered: grounding_cutoff={t['grounding_cutoff']}  "
        f"min_answer_content_tokens={t['min_answer_content_tokens']}  "
        f"duplicate_trigram_jaccard={t['duplicate_trigram_jaccard']}"
    )

    print("\n[1] THREE COUNTS (verdict the gate assigned):")
    vc = res["gate_verdict_counts"]
    for v in _VERDICTS:
        print(f"    {v:<26} {vc[v]}")

    print(
        f"\n[2] PUBLISHED (correct_useful only): {res['published']}"
        f"    BLOCKED (wrong + bad_teaching): {res['blocked']}"
    )

    print("\n[3] GATE ACCURACY vs the generator's KNOWN intended labels:")
    print(
        f"    accuracy: {sum(1 for r in res['rows'] if r['match'])}/{res['n_cards']} "
        f"= {res['gate_accuracy'] * 100:.1f}%"
    )
    print("    confusion (rows = intended, cols = gate verdict):")
    conf = res["confusion"]
    header = (
        "      "
        + f"{'intended \\ gate':<26}"
        + "".join(f"{v[:16]:>18}" for v in _VERDICTS)
    )
    print(header)
    for iv in _VERDICTS:
        print(f"      {iv:<26}" + "".join(f"{conf[iv][gv]:>18}" for gv in _VERDICTS))
    if res["misclassified"]:
        print(f"    MISCLASSIFIED ({len(res['misclassified'])}) -- reported honestly:")
        for m in res["misclassified"]:
            print(
                f"      {m['card_id']:<20} intended={m['intended']:<24} "
                f"gate={m['gate_verdict']:<24} reason={m['reason']} cov={m['coverage']}"
            )
    else:
        print("    MISCLASSIFIED: none (gate verdict matched intended on all 50)")

    print("\n[4] SAFETY + TRACEABILITY:")
    print(
        f"    wrong cards published (unsupported reaching a student): {res['wrong_published']}"
    )
    print(f"    bad-teaching cards published: {res['bad_teaching_published']}")
    print(
        f"    every published card resolves to a real SourceRef span: "
        f"{res['all_published_traceable']} "
        f"({res['published']}/{res['published']} traceable)"
    )

    print("\n" + "-" * 74)
    verdict = "SAFE" if res["safe"] else "UNSAFE"
    print(
        f"RESULT: gate BLOCKED {res['blocked']} of {res['n_cards']} cards; "
        f"no wrong card published, all published cards traceable -> {verdict}"
    )
    print("-" * 74)


def main() -> int:
    res = run()
    _print_report(res)

    artifact = {
        k: res[k]
        for k in (
            "seed",
            "source",
            "n_cards",
            "cutoff",
            "thresholds",
            "intended_counts",
            "gate_verdict_counts",
            "published",
            "blocked",
            "gate_accuracy",
            "confusion",
            "misclassified",
            "wrong_published",
            "bad_teaching_published",
            "all_published_traceable",
            "safe",
            "deterministic",
            "llm_off",
        )
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, os.path.dirname(HERE))}")
    return 0 if res["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
