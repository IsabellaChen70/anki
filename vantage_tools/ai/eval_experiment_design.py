#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Gate check for the NEW experiment-design (SIRS 'research') reasoning questions.

The science reasoning banks previously had zero items testing the AAMC skill
"reasoning about the design and execution of research". A small batch was authored
(one passage per science section). Before those items are trusted in the live bank
they must clear the SAME gate the AI card layer uses:

  1. GROUNDING (checker.py): each item's claim (its `explain`) must trace to a
     cited source span in corpus.json at the pre-registered coverage cutoff (0.5),
     with no negation or numeric contradiction.
  2. QUALITY (quality.py): grounded AND useful (specific, non-circular,
     non-duplicate) -> the three-way verdict must be `correct_useful`.

Every item also names an OpenStax-cited source (see corpus.json citations). This is
deterministic and offline (no LLM, no network). Re-run:

    out/pyenv/bin/python vantage_tools/ai/eval_experiment_design.py
"""

from __future__ import annotations

import json
import os

from checker import COVERAGE_CUTOFF, GroundingChecker
from quality import CORRECT_USEFUL, QualityChecker
from sources import SourceRef, load_corpus

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.path.join(HERE, "experiment_design_items.json")
RESULTS_PATH = os.path.join(HERE, "experiment_design_results.json")


def load_items() -> list[dict]:
    with open(ITEMS_PATH, encoding="utf-8") as fh:
        return json.load(fh)["items"]


def main() -> int:
    corpus = load_corpus()
    checker = GroundingChecker()
    gate = QualityChecker()
    items = load_items()

    print("=" * 78)
    print("EXPERIMENT-DESIGN ITEMS: grounding + quality gate")
    print(f"(pre-registered grounding cutoff = {COVERAGE_CUTOFF}; verdict must be correct_useful)")
    print("=" * 78)

    accepted: list[str] = []
    published = 0
    rows = []
    for it in items:
        ref = SourceRef.from_dict(it["source_ref"])
        g = checker.check_ref(it["claim"], ref, corpus)
        q = gate.classify(it["stem"], it["claim"], g, accepted)
        ok = g.passed and q.verdict == CORRECT_USEFUL
        if ok:
            accepted.append(it["claim"])
            published += 1
        cite = corpus.citation_for(ref.source_id).split(".")[0]
        print(
            f"  {it['design_id']:<20} skill={it['skill']:<8} cov={g.coverage:.2f} "
            f"{g.verdict:<9} quality={q.verdict:<14} [{ref.locator()}]"
            f"{'' if ok else '  <- FAIL ' + str(g.reasons or q.reason)}"
        )
        rows.append({
            "design_id": it["design_id"], "bank": it["bank"], "concept": it["concept"],
            "skill": it["skill"], "coverage": round(g.coverage, 3),
            "grounding": g.verdict, "quality": q.verdict,
            "source": ref.locator(), "citation": corpus.citation_for(ref.source_id),
            "passed": ok,
        })

    total = len(items)
    all_pass = published == total
    print(
        f"\n  {published}/{total} items grounded AND useful (correct_useful); "
        f"0 published without a cited source."
    )
    print(f"  result: {'ALL ITEMS PASS THE GATE' if all_pass else 'ONE OR MORE ITEMS FAILED'}")

    artifact = {
        "cutoff": COVERAGE_CUTOFF,
        "n_items": total,
        "published": published,
        "all_pass": all_pass,
        "deterministic": True,
        "items": rows,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"  wrote {os.path.relpath(RESULTS_PATH, os.path.dirname(HERE))}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
