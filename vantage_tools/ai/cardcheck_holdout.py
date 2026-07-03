#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Independent held-out card-check set (de-circularizes eval_cardcheck.py).

WHY THIS EXISTS
    `chapter_cardgen.py` authors 50 cards that each CARRY their intended verdict,
    hand-tuned so the gate agrees; `eval_cardcheck.py`'s 100% "accuracy" against
    those labels is therefore self-fulfilling -- it proves the gate's MECHANICS,
    not that it generalizes. This module builds a SEPARATE set whose labels come
    from MECHANICAL, content-level perturbations of real corpus sentences the gate
    was never tuned on:

        useful    : a real corpus sentence, cited to itself (faithful + specific).
        wrong/negation  : "It is not true that <sentence>"  (polarity flip).
        wrong/numeric   : one number in the sentence swapped for another.
        wrong/misattrib : a faithful sentence cited to an UNRELATED span (the
                          claim is true, but not supported by the cited source).

    The label is fixed by the OPERATION, independent of the gate's own lexical
    teaching heuristics, and the gate never sees it. Running the gate here measures
    GENERALIZATION -- does it catch corrupted cards it did not author -- and every
    miss is printed, not hidden. The safety-critical invariant: NO card whose gold
    label is `wrong` may be published.

    Deterministic: sentences are enumerated in sorted (source_id, index) order and
    selected by a fixed rule; re-running yields byte-identical cards.

Re-run:  out/pyenv/bin/python vantage_tools/ai/cardcheck_holdout.py
Writes vantage_tools/ai/cardcheck_holdout_results.json ; exit 0 = safe (no wrong
card published), 1 otherwise.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from cardgen import Candidate
from checker import _DIGIT_RE, _NEGATION_RE, _NUMBER_WORDS, GroundingChecker
from quality import CORRECT_USEFUL, WRONG, QualityChecker
from retrieval import Tokenizer
from sources import Corpus, SourceRef, build_chunks, load_corpus

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "cardcheck_holdout_results.json")

STEM = "According to the cited source, state the key fact it gives."
MIN_CONTENT_TOKENS = 6  # only perturb sentences specific enough to teach
_CONTENT_TOK = Tokenizer(stem=True, remove_stopwords=True)


@dataclass
class HeldoutCard:
    candidate: Candidate
    gold: str  # CORRECT_USEFUL | WRONG
    op: str  # useful | negation | numeric | misattrib


def _content_len(text: str) -> int:
    return len(set(_CONTENT_TOK.tokens(text)))


