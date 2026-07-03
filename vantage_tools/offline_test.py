#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Offline / network-loss degrade check (PRD 10.7.4, spec-eval-harness 'offline-test').

Pull the network and the app must degrade cleanly: AI turns OFF (it was off by
default anyway) and BOTH apps keep reviewing and still produce the three honest
scores from local data. This asserts, with no network:

  1. AI-OFF by default: the shipped pipeline yields zero cards, status "ai_off".
  2. NETWORK LOSS is graceful: even a WIRED LLM generator whose provider call
     raises (a dropped connection) returns zero cards, never a crash -- so a
     failed model call never blocks the app.
  3. SCORING IS LOCAL + AI-INDEPENDENT: on a collection above the give-up line the
     dashboard computes all three scores (memory / performance / readiness) with
     `ai_used = False`, and on an empty collection it abstains honestly while still
     naming the best next topic. No model, no network, in either case.

Deterministic; writes vantage_tools/offline_results.json. Exit 0 = degrades cleanly.
Re-run:  out/pyenv/bin/python vantage_tools/offline_test.py   (or `just offline-test`)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

from anki import cards_pb2
from anki.collection import Collection
from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
from anki.vantage import collect

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ai"))  # flat AI-package imports
RESULTS_PATH = os.path.join(HERE, "offline_results.json")

FSRSMemoryState = cards_pb2.FsrsMemoryState
_CONCEPTS = [
    "1A", "1B", "1C", "1D", "2A", "2B", "2C", "3A", "3B",
    "4A", "4B", "4C", "4D", "4E", "5A", "5B", "5C", "5D", "5E",
    "6A", "6B", "6C", "7A", "7B",
]


def _add_review_card(col, basic, deck_id, tags, stability, elapsed_days, front):
    note = col.new_note(basic)
    note["Front"] = front
    note.tags = list(tags)
    col.add_note(note, deck_id)
    card = note.cards()[0]
    card.type = CARD_TYPE_REV
    card.queue = QUEUE_TYPE_REV
    card.ivl = elapsed_days
    card.due = 0
    card.memory_state = FSRSMemoryState(stability=stability, difficulty=5.0)
    card.last_review_time = int(time.time()) - elapsed_days * 86400
    col.update_card(card)


def _insert_graded_reviews(col, n):
    cid = col.db.scalar("select id from cards limit 1")
    base = int(time.time() * 1000)
    for i in range(n):
        col.db.execute(
            "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type)"
            " values (?,?,?,?,?,?,?,?,?)",
            base + i, cid, -1, (i % 4) + 1, 10, 5, 2500, 1000, 1,
        )


def _ready_collection(path: str) -> Collection:
    col = Collection(path)
    basic = col.models.by_name("Basic")
    deck_id = col.decks.id("Default")
    for c in _CONCEPTS:
        _add_review_card(col, basic, deck_id, [f"mcat::{c}"], 40.0, 10, f"c{c}")
    _insert_graded_reviews(col, 220)
    outcomes = []
    for s in ("chem_phys", "bio_biochem", "psych_soc"):
        for i in range(30):
            outcomes.append({"section": s, "correct": (i % 3) != 0})  # ~67%
    collect.set_perf_outcomes(col, outcomes)
    return col


def _ai_off_and_network_loss() -> dict:
    """AI is off by default, and a dropped provider connection yields zero cards."""
    from cardgen import (
        GenerationPipeline,
        GroundingChecker,
        LLMCardGenerator,
        QualityChecker,
    )
    from retrieval import build_retrievers
    from sources import build_chunks, load_corpus

    default_run = GenerationPipeline.default().run(
        "buffers and pH", topic_tag="mcat::chem::acids_bases"
    )

    corpus = load_corpus()
    chunks, _ = build_chunks(corpus)
    retriever = build_retrievers(chunks)["vantage_rag"]

    def dropped_connection(_prompt: str) -> str:
        raise ConnectionError("network is down")

    wired = LLMCardGenerator(client=dropped_connection, enabled=True, model="mock")
    pipe = GenerationPipeline(
        corpus, chunks, retriever, GroundingChecker(), wired, QualityChecker()
    )
    net_loss = pipe.run("enzymes", topic_tag="mcat::biochem::enzymes")

    return {
        "default_status": default_run.status,
        "default_cards": len(default_run.published),
        "netloss_status": net_loss.status,
        "netloss_cards": len(net_loss.published) + len(net_loss.blocked),
        "ai_off_default": default_run.status == "ai_off" and not default_run.published,
        "network_loss_graceful": (
            net_loss.status == "generated"
            and not net_loss.published
            and not net_loss.blocked
        ),
    }


def run() -> dict:
    ai = _ai_off_and_network_loss()

    tmp = tempfile.mkdtemp()
    # (a) rich local collection -> all three scores, AI untouched
    ready = _ready_collection(os.path.join(tmp, "ready.anki2"))
    dash = collect.gather(ready)
    scores_ok = (
        dash.ai_used is False
        and not dash.memory.abstained
        and not dash.performance.abstained
        and not dash.readiness.abstained
        and dash.readiness.band is not None
    )
    ready.close()

    # (b) empty collection -> honest abstention, still names the best next topic
    empty = Collection(os.path.join(tmp, "empty.anki2"))
    edash = collect.gather(empty)
    abstain_ok = (
        edash.ai_used is False
        and edash.readiness.abstained
        and edash.readiness.band is None
        and edash.best_next is not None
    )
    empty.close()

    checks = {
        "ai_off_by_default": ai["ai_off_default"],
        "network_loss_graceful": ai["network_loss_graceful"],
        "scores_computed_offline_ai_off": scores_ok,
        "empty_abstains_but_guides": abstain_ok,
    }
    return {
        "checks": checks,
        "ai_probe": ai,
        "ready_readiness_low": round(dash.readiness.band.low, 1),
        "ready_readiness_high": round(dash.readiness.band.high, 1),
        "degrades_cleanly": all(checks.values()),
        "network_used": False,
        "deterministic": True,
    }


def main() -> int:
    res = run()
    bar = "=" * 70
    print(bar)
    print("OFFLINE / NETWORK-LOSS DEGRADE CHECK")
    print(bar)
    a = res["ai_probe"]
    print(
        f"[1] AI off by default: status={a['default_status']} cards={a['default_cards']} "
        f"-> {res['checks']['ai_off_by_default']}"
    )
    print(
        f"[2] Dropped provider connection: status={a['netloss_status']} "
        f"cards={a['netloss_cards']} (0 = graceful) -> {res['checks']['network_loss_graceful']}"
    )
    print(
        f"[3] Local scoring, AI off: three scores computed "
        f"(readiness {res['ready_readiness_low']}-{res['ready_readiness_high']}) -> "
        f"{res['checks']['scores_computed_offline_ai_off']}"
    )
    print(
        f"[4] Empty collection: abstains but still names best next topic -> "
        f"{res['checks']['empty_abstains_but_guides']}"
    )
    print("\n" + "-" * 70)
    print(
        f"RESULT: {'DEGRADES CLEANLY (offline-safe)' if res['degrades_cleanly'] else 'FAILED'}"
    )
    print("-" * 70)

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, HERE)}")
    return 0 if res["degrades_cleanly"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
