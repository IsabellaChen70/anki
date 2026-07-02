#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage ablation: topic-interleaving, feature OFF vs ON.

FEATURE UNDER TEST
    Topic-interleaving review order (the Rust change in
    rslib/src/scheduler/queue/builder/interleave.rs).

HYPOTHESIS (written before running)
    Turning the feature to MIXED should drop the rate of *consecutive
    same-topic* review cards to ~0, while stock order (OFF) leaves a chance
    rate (~1/number-of-topics) and the BLOCKED arm (deliberately grouping a
    topic together) is high. Fewer same-topic neighbors is the mechanism behind
    the learning-science claim that interleaving forces concept discrimination.

    Predicted before running: mixed << off < blocked.

METHOD
    Build a deterministic collection (fixed content + seed): N topics x M cards,
    all due for review today, added in a shuffled order so OFF reflects a
    realistic (not pre-sorted) queue. Then run the review-queue build three ways
    through the real engine (get_queued_cards) and measure the same-topic
    adjacency rate of the resulting order.

REPRODUCIBLE
    Fixed content and seed; no randomness beyond the seeded shuffle. Re-run:
        out/pyenv/bin/python vantage_tools/ablation_interleave.py
"""

from __future__ import annotations

import os
import random
import tempfile

from anki.collection import Collection

TOPICS = ["t1", "t2", "t3", "t4"]
PER_TOPIC = 6
SEED = 7


def same_topic_adjacency(topics: list[str]) -> float:
    if len(topics) < 2:
        return 0.0
    same = sum(1 for a, b in zip(topics, topics[1:]) if a == b)
    return same / (len(topics) - 1)


def build_due_collection(path: str) -> Collection:
    col = Collection(path)
    basic = col.models.by_name("Basic")
    did = col.decks.id("Ablation")
    col.decks.select(did)
    pairs = [(t, i) for t in TOPICS for i in range(PER_TOPIC)]
    random.Random(SEED).shuffle(pairs)  # realistic, not pre-sorted by topic
    for t, i in pairs:
        note = col.new_note(basic)
        note["Front"] = f"{t} card {i}"
        note["Back"] = "x"
        note.tags = [f"mcat::sci::{t}"]
        col.add_note(note, did)
    # make every card a review card due today
    col.db.execute("update cards set queue=2, type=2, due=?, ivl=10", col.sched.today)
    return col


def queue_topics(col: Collection) -> list[str]:
    q = col._backend.get_queued_cards(fetch_limit=1000, intraday_learning_only=False)
    out = []
    for qc in q.cards:
        tags = col.get_card(qc.card.id).note().tags
        topic = next((t for t in tags if t.startswith("mcat::")), "::untagged")
        out.append(topic)
    return out


def main() -> None:
    path = os.path.join(tempfile.mkdtemp(), "ablation.anki2")
    col = build_due_collection(path)
    total = len(TOPICS) * PER_TOPIC
    print(
        f"content: {len(TOPICS)} topics x {PER_TOPIC} cards = {total} due review cards, "
        f"seed={SEED}\n"
    )
    print(f"{'mode':<9}{'same-topic adjacency':<22}{'meaning'}")
    results = {}
    for name, mode in [("off", 0), ("mixed", 1), ("blocked", 2)]:
        col.sched.set_interleave_mode(mode=mode, topic_tag_prefix="mcat", seed=SEED)
        rate = same_topic_adjacency(queue_topics(col))
        results[name] = rate
        meaning = {
            "off": "stock Anki order (feature off)",
            "mixed": "interleaving ON (the feature)",
            "blocked": "grouped arm (worst case)",
        }[name]
        print(f"{name:<9}{rate:<22.3f}{meaning}")
    col.close()

    print("\nhypothesis: mixed << off < blocked")
    ok = results["mixed"] < results["off"] < results["blocked"]
    print(
        f"result: {'CONFIRMED' if ok else 'NOT confirmed'}  "
        f"(mixed={results['mixed']:.3f}, off={results['off']:.3f}, "
        f"blocked={results['blocked']:.3f})"
    )


if __name__ == "__main__":
    main()
