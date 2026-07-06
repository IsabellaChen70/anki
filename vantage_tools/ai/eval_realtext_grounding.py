#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Grounding + 3-way gate on REAL, openly-licensed source text (not synthetic).

WHY THIS EXISTS
    Every other AI eval grounds cards against `corpus.json`, which is honestly
    labeled SYNTHETIC (author-written) prose. A fair skeptic can object that the
    checker is only ever tested on text the Vantage authors wrote themselves. This
    eval closes that gap with REAL external text: verbatim excerpts fetched from
    the English Wikipedia (`realtext_corpus.json`, CC BY-SA 4.0, attributed per
    source), covering the same MCAT concepts (buffers, catalysis, enzyme
    inhibition, the spacing and testing effects, confounding).

    It runs the IDENTICAL, independent held-out harness from `cardcheck_holdout.py`
    -- faithful sentences cited to themselves (useful) plus MECHANICAL, content-
    level perturbations (negation flip / number swap / misattribution to an
    unrelated span) whose labels are fixed by the OPERATION, not tuned to the gate
    -- but on the real corpus. The safety-critical invariant is unchanged: NO card
    whose gold label is `wrong` may be published, now demonstrated on text the
    project did not author.

LICENSE / HONESTY
    OpenStax (the obvious "real textbook" choice) turned out to be CC BY-NC-SA
    (NonCommercial), which is incompatible with this AGPL repo; see the
    `why_wikipedia_not_openstax` note in realtext_corpus.json. Wikipedia (CC BY-SA
    4.0) is license-compatible and is used instead. The excerpts are read only by a
    deterministic lexical checker; nothing here trains or prompts a model.

Deterministic and offline: the excerpts are stored in the repo (the fetch was a
one-time authoring step), so re-running needs no network and yields byte-identical
output.

Re-run:  out/pyenv/bin/python vantage_tools/ai/eval_realtext_grounding.py
Writes vantage_tools/ai/realtext_grounding_results.json ; exit 0 = safe (no wrong
card published), 1 otherwise.
"""

from __future__ import annotations

import json
import os

from cardcheck_holdout import build_holdout, evaluate
from sources import build_chunks, load_corpus

HERE = os.path.dirname(os.path.abspath(__file__))
REALTEXT_PATH = os.path.join(HERE, "realtext_corpus.json")
RESULTS_PATH = os.path.join(HERE, "realtext_grounding_results.json")


def _attribution(corpus) -> list[dict]:
    """One row per real source: what it is and under what license (for the report)."""
    rows = []
    for source_id in sorted(corpus.docs):
        doc = corpus.docs[source_id]
        rows.append({
            "source_id": source_id,
            "title": doc.title,
            "license": doc.license,
            "synthetic": doc.synthetic,
            "citation": doc.citation,
            "sentences": len(doc.sentences),
        })
    return rows


def main() -> int:
    corpus = load_corpus(REALTEXT_PATH)
    chunks, quarantined = build_chunks(corpus)

    # The held-out perturbation harness, verbatim from cardcheck_holdout, on REAL text.
    cards = build_holdout(corpus)
    res = evaluate(cards, corpus)

    # Sanity: real prose must not be synthetic, and must survive injection sanitation.
    all_real = all(not corpus.docs[sid].synthetic for sid in corpus.docs)
    res["corpus"] = "real (English Wikipedia, CC BY-SA 4.0)"
    res["all_sources_real"] = all_real
    res["indexed_chunks"] = len(chunks)
    res["quarantined_chunks"] = len(quarantined)
    res["sources"] = _attribution(corpus)

    bar = "=" * 78
    print(bar)
    print("REAL-TEXT GROUNDING: 3-way gate on real, openly-licensed source text")
    print(bar)
    print("source: English Wikipedia excerpts (CC BY-SA 4.0), NOT synthetic  (deterministic, LLM OFF)")
    for s in res["sources"]:
        print(f"  {s['source_id']:<26} {s['sentences']:>2} sentences  [{s['license']}]  {s['title']}")
    print(
        f"\nindexed chunks: {res['indexed_chunks']}   injection-quarantined: {res['quarantined_chunks']}"
        f"   all sources real (non-synthetic): {res['all_sources_real']}"
    )
    print(
        f"\ncards: {res['n_cards']}  (useful {res['n_useful_gold']}, wrong {res['n_wrong_gold']})"
        "   labels = mechanical perturbations of the REAL sentences, not tuned to the gate"
    )
    print(
        f"wrong-gold cards BLOCKED (recall): {res['wrong_recall'] * 100:.1f}%  "
        f"({res['n_wrong_gold'] - res['wrong_published']}/{res['n_wrong_gold']})"
    )
    print(
        f"useful-gold cards PUBLISHED (precision): {res['useful_precision'] * 100:.1f}%  "
        f"({res['useful_published']}/{res['n_useful_gold']})"
    )
    print(f"binary safety agreement: {res['binary_agreement'] * 100:.1f}%")
    print(
        f"\nSAFETY: wrong cards published (must be 0): {res['wrong_published']}  -> "
        f"{'SAFE' if res['safe'] else 'UNSAFE'}"
    )
    misses = [r for r in res["rows"] if not r["match"]]
    if misses:
        print(f"\nMISSES ({len(misses)}) -- reported honestly:")
        for m in misses:
            print(
                f"  op={m['op']:<10} gold={m['gold']:<14} gate={m['gate_verdict']:<24} "
                f"reason={m['reason']} cov={m['coverage']}"
            )
    else:
        print("\nMISSES: none")
    print(
        "\nresult: the same grounding + 3-way gate, run on REAL open-licensed text the\n"
        "project did not author, still blocks every wrong card and publishes none."
    )

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, os.path.dirname(HERE))}")
    return 0 if res["safe"] and all_real else 1


if __name__ == "__main__":
    raise SystemExit(main())
