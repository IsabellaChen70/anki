# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project): end-to-end test of the scoring adapter on a real Collection.

Proves the memory model runs against actual FSRS retrievability, coverage is read
from card tags, the readiness give-up rule fires below the line and lifts above it,
and none of it touches a model (AI-off by construction).
"""

import time

from anki import cards_pb2
from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
from anki.vantage import collect
from tests.shared import getEmptyCol

FSRSMemoryState = cards_pb2.FsrsMemoryState


def _add_review_card(col, tags, stability, elapsed_days, front="q"):
    note = col.newNote()
    note["Front"] = front
    note.tags = list(tags)
    col.addNote(note)
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
            base + i,
            cid,
            -1,
            (i % 4) + 1,  # ease 1..4 => all graded
            10,
            5,
            2500,
            1000,
            1,
        )


def test_memory_uses_real_fsrs_and_coverage_from_tags():
    col = getEmptyCol()
    for i in range(12):
        _add_review_card(col, ["mcat::bio_biochem::1A"], 30.0, 15, f"a{i}")
        _add_review_card(col, ["mcat::bio_biochem::1D"], 10.0, 25, f"b{i}")

    dash = collect.gather(col)

    assert not dash.memory.abstained
    b = dash.memory.band
    assert 0.0 <= b.low <= b.point <= b.high <= 1.0
    # cards with the shorter, older memory drag the mean below 1.0 (real decay)
    assert b.point < 1.0
    assert dash.memory.n == 24
    # coverage picked up exactly the two bio concepts
    assert dash.coverage_by_section["bio_biochem"] > 0
    assert dash.coverage_by_section["psych_soc"] == 0.0
    assert dash.ai_used is False
    col.close()


def test_readiness_abstains_below_the_line_then_lifts_above_it():
    col = getEmptyCol()

    # fresh: no reviews, no coverage -> readiness abstains, no number
    dash = collect.gather(col)
    assert dash.readiness.abstained
    assert dash.readiness.band is None
    assert dash.best_next is not None  # still tells you what to study

    # now cover >= 50% weighted, add 200+ graded reviews, and app-item outcomes
    concepts = [
        "1A", "1B", "1C", "1D", "2A", "2B", "2C", "3A", "3B",
        "4A", "4B", "4C", "4D", "4E", "5A", "5B", "5C", "5D", "5E",
        "6A", "6B", "6C", "7A", "7B",
    ]
    for c in concepts:
        _add_review_card(col, [f"mcat::{c}"], 40.0, 10, f"c{c}")
    _insert_graded_reviews(col, 220)
    outcomes = []
    for s in ("chem_phys", "bio_biochem", "psych_soc"):
        for i in range(30):
            outcomes.append({"section": s, "correct": (i % 3) != 0})  # ~67%
    collect.set_perf_outcomes(col, outcomes)

    dash = collect.gather(col)
    assert dash.coverage >= 0.5
    assert dash.n_reviews >= 200
    assert not dash.readiness.abstained
    assert dash.readiness.band is not None
    # 3-section partial only; never a 472..528 total
    assert 354.0 <= dash.readiness.band.low <= dash.readiness.band.high <= 396.0
    assert dash.readiness.extra["cars_modeled"] is False
    for band in dash.readiness.extra["sections"].values():
        assert 118.0 <= band.low <= band.point <= band.high <= 132.0
    assert not dash.performance.abstained
    col.close()