def _swap_number(text: str) -> str | None:
    """Swap one number for a different one, or return None if there is none."""
    m = _DIGIT_RE.search(text)
    if m:
        old = m.group()
        if "." in old:
            new = "0.9" if old != "0.9" else "0.2"
        else:
            iv = int(old)
            new = str(iv + 3) if iv < 100 else str(iv // 2)
            if new == old:
                new = str(iv + 5)
        return text[: m.start()] + new + text[m.end() :]
    low = text.lower()
    for word in _NUMBER_WORDS:
        if re.search(rf"\b{word}\b", low):
            repl = "seven" if word != "seven" else "three"
            return re.sub(rf"\b{word}\b", repl, text, count=1, flags=re.IGNORECASE)
    return None


def _has_number(text: str) -> bool:
    if _DIGIT_RE.search(text):
        return True
    low = text.lower()
    return any(re.search(rf"\b{w}\b", low) for w in _NUMBER_WORDS)


def _candidate(answer: str, ref: SourceRef, corpus: Corpus, op: str) -> Candidate:
    return Candidate(
        kind="recall",
        stem=STEM,
        answer=answer,
        claim=answer,
        source_ref=ref,
        provenance={
            "model": "holdout-perturbation-v1 (mechanical, LLM OFF)",
            "op": op,
            "locator": ref.locator(),
            "citation": corpus.citation_for(ref.source_id),
        },
    )


def build_holdout(corpus: Corpus | None = None) -> list[HeldoutCard]:
    corpus = corpus or load_corpus()
    chunks, _ = build_chunks(corpus)
    # Clean, non-canary sentences, long enough to be specific, in deterministic order.
    facts = [
        c
        for c in sorted(chunks, key=lambda c: (c.source_id, c.sent_idx))
        if not corpus.docs[c.source_id].canary
        and _content_len(c.text) >= MIN_CONTENT_TOKENS
    ]
    checker = GroundingChecker()
    cards: list[HeldoutCard] = []
    used_useful: list[str] = []

    def _near_dup(text: str) -> bool:
        toks = set(_CONTENT_TOK.tokens(text))
        for prev in used_useful:
            p = set(_CONTENT_TOK.tokens(prev))
            if p and toks and len(toks & p) / len(toks | p) >= 0.6:
                return True
        return False

    # 1) USEFUL: faithful sentence cited to itself (distinct facts only).
    for c in facts:
        if len(used_useful) >= 14:
            break
        if _near_dup(c.text):
            continue
        used_useful.append(c.text)
        cards.append(
            HeldoutCard(_candidate(c.text, c.ref(), corpus, "useful"), CORRECT_USEFUL, "useful")
        )

    # 2) NEGATION: polarity flip on sentences that are not already negated.
    neg = 0
    for c in facts:
        if neg >= 8:
            break
        if _NEGATION_RE.search(c.text.lower()):
            continue
        answer = "It is not true that " + c.text[0].lower() + c.text[1:]
        cards.append(
            HeldoutCard(_candidate(answer, c.ref(), corpus, "negation"), WRONG, "negation")
        )
        neg += 1

    # 3) NUMERIC: swap one number so the claim conflicts with its source.
    num = 0
    for c in facts:
        if num >= 6:
            break
        if not _has_number(c.text):
            continue
        swapped = _swap_number(c.text)
        if swapped is None or swapped == c.text:
            continue
        cards.append(
            HeldoutCard(_candidate(swapped, c.ref(), corpus, "numeric"), WRONG, "numeric")
        )
        num += 1

    # 4) MISATTRIB: a faithful sentence cited to an UNRELATED, low-overlap span.
    mis = 0
    for c in facts:
        if mis >= 8:
            break
        best = None  # a span from a DIFFERENT source with coverage below the cutoff
        for other in facts:
            if other.source_id == c.source_id:
                continue
            cov = checker.check_text(c.text, other.text).coverage
            if cov < checker.cutoff and (best is None or cov < best[1]):
                best = (other, cov)
        if best is None:
            continue
        cards.append(
            HeldoutCard(_candidate(c.text, best[0].ref(), corpus, "misattrib"), WRONG, "misattrib")
        )
        mis += 1

    return cards


def evaluate(cards: list[HeldoutCard], corpus: Corpus) -> dict:
    checker = GroundingChecker()
    gate = QualityChecker()
    accepted: list[str] = []
    rows: list[dict] = []
    wrong_published = 0
    caught = 0  # wrong-gold cards the gate blocked
    n_wrong = 0
    useful_published = 0
    n_useful = 0

    for hc in cards:
        c = hc.candidate
        grounding = checker.check_ref(c.claim, c.source_ref, corpus)
        qr = gate.classify(c.stem, c.answer, grounding, accepted)
        published = qr.published
        if published:
            accepted.append(c.answer)
        if hc.gold == WRONG:
            n_wrong += 1
            if published:
                wrong_published += 1
            else:
                caught += 1
        else:
            n_useful += 1
            if published:
                useful_published += 1
        rows.append(
            {
                "op": hc.op,
                "gold": hc.gold,
                "gate_verdict": qr.verdict,
                "reason": qr.reason,
                "coverage": round(grounding.coverage, 3),
                "published": published,
                "locator": c.source_ref.locator(),
                "answer": c.answer[:80],
                # binary match on the safety axis: wrong<->blocked, useful<->published
                "match": (hc.gold == WRONG and not published)
                or (hc.gold == CORRECT_USEFUL and published),
            }
        )

    n = len(cards)
    binary_agreement = sum(1 for r in rows if r["match"]) / n if n else 0.0
    wrong_recall = caught / n_wrong if n_wrong else 0.0
    useful_precision = useful_published / n_useful if n_useful else 0.0
    return {
        "n_cards": n,
        "n_useful_gold": n_useful,
        "n_wrong_gold": n_wrong,
        "binary_agreement": round(binary_agreement, 4),
        "wrong_recall": round(wrong_recall, 4),  # fraction of wrong cards blocked
        "useful_published": useful_published,
        "useful_precision": round(useful_precision, 4),
        "wrong_published": wrong_published,  # SAFETY: must be 0
        "safe": wrong_published == 0,
        "rows": rows,
        "deterministic": True,
        "llm_off": True,
        "labels": "mechanical perturbation of real corpus sentences (independent of the gate)",
    }


def main() -> int:
    corpus = load_corpus()
    cards = build_holdout(corpus)
    res = evaluate(cards, corpus)

    bar = "=" * 74
    print(bar)
    print("HELD-OUT CARD CHECK: independent labels, gate judges cards it didn't author")
    print(bar)
    print(
        f"cards: {res['n_cards']}  (useful {res['n_useful_gold']}, wrong {res['n_wrong_gold']})"
        "   labels = mechanical perturbations, not tuned to the gate"
    )
    print(
        f"\nwrong-gold cards BLOCKED (recall): {res['wrong_recall'] * 100:.1f}%  "
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

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, os.path.dirname(HERE))}")
    return 0 if res["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
