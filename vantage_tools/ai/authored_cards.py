#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Offline, deterministic card generation for one AAMC coverage gap, gated by the
SAME pipeline that gates every other AI card (spec-ai-cardgen.md sec 5).

This is the engine behind the dashboard's opt-in "Generate cards for a gap"
button in the shipped (AI-off) default. There is no live model here: the content
is a set of authored, corpus-mapped card items (card_items.json), each restating
what a NAMED source already says (grounded by construction). Every item is turned
into a `cardgen.Candidate` and run through `cardgen.GenerationPipeline.gate_candidate`
-- the one shared gate the card generator and the reasoning-explanations path also
use. There is NO forked grounding/quality logic here and NO new threshold: the
coverage cutoff and quality thresholds come from checker.py / quality.py unchanged.

Honesty-first: only cards that PASS the gate are published; anything that fails
(no SourceRef, ungrounded, or low teaching quality) is blocked and never added. A
category with no authored, source-backed item here generates nothing rather than a
fabricated card. A real LLM seam would produce the same shape of candidate and pass
through the same gate before anything reached a student.

Inputs / outputs:
  card_items.json  (authored)  concept_id + topic_id + stem + answer + SourceRef
                               + a topic `tag` (an outline alias) for coverage.
  cards_for_concept(...)       gate the items for ONE category and return the
                               published Candidates plus the blocked (candidate,
                               reason) pairs. The desktop bridge writes the passers.

Run:  python3 vantage_tools/ai/authored_cards.py
"""

from __future__ import annotations

import json
from pathlib import Path

from cardgen import Candidate, GenerationPipeline
from sources import Corpus, SourceRef, load_corpus

HERE = Path(__file__).resolve().parent
ITEMS_PATH = HERE / "card_items.json"

# Provenance marker for a source-grounded, offline authored card (not a live model).
MODEL_NAME = "offline-authored-card-v1"


def load_items(path: Path = ITEMS_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    return list(items or [])


def items_for_concept(items: list[dict], concept_id: str) -> list[dict]:
    """The authored items scoped to ONE AAMC content category (case-insensitive)."""
    cid = str(concept_id or "").strip().lower()
    return [it for it in items if str(it.get("concept_id", "")).strip().lower() == cid]


def _source_ref(item: dict) -> SourceRef | None:
    """The item's SourceRef, or None when absent/malformed. A None (or unresolvable)
    ref makes the gate block the item ("SourceRef required")."""
    raw = item.get("source_ref")
    if not isinstance(raw, dict):
        return None
    try:
        return SourceRef.from_dict(raw)
    except (KeyError, TypeError, ValueError):
        return None


def card_candidate(item: dict, corpus: Corpus) -> Candidate:
    """Build a gate Candidate for one authored card. The answer is both the shown
    card back and the claim the grounding checker verifies against the cited span
    (claim == answer, the card-generator convention). `coverage_alias` (a topic
    alias) rides in provenance so the written card can count toward that topic."""
    stem = str(item.get("stem", "")).strip()
    answer = str(item.get("answer", "")).strip()
    ref = _source_ref(item)
    provenance: dict = {
        "model": MODEL_NAME,
        "kind": "authored_card",
        "concept_id": str(item.get("concept_id", "")).strip(),
        "topic_id": str(item.get("topic_id", "")).strip(),
        "coverage_alias": str(item.get("tag", "")).strip(),
    }
    if ref is not None and ref.source_id in corpus.docs:
        provenance["citation"] = corpus.citation_for(ref.source_id)
        provenance["locator"] = ref.locator()
    return Candidate(
        kind="recall",
        stem=stem,
        answer=answer,
        claim=answer,
        source_ref=ref,
        provenance=provenance,
    )


def cards_for_concept(
    concept_id: str,
    corpus: Corpus,
    pipe: GenerationPipeline,
    *,
    items: list[dict] | None = None,
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """Gate the authored cards for ONE category and split them into published and
    blocked. Reuses the pipeline's shared per-candidate gate exactly like `run()`:
    it loops `gate_candidate`, accumulating accepted answers so the duplicate signal
    fires within the batch. Returns (published, [(blocked_candidate, reason), ...])."""
    items = load_items() if items is None else items
    scoped = items_for_concept(items, concept_id)
    published: list[Candidate] = []
    blocked: list[tuple[Candidate, str]] = []
    accepted_answers: list[str] = []
    for item in scoped:
        cand = card_candidate(item, corpus)
        outcome = pipe.gate_candidate(cand, accepted_answers)
        if outcome.published:
            published.append(cand)
            accepted_answers.append(cand.answer)
        else:
            blocked.append((cand, outcome.reason))
    return published, blocked


def _summary(corpus: Corpus | None = None) -> dict:
    """Gate every authored card, grouped by category, for a quick offline audit."""
    corpus = corpus or load_corpus()
    pipe = GenerationPipeline.default(corpus)
    items = load_items()
    by_concept: dict[str, dict] = {}
    for cid in sorted({str(it.get("concept_id", "")) for it in items}):
        pub, blk = cards_for_concept(cid, corpus, pipe)
        by_concept[cid] = {"published": len(pub), "blocked": len(blk)}
    return by_concept


if __name__ == "__main__":
    summary = _summary()
    total_pub = sum(v["published"] for v in summary.values())
    total_blk = sum(v["blocked"] for v in summary.values())
    print(f"authored cards gated: {total_pub} published / {total_blk} blocked")
    for cid, counts in summary.items():
        print(f"  {cid}: {counts['published']} published, {counts['blocked']} blocked")
