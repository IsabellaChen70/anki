# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project): the "second look" -- a delayed re-test of a missed
reasoning QUESTION (extends the concept-level flashcard misses deck to the
questions themselves).

Proves the full loop end to end:
  1. a missed reasoning question schedules a real, FSRS-scheduled second-look card
     with a FUTURE due date (reusing Anki's own scheduler, not reinvented math);
  2. it does NOT surface before its due date but DOES resurface once due
     (fast-forwarding `today` / the stored due value);
  3. a successful second attempt is recorded DISTINCTLY from the original miss, so
     "missed then corrected" is tellable apart from "missed and still failing";
  4. no regressions: scheduling never inflates the flashcard give-up gate, never
     pollutes the reasoning-outcome revlog, and never touches the concept-level
     misses deck's own state.
"""

import importlib.util
import pathlib
import time

from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV, QUEUE_TYPE_SUSPENDED
from anki.vantage import collect
from tests.shared import getEmptyCol

_REPO = pathlib.Path(__file__).resolve().parents[2]
_RENDER = _REPO / "vantage_addon" / "render.py"


def _sl_card_row(col, cid):
    return col.db.all("select queue, due from cards where id = ?", cid)[0]


def _tags_of(col, cid):
    return col.db.scalar(
        "select n.tags from notes n join cards c on c.nid = n.id where c.id = ?", cid
    )


# --------------------------------------------------------------------------- #
# 1. a miss schedules a REAL card with a FUTURE due date (Anki's own scheduler)
# --------------------------------------------------------------------------- #
def test_missed_question_schedules_a_future_suspended_card():
    col = getEmptyCol()
    stem = "why does the buffer resist pH change"
    cid = collect.schedule_second_look(col, "chem_phys", stem, "ans", "why", concept="5A")
    assert cid is not None

    queue, due = _sl_card_row(col, cid)
    # suspended -> never leaks into the flashcard reviewer (practice re-serves it)
    assert queue == QUEUE_TYPE_SUSPENDED
    # a real, delayed due date assigned by Anki/FSRS (default 3 days out), not now
    assert due == col.sched.today + 3

    tags = _tags_of(col, cid)
    assert collect.SECOND_LOOK_SECTION_TAG + "chem_phys" in tags
    # reuses the SAME stable qid the reasoning anchor uses
    assert collect.REASONING_QID_TAG + collect._reasoning_qid(stem) in tags
    assert collect.REASONING_CONCEPT_TAG + "5A" in tags
    col.close()


def test_re_missing_the_same_question_reuses_one_card():
    col = getEmptyCol()
    stem = "same stem"
    c1 = collect.schedule_second_look(col, "bio_biochem", stem, "a", "e")
    c2 = collect.schedule_second_look(col, "bio_biochem", stem, "a", "e")
    assert c1 == c2  # deduped by qid -> one card, not a pile of copies
    n = col.db.scalar(
        "select count() from cards c join notes n on c.nid = n.id where n.tags like ?",
        f"%{collect.SECOND_LOOK_SECTION_TAG}%",
    )
    assert n == 1
    col.close()


# --------------------------------------------------------------------------- #
# 2. not due before its date; resurfaces once due (fast-forward the day number)
# --------------------------------------------------------------------------- #
def test_not_due_until_its_date_then_resurfaces():
    col = getEmptyCol()
    collect.schedule_second_look(col, "bio_biochem", "enzyme kinetics q", "a", "e")
    today = col.sched.today
    # before the due date: nothing to re-serve
    assert collect.due_second_looks(col, today=today) == []
    assert collect.due_second_looks(col, today=today + 2) == []
    # on/after the due date: it resurfaces, carrying enough to re-serve the question
    due = collect.due_second_looks(col, today=today + 3)
    assert len(due) == 1
    assert due[0]["section"] == "bio_biochem"
    assert due[0]["stem"] == "enzyme kinetics q"
    col.close()


# --------------------------------------------------------------------------- #
# 3. a passed second attempt is recorded distinctly and resolves the item
# --------------------------------------------------------------------------- #
def test_passed_second_look_records_distinctly_and_resolves():
    col = getEmptyCol()
    stem = "spacing effect q"
    cid = collect.schedule_second_look(col, "psych_soc", stem, "a", "e")
    qid = collect._reasoning_qid(stem)

    # bring the due date forward (simulate days passing) and confirm it is due
    col.sched.set_due_date([cid], "0")
    col.sched.suspend_cards([cid])
    assert [d["qid"] for d in collect.due_second_looks(col)] == [qid]

    # pass the second look: recorded in the SECOND-LOOK store, distinct from the miss
    collect.record_second_look_outcome(col, qid, "psych_soc", correct=True)

    # resolved: it no longer surfaces even though its card date has passed
    assert collect.due_second_looks(col) == []
    status = collect.second_look_status(col)
    assert status["corrected"] == 1
    assert status["still_failing"] == 0
    assert status["due_count"] == 0
    assert status["attempts"] == 1
    col.close()


# --------------------------------------------------------------------------- #
# 4. a failed second attempt is recorded, reschedules another look, stays unresolved
# --------------------------------------------------------------------------- #
def test_failed_second_look_reschedules_and_stays_unresolved():
    col = getEmptyCol()
    stem = "reaction spontaneity q"
    cid = collect.schedule_second_look(col, "chem_phys", stem, "a", "e")
    qid = collect._reasoning_qid(stem)

    # its due date arrives
    col.sched.set_due_date([cid], "0")
    col.sched.suspend_cards([cid])
    assert [d["qid"] for d in collect.due_second_looks(col)] == [qid]

    # miss it again: recorded distinctly AND pushed out another delay
    collect.record_second_look_outcome(col, qid, "chem_phys", correct=False)
    assert collect.due_second_looks(col) == []  # not due today anymore (rescheduled)
    due_day = col.db.scalar("select due from cards where id = ?", cid)
    assert due_day == col.sched.today + 3  # a fresh delayed look, Anki-scheduled

    # still unresolved, and it comes back after the new delay
    status = collect.second_look_status(col, col.sched.today + 3)
    assert status["still_failing"] == 1
    assert status["corrected"] == 0
    assert [d["qid"] for d in collect.due_second_looks(col, col.sched.today + 3)] == [qid]
    col.close()


def test_latest_attempt_wins_missed_then_corrected():
    col = getEmptyCol()
    qid = collect._reasoning_qid("later corrected q")
    collect.record_second_look_outcome(col, qid, "psych_soc", correct=False, ts=100)
    collect.record_second_look_outcome(col, qid, "psych_soc", correct=True, ts=200)
    status = collect.second_look_status(col)
    # the most recent outcome decides: corrected, not still-failing
    assert status["corrected"] == 1
    assert status["still_failing"] == 0
    assert status["attempts"] == 2
    col.close()


def test_corrected_and_still_failing_are_distinguishable():
    col = getEmptyCol()
    a, b = "alpha stem", "beta stem"
    ca = collect.schedule_second_look(col, "chem_phys", a, "x", "y")
    cb = collect.schedule_second_look(col, "bio_biochem", b, "x", "y")
    qa, qb = collect._reasoning_qid(a), collect._reasoning_qid(b)
    for c in (ca, cb):
        col.sched.set_due_date([c], "0")
        col.sched.suspend_cards([c])
    assert {d["qid"] for d in collect.due_second_looks(col)} == {qa, qb}

    collect.record_second_look_outcome(col, qa, "chem_phys", correct=True)
    collect.record_second_look_outcome(col, qb, "bio_biochem", correct=False)

    status = collect.second_look_status(col)
    assert status["corrected"] == 1  # a: missed then corrected
    assert status["still_failing"] == 1  # b: missed and still failing
    # the corrected one is gone; the still-failing one returns for another look
    remaining = {d["qid"] for d in collect.due_second_looks(col, col.sched.today + 3)}
    assert qa not in remaining
    assert qb in remaining
    col.close()


# --------------------------------------------------------------------------- #
# distinct per-device store: two devices' second-look results survive a merge
# --------------------------------------------------------------------------- #
def test_second_look_records_merge_across_devices_without_clobber():
    col = getEmptyCol()
    col.set_config(
        collect.SECOND_LOOK_DEVICE_PREFIX + "dev-a",
        [{"qid": "aaa", "section": "chem_phys", "correct": True, "ts": 10}],
    )
    col.set_config(
        collect.SECOND_LOOK_DEVICE_PREFIX + "dev-b",
        [{"qid": "bbb", "section": "bio_biochem", "correct": False, "ts": 20}],
    )
    recs = collect._all_second_look_records(col)
    assert len(recs) == 2  # both devices survive (distinct keys never clobber)
    latest = collect._latest_second_look_by_qid(recs)
    assert latest["aaa"]["correct"] is True
    assert latest["bbb"]["correct"] is False
    col.close()


def test_status_abstains_to_zero_when_there_is_nothing():
    col = getEmptyCol()
    assert collect.due_second_looks(col) == []
    assert collect.second_look_status(col) == {
        "due": [],
        "due_count": 0,
        "scheduled_count": 0,
        "corrected": 0,
        "still_failing": 0,
        "attempts": 0,
    }
    col.close()


# --------------------------------------------------------------------------- #
# no regressions: scheduling a second look is isolated from the other two flows
# --------------------------------------------------------------------------- #
def _add_review_card(col, tags, front="q"):
    note = col.newNote()
    note["Front"] = front
    note.tags = list(tags)
    col.addNote(note)
    card = note.cards()[0]
    card.type = CARD_TYPE_REV
    card.queue = QUEUE_TYPE_REV
    card.ivl = 10
    card.due = 0
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


def test_scheduling_second_looks_does_not_disturb_the_other_two_flows():
    col = getEmptyCol()
    # baseline flashcard study (the memory / readiness give-up gate reads this)
    _add_review_card(col, ["mcat::chem_phys::5A"], "flash")
    _insert_graded_reviews(col, 5)
    before_reviews = collect._graded_reviews(col)
    assert before_reviews == 5

    # schedule several second looks
    for i in range(3):
        assert collect.schedule_second_look(col, "chem_phys", f"missed q{i}", "a", "e")

    # (a) the flashcard give-up gate is untouched: set_due_date never logs a graded
    #     (ease 1..4) review, so the count does not move
    assert collect._graded_reviews(col) == before_reviews
    # (b) second-look cards are NOT reasoning anchors, so reasoning outcomes ignore
    #     them entirely (performance / readiness never see them)
    assert collect._has_reasoning_cards(col) is False
    assert collect._revlog_outcomes(col) == []
    # (c) the concept-level misses deck keeps its OWN state; scheduling a question-
    #     level second look never writes the flashcard-miss dedup key
    assert col.get_config("vantage_miss_seen", None) is None
    col.close()


def test_second_look_cards_are_excluded_from_memory_and_coverage_scan():
    col = getEmptyCol()
    collect.schedule_second_look(col, "chem_phys", "hidden from memory q", "a", "e")
    # the memory/coverage pass reads only non-suspended cards; the suspended
    # second-look card must not appear among them
    rows = collect._cards_r_and_tags(col)
    assert all(collect.SECOND_LOOK_SECTION_TAG not in tags for tags, _r in rows)
    col.close()


# --------------------------------------------------------------------------- #
# wiring: the dashboard payload exposes the second-look status for the web UI
# --------------------------------------------------------------------------- #
def _load_render():
    spec = importlib.util.spec_from_file_location("vantage_render", _RENDER)
    assert spec and spec.loader, _RENDER
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dashboard_dict_exposes_due_second_looks():
    try:
        render = _load_render()
    except Exception as exc:  # pragma: no cover - only if aqt creeps into render
        import pytest

        pytest.skip(f"render.py not importable headlessly: {exc}")
    col = getEmptyCol()
    cid = collect.schedule_second_look(col, "chem_phys", "wired-in q", "a", "e")
    col.sched.set_due_date([cid], "0")
    col.sched.suspend_cards([cid])
    data = render.dashboard_dict(col)
    assert "second_look" in data
    sl = data["second_look"]
    assert sl["due_count"] == 1
    assert sl["due"][0]["stem"] == "wired-in q"
    assert sl["due"][0]["section"] == "chem_phys"
    col.close()
