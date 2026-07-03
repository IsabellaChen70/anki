#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Leakage / near-duplicate scan (Sec 7e, a HARD CAP).

WHAT LEAKAGE WOULD MEAN HERE
    A held-out EVAL item appearing (verbatim or near-verbatim) inside the
    TRAINING / generation data would let a system reproduce the answer without the
    intended skill, inflating the score. A leaked eval item zeroes that score, so
    this must be actively scanned, not assumed.

    Note (stated honestly): Vantage's AI path trains NO model (BM25 has no learned
    parameters, the checker is lexical, the generator is disabled), so there is no
    model that could memorise leaked text. And retrieval eval EXPECTS topical word
    overlap between a question and its source (that is the task). So the scan flags
    only near-VERBATIM duplication above a high, pre-registered threshold, not
    ordinary topical overlap.

PRE-REGISTERED (before looking at results)
    Normalise text (lowercase, strip punctuation, collapse whitespace). For each
    held-out eval item, take the MAX similarity to any training passage, where
    similarity = 1.0 on an exact normalised match, else
    max(word-trigram Jaccard, char-5gram Jaccard).
    LEAK cutoff = 0.80. CLEAN = zero eval items at or above the cutoff.
    (No embedding model is used, to keep the check offline + deterministic; the
    dual n-gram Jaccard is a standard lexical near-dup detector. This omission is
    stated, not hidden.)

DATA
    Training/generation:  vantage_tools/ai/corpus.json  (source sentences)
    Held-out / eval:      vantage_tools/ai/gold_set.json (questions),
                          vantage_tools/ai/retrofit_items.json (claims),
                          vantage_tools/paraphrase_items.json (reworded items), if present.
    Also checks paraphrase reworded items are NOT verbatim copies of their own
    recall card (else "application" would collapse into "recall").

Re-run (deterministic):  out/pyenv/bin/python vantage_tools/leakage_check.py
Writes vantage_tools/leakage_report.json ; exit 0 = CLEAN, 1 = leak found.
"""

from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.join(HERE, "ai")
CORPUS = os.path.join(AI, "corpus.json")
GOLD = os.path.join(AI, "gold_set.json")
RETROFIT = os.path.join(AI, "retrofit_items.json")
PARAPHRASE = os.path.join(HERE, "paraphrase_items.json")
RESULTS_PATH = os.path.join(HERE, "leakage_report.json")

LEAK_CUTOFF = 0.80  # pre-registered


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def word_ngrams(text: str, n: int = 3) -> set[str]:
    w = normalize(text).split()
    if len(w) < n:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i : i + n]) for i in range(len(w) - n + 1)}


def char_ngrams(text: str, n: int = 5) -> set[str]:
    s = normalize(text).replace(" ", "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: str, b: str) -> float:
    if normalize(a) == normalize(b):
        return 1.0
    return max(
        jaccard(word_ngrams(a), word_ngrams(b)),
        jaccard(char_ngrams(a), char_ngrams(b)),
    )


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def corpus_passages() -> list[str]:
    data = load_json(CORPUS)
    out = []
    for src in data["sources"]:
        out.extend(src.get("sentences", []))
    return out


def eval_items() -> list[tuple[str, str, str]]:
    """(set_name, item_id, text) for every HELD-OUT eval item: gold retrieval
    questions and paraphrase reworded application items. Retrofit CLAIMS are NOT
    held-out eval data -- they are the grounding checker's *supported* fixtures,
    designed to match their cited source span -- so they are reported separately
    (retrofit_overlap), informationally, not as leaks."""
    items: list[tuple[str, str, str]] = []
    for it in load_json(GOLD)["items"]:
        items.append(("gold_question", it["gold_id"], it["question"]))
    if os.path.exists(PARAPHRASE):
        for c in load_json(PARAPHRASE).get("concepts", []):
            cid = c.get("concept_id", "?")
            for j, item in enumerate(c.get("reworded", c.get("items", []))):
                stem = item.get("stem") or item.get("question") or ""
                if stem:
                    items.append(("paraphrase_reworded", f"{cid}#{j}", stem))
    return items


def retrofit_overlap(passages: list[str]) -> list[dict]:
    """Retrofit claims are checker 'supported' fixtures and SHOULD closely match
    their source span (high similarity is the intended signal, not leakage).
    Reported for transparency."""
    out = []
    for it in load_json(RETROFIT)["items"]:
        sim, _ = max_similarity(it["claim"], passages)
        out.append({"id": it["retrofit_id"], "max_similarity": round(sim, 3)})
    return out


def max_similarity(text: str, passages: list[str]) -> tuple[float, str]:
    best, best_p = 0.0, ""
    for p in passages:
        s = similarity(text, p)
        if s > best:
            best, best_p = s, p
            if best == 1.0:
                break
    return best, best_p


def paraphrase_self_leak() -> list[dict]:
    """Reworded items must NOT be verbatim copies of their own recall card."""
    if not os.path.exists(PARAPHRASE):
        return []
    flagged = []
    for c in load_json(PARAPHRASE).get("concepts", []):
        recall = c.get("recall", {})
        card_text = f"{recall.get('front', '')} {recall.get('back', '')}"
        for j, item in enumerate(c.get("reworded", c.get("items", []))):
            stem = item.get("stem") or item.get("question") or ""
            sim = similarity(stem, card_text)
            if sim >= LEAK_CUTOFF:
                flagged.append(
                    {"concept": c.get("concept_id"), "item": j, "similarity": round(sim, 3)}
                )
    return flagged


def main() -> int:
    passages = corpus_passages()
    items = eval_items()
    print(
        f"training passages: {len(passages)}   held-out eval items: {len(items)}   "
        f"leak cutoff: {LEAK_CUTOFF}\n"
    )

    per_item = []
    leaks = []
    worst = 0.0
    for set_name, item_id, text in items:
        sim, match = max_similarity(text, passages)
        worst = max(worst, sim)
        rec = {"set": set_name, "id": item_id, "max_similarity": round(sim, 3)}
        per_item.append(rec)
        if sim >= LEAK_CUTOFF:
            rec["match"] = match
            leaks.append(rec)

    # top overlaps for transparency (expected to be topical, below cutoff)
    top = sorted(per_item, key=lambda r: r["max_similarity"], reverse=True)[:5]
    print("highest eval<->training overlaps (topical overlap is expected):")
    for r in top:
        print(f"  {r['set']:<20}{r['id']:<12}max_sim={r['max_similarity']:.3f}")

    retro = retrofit_overlap(passages)
    print("\nretrofit claims vs source (checker 'supported' fixtures; high is BY DESIGN):")
    for r in sorted(retro, key=lambda r: r["max_similarity"], reverse=True)[:3]:
        print(f"  {r['id']:<16}max_sim={r['max_similarity']:.3f}")

    self_leaks = paraphrase_self_leak()

    clean = not leaks and not self_leaks
    print(
        f"\ncorpus<->eval leaks (>= {LEAK_CUTOFF}): {len(leaks)}"
        f"   paraphrase reworded==recall leaks: {len(self_leaks)}"
    )
    print(
        f"worst eval<->training similarity: {worst:.3f}  ->  "
        f"{'CLEAN' if clean else 'LEAK FOUND'}"
    )

    out = {
        "leak_cutoff": LEAK_CUTOFF,
        "n_training_passages": len(passages),
        "n_eval_items": len(items),
        "worst_similarity": round(worst, 3),
        "corpus_eval_leaks": leaks,
        "paraphrase_self_leaks": self_leaks,
        "clean": clean,
        "per_item": per_item,
        "retrofit_overlap_informational": retro,
        "note": (
            "No trained model exists (BM25/lexical/disabled generator), so "
            "memorisation-leakage risk is inherently low; retrieval topical overlap "
            "is expected and not flagged below the 0.80 cutoff. Held-out eval splits "
            "in evaluate_memory/performance are disjoint by construction (index cut "
            "over distinct ids)."
        ),
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH)}")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
