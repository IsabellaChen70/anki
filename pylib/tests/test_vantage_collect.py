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
from anki.vantage.outline import Outline
from anki.vantage.scoring import ScoringConfig
from tests.shared import getEmptyCol

FSRSMemoryState = cards_pb2.FsrsMemoryState
CFG = ScoringConfig()


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


# --------------------------------------------------------------------------- #
# adaptive plan: content gaps to study vs topics ready to practice
# --------------------------------------------------------------------------- #
def test_study_plan_leads_with_content_gaps_when_nothing_studied():
    outline = Outline.load()
    plan = collect.study_plan(outline, covered=set(), concept_recall={}, cfg=CFG)
    assert plan["practice"] == []  # nothing is content-ready to practice yet
    assert plan["study"]  # content gaps to study
    top = plan["study"][0]
    assert top.recall is None  # uncovered, not studied
    assert top.concept_id == "1A"  # heaviest concept (weight 5) leads


def test_study_plan_moves_solid_recall_to_practice():
    outline = Outline.load()
    plan = collect.study_plan(outline, {"1A"}, {"1A": [0.9, 0.92]}, cfg=CFG)
    assert any(x.concept_id == "1A" for x in plan["practice"])
    assert all(x.concept_id != "1A" for x in plan["study"])


def test_study_plan_keeps_weak_recall_as_a_content_gap():
    outline = Outline.load()
    plan = collect.study_plan(outline, {"1A"}, {"1A": [0.5]}, cfg=CFG, top=99)
    # weak recall (0.5 < content-ready line) stays a study gap, never practice
    assert any(x.concept_id == "1A" for x in plan["study"])
    assert all(x.concept_id != "1A" for x in plan["practice"])


# --------------------------------------------------------------------------- #
# readiness history: snapshot once per day, no stale trajectory, robust config
# --------------------------------------------------------------------------- #
def _ready_collection():
    """A collection above the give-up line that yields a full 3-section composite."""
    col = getEmptyCol()
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
    return col


def test_readiness_history_writes_at_most_once_per_day():
    col = _ready_collection()
    writes = []
    orig_set = col.set_config

    def counting_set(key, val):
        if key == collect.HISTORY_CONFIG_KEY:
            writes.append(val)
        return orig_set(key, val)

    col.set_config = counting_set
    collect.gather(col)  # first render records today's full-composite snapshot
    collect.gather(col)  # nothing changed -> must not rewrite the collection
    collect.gather(col)
    assert len(writes) == 1
    hist = col.get_config(collect.HISTORY_CONFIG_KEY, [])
    today = collect._today_iso()
    assert sum(1 for h in hist if h.get("d") == today) == 1
    col.close()


def test_trajectory_does_not_project_stale_history_after_dropping_below_line():
    col = _ready_collection()
    col.set_config(collect.TARGET_CONFIG_KEY, 500)
    col.set_config(collect.EXAM_CONFIG_KEY, "2099-01-01")
    # pretend readiness used to be live: several dated snapshots on file
    col.set_config(
        collect.HISTORY_CONFIG_KEY,
        [
            {"d": "2026-06-01", "point": 380.0},
            {"d": "2026-06-02", "point": 381.0},
            {"d": "2026-06-03", "point": 382.0},
        ],
    )
    # now the evidence disappears -> readiness abstains; the trajectory must not
    # keep projecting from the stale snapshots.
    collect.set_perf_outcomes(col, [])
    dash = collect.gather(col)
    assert dash.readiness.abstained
    assert dash.trajectory.abstained
    col.close()


def test_gather_survives_corrupt_config():
    col = _ready_collection()
    # one corrupt perf entry (non-dict) + a non-numeric ms must not crash gather
    perf = col.get_config(collect.PERF_CONFIG_KEY, [])
    perf = perf + ["bogus", None, {"section": "chem_phys", "correct": False, "ms": "NaNish"}]
    col.set_config(collect.PERF_CONFIG_KEY, perf)
    # corrupt history entries alongside a single valid one
    col.set_config(
        collect.HISTORY_CONFIG_KEY,
        [
            "junk",
            None,
            7,
            {"d": 20260601, "point": 380.0},  # bad date type
            {"d": "2026-06-01", "point": "oops"},  # bad point
            {"d": "2026-06-02", "point": 381.0},  # the one usable point
        ],
    )
    dash = collect.gather(col)  # must not raise
    assert not dash.readiness.abstained  # 90 valid outcomes still lift readiness
    assert dash.pacing is not None
    col.close()


def test_cars_reasoning_lifts_readiness_to_a_full_four_section_composite():
    col = _ready_collection()  # 3 science sections above the line
    dash3 = collect.gather(col)
    assert dash3.readiness.extra["cars_modeled"] is False
    assert set(dash3.readiness.extra["modeled_sections"]) == set(
        ("chem_phys", "bio_biochem", "psych_soc")
    )
    # 3-section partial: sits on the 354..396 band
    assert 354.0 <= dash3.readiness.band.low <= dash3.readiness.band.high <= 396.0

    # answer enough CARS reasoning questions -> CARS becomes a 4th scored section
    for i in range(8):
        collect.log_reasoning_outcome(
            col, "cars", f"cars q{i}", "a", "e", correct=(i % 3 != 0), ms=1000
        )
    dash4 = collect.gather(col)
    assert dash4.readiness.extra["cars_modeled"] is True
    assert "cars" in dash4.readiness.extra["modeled_sections"]
    # now a full 4-section projection on the real 472..528 scale
    assert 472.0 <= dash4.readiness.band.low <= dash4.readiness.band.high <= 528.0
    assert 118.0 <= dash4.readiness.extra["sections"]["cars"].point <= 132.0
    col.close()


def test_outline_loads_topics_and_computes_topic_coverage():
    ol = Outline.load()
    assert len(ol.concepts) == 31
    assert all(c.topics for c in ol.concepts)  # every category has authored topics
    assert len(ol.topics) >= 140  # ~151 authored across the three sciences
    tids = [t.id for t in ol.topics]
    assert len(tids) == len(set(tids))  # topic ids are unique
    assert all(t.id.startswith(t.category + ".") for t in ol.topics)

    # unambiguous topic aliases map to exactly their topic
    covered = ol.covered_topics(["glycolysis", "mitosis", "snells_law"])
    assert covered == {"1D.3", "2C.1", "4D.4"}
    assert ol.topic("1D.3").category == "1D"
    cov = ol.topic_coverage_by_category(covered)
    assert cov["1D"] == (1, len(ol.concept("1D").topics))
    miss = ol.missing_topics(covered)
    assert all(t.id not in covered for t in miss)
    assert [t.weight for t in miss] == sorted((t.weight for t in miss), reverse=True)


def test_topics_do_not_change_category_coverage():
    # backward compat: adding topics leaves category-level coverage untouched.
    ol = Outline.load()
    tags = ["amino_acids", "glycolysis", "mitosis", "vision"]
    assert ol.covered_concepts(tags) == {"1A", "1D", "2C", "6A"}
    assert 0.0 < ol.weighted_coverage(ol.covered_concepts(tags)) < 1.0


def test_next_topics_surfaces_uncovered_topic_names():
    ol = Outline.load()
    # 1D studied only at the glycolysis topic; the rest are still gaps
    items = collect._next_topics(ol, {"1D"}, {"1D": [0.5]}, {"1D.3"}, top=31)
    d = {it["concept_id"]: it for it in items}["1D"]
    assert d["topics_total"] == len(ol.concept("1D").topics)
    assert d["topics_covered"] == 1
    # the surfaced topics are the UNCOVERED ones (not the studied glycolysis topic)
    assert ol.topic("1D.3").name not in d["topics"]
    assert 1 <= len(d["topics"]) <= 4


# --------------------------------------------------------------------------- #
# #7A: reasoning outcomes as real cards + revlog (sync-safe), config as fallback
# --------------------------------------------------------------------------- #
def _log_reasoning(col, section, stem, correct, ms=1200):
    return collect.log_reasoning_outcome(
        col, section, stem, "the answer", "why it is right", correct, ms
    )


def _reasoning_card_count(col):
    return col.db.scalar(
        "select count() from cards c join notes n on c.nid = n.id where n.tags like ?",
        f"%{collect.REASONING_SECTION_TAG}%",
    )


def test_reasoning_outcomes_are_real_cards_and_revlog():
    col = getEmptyCol()
    for i in range(6):
        rid = _log_reasoning(col, "chem_phys", f"question {i}", correct=(i % 2 == 0))
        assert rid is not None
    ro = collect._revlog_outcomes(col)
    assert len(ro) == 6
    assert all(o["section"] == "chem_phys" for o in ro)
    assert sum(1 for o in ro if o["correct"]) == 3  # even i -> correct
    # one anchor card per unique question, and every anchor is suspended so it never
    # pollutes the memory/coverage pass (which skips queue == -1)
    assert _reasoning_card_count(col) == 6
    queues = col.db.list(
        "select c.queue from cards c join notes n on c.nid = n.id where n.tags like ?",
        f"%{collect.REASONING_SECTION_TAG}%",
    )
    assert queues and all(q == -1 for q in queues)
    col.close()


def test_same_question_reuses_one_anchor_card_with_many_attempts():
    col = getEmptyCol()
    r1 = _log_reasoning(col, "bio_biochem", "same stem", correct=False)
    r2 = _log_reasoning(col, "bio_biochem", "same stem", correct=True)
    assert r1 is not None and r2 is not None and r1 != r2
    assert _reasoning_card_count(col) == 1  # one card, two revlog attempts
    assert len(collect._revlog_outcomes(col)) == 2
    col.close()


def test_study_pace_reasoning_today_counts_only_todays_attempts():
    # The practice screen's "X of Y today" counter reads study_pace.reasoning_today:
    # reasoning attempts since the day rollover. Attempts from earlier days must not
    # inflate today's progress.
    col = getEmptyCol()
    for i in range(3):
        _log_reasoning(col, "chem_phys", f"today q{i}", correct=(i != 0))
    # A back-dated attempt on an existing anchor card, three days before the
    # rollover, is a real outcome but not part of *today*.
    cid = col.db.scalar(
        "select c.id from cards c join notes n on c.nid = n.id where n.tags like ? limit 1",
        f"%{collect.REASONING_SECTION_TAG}%",
    )
    old_id = (int(col.sched.day_cutoff) - 3 * 86400) * 1000
    col.db.execute(
        "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type)"
        " values (?,?,?,?,?,?,?,?,?)",
        old_id, cid, -1, 3, 10, 5, 2500, 1200, 1,
    )
    dash = collect.gather(col)
    assert len(collect._merged_outcomes(col)) == 4  # all four are real outcomes
    assert dash.study_pace.reasoning_today == 3  # but only today's three count
    col.close()


# --------------------------------------------------------------------------- #
# deck-hierarchy -> topic mapping + depth-aware (topic-grain) coverage
# --------------------------------------------------------------------------- #
def test_deck_topic_map_resolves_imported_hierarchy():
    outline = Outline.load()
    # MileDown's own topic tag resolves to its AAMC topic (via deck_topic_map.json),
    # matched through the normal tag matcher.
    tid = outline.match_tag_topic("MileDown::Biochemistry::Metabolism::Glycolysis")
    assert tid is not None and tid.startswith("1D")
    # Pankow encodes the topic in the DECK path; deck_topic() resolves it exactly.
    dtid = outline.deck_topic("MCAT \U0001f499::P/S Deck::9B::Demographics")
    assert dtid is not None and dtid.startswith("9B")
    # An unmapped deck path returns None (no loose alias fallback for deck names).
    assert outline.deck_topic("Totally::Unmapped::Deck") is None


def test_topic_weighted_coverage_reflects_depth_not_just_breadth():
    outline = Outline.load()
    all_topics = {t.id for t in outline.topics}
    assert outline.topic_weighted_coverage(set(), set()) == 0.0
    full = outline.topic_weighted_coverage(all_topics, set())
    assert 0.99 <= full <= 1.0  # every topic covered -> ~100%
    # Touching every CATEGORY (breadth) but few topics (depth) stays well below 100%,
    # which is the whole point: the display number no longer saturates at 100%.
    one_topic_per_cat = {c.topics[0].id for c in outline.concepts if c.topics}
    shallow = outline.topic_weighted_coverage(one_topic_per_cat, {c.id for c in outline.concepts})
    assert 0.0 < shallow < 0.6


def test_merged_outcomes_count_revlog_and_config_twin_once():
    col = getEmptyCol()
    rid = _log_reasoning(col, "psych_soc", "meta q", correct=True, ms=2500)
    # the add-on also writes a config record carrying the metacognition, linked by
    # revlog id; the merge must count this answer once, enriched from config
    col.set_config(
        collect.PERF_CONFIG_KEY,
        [
            {
                "section": "psych_soc", "correct": True, "confidence": "sure",
                "reason": None, "ms": 2500, "revlog_id": rid, "logged": True,
            }
        ],
    )
    merged = collect._merged_outcomes(col)
    assert len(merged) == 1  # not 2
    assert merged[0]["correct"] is True  # outcome from the revlog
    assert merged[0]["confidence"] == "sure"  # metacognition from config
    col.close()


def test_merged_outcomes_keep_legacy_config_when_no_revlog():
    col = getEmptyCol()
    # a collection that only ever wrote config (older build, or mobile) still scores:
    # additive, nothing lost
    col.set_config(
        collect.PERF_CONFIG_KEY,
        [
            {"section": "chem_phys", "correct": True},
            {"section": "chem_phys", "correct": False},
        ],
    )
    merged = collect._merged_outcomes(col)
    assert len(merged) == 2
    col.close()


def test_graded_reviews_gate_excludes_reasoning_revlog():
    col = getEmptyCol()
    _add_review_card(col, ["mcat::bio_biochem::1A"], 30.0, 15, "flash")
    _insert_graded_reviews(col, 5)  # 5 flashcard reviews
    _log_reasoning(col, "chem_phys", "a reasoning q", correct=True)  # 1 reasoning
    # the flashcard give-up gate counts flashcards only, not reasoning attempts
    assert collect._graded_reviews(col) == 5
    assert col.db.scalar("select count() from revlog") == 6  # both are in the revlog
    col.close()


def test_performance_reads_purely_from_reasoning_revlog():
    col = getEmptyCol()
    # 25 attempts (~75% correct) logged only as cards + revlog, nothing in config
    for i in range(25):
        _log_reasoning(col, "chem_phys", f"stem {i}", correct=(i % 4 != 0))
    assert col.get_config(collect.PERF_CONFIG_KEY, []) == []  # config empty
    dash = collect.gather(col)
    assert not dash.performance.abstained  # 25 revlog outcomes clear the gate
    assert dash.performance.band is not None
    assert dash.performance.band.point > 0.5  # reflects the ~75% correct rate
    col.close()


# --------------------------------------------------------------------------- #
# per-device metacognition merge (confidence / miss reason survive two devices)
# --------------------------------------------------------------------------- #
def test_metacognition_writes_to_stable_per_device_key():
    col = getEmptyCol()
    k1 = collect.record_metacognition(col, "chem_phys", True, confidence="sure")
    k2 = collect.record_metacognition(col, "bio_biochem", False, reason="trap")
    # same device -> same key, and it is a per-device key, not the legacy single list
    assert k1 == k2
    assert k1.startswith(collect.PERF_DEVICE_PREFIX)
    assert k1 != collect.PERF_CONFIG_KEY
    assert collect._device_id(col) == collect._device_id(col)  # stable per device
    stored = col.get_config(k1, [])
    assert len(stored) == 2  # both records land in this device's own list
    col.close()


def test_two_device_metacognition_merges_without_clobber_or_double_count():
    col = getEmptyCol()
    # two sync-safe outcomes live in the revlog (device-independent, union-merged)
    rid_a = _log_reasoning(col, "chem_phys", "q-from-device-a", correct=True)
    rid_b = _log_reasoning(col, "bio_biochem", "q-from-device-b", correct=False)
    assert rid_a and rid_b
    key_a = collect.PERF_DEVICE_PREFIX + "device-a"
    key_b = collect.PERF_DEVICE_PREFIX + "device-b"
    # after a two-device offline sync BOTH per-device keys are present in the merged
    # config -- distinct keys never clobber (unlike one shared list).
    col.set_config(
        key_a,
        [
            {"section": "chem_phys", "correct": True, "confidence": "sure", "revlog_id": rid_a},
            {"section": "psych_soc", "correct": False, "reason": "trap"},  # config-only
        ],
    )
    col.set_config(
        key_b,
        [
            {"section": "bio_biochem", "correct": False, "confidence": "guess", "revlog_id": rid_b},
            {"section": "psych_soc", "correct": True, "confidence": "unsure"},  # config-only
        ],
    )
    merged = collect._merged_outcomes(col)
    # 2 revlog outcomes (enriched, each counted once) + 2 config-only = 4, no dup
    assert len(merged) == 4
    by_rid = {o.get("revlog_id"): o for o in merged if isinstance(o.get("revlog_id"), int)}
    # both devices' metacognition survived, linked to the right revlog outcome
    assert by_rid[rid_a]["confidence"] == "sure"
    assert by_rid[rid_b]["confidence"] == "guess"
    # the outcome itself always comes from the revlog, never the config
    assert by_rid[rid_a]["correct"] is True
    assert by_rid[rid_b]["correct"] is False
    # both config-only notes (one per device) survived too
    assert any(o.get("reason") == "trap" for o in merged)
    assert any(o.get("confidence") == "unsure" for o in merged)
    col.close()


def test_legacy_single_key_would_clobber_two_devices():
    # Contrast: the OLD single-list store loses device A's write the moment device B
    # writes -- exactly the last-writer-wins clobber the per-device keys fix.
    col = getEmptyCol()
    col.set_config(collect.PERF_CONFIG_KEY, [{"section": "chem_phys", "correct": True}])
    col.set_config(collect.PERF_CONFIG_KEY, [{"section": "bio_biochem", "correct": False}])
    surviving = col.get_config(collect.PERF_CONFIG_KEY, [])
    assert len(surviving) == 1 and surviving[0]["section"] == "bio_biochem"
    col.close()


def test_per_device_metacognition_does_not_double_count_performance():
    col = getEmptyCol()
    # 22 outcomes in the revlog; their metacognition split across two device keys.
    rids = [_log_reasoning(col, "chem_phys", f"dc q{i}", correct=(i % 3 != 0)) for i in range(22)]
    half = len(rids) // 2
    collect.set_perf_outcomes(col, [])  # legacy empty
    col.set_config(
        collect.PERF_DEVICE_PREFIX + "dev-1",
        [{"section": "chem_phys", "correct": True, "confidence": "sure", "revlog_id": r} for r in rids[:half]],
    )
    col.set_config(
        collect.PERF_DEVICE_PREFIX + "dev-2",
        [{"section": "chem_phys", "correct": True, "confidence": "guess", "revlog_id": r} for r in rids[half:]],
    )
    dash = collect.gather(col)
    # performance counts each revlog outcome once (22), not 44 (revlog + both keys)
    assert dash.performance.n == 22
    assert not dash.performance.abstained
    col.close()


# --------------------------------------------------------------------------- #
# card-level paraphrase test (per-concept transfer gap surfaced on the dashboard)
# --------------------------------------------------------------------------- #
def test_reasoning_card_carries_linked_concept_tag():
    col = getEmptyCol()
    rid = collect.log_reasoning_outcome(
        col, "bio_biochem", "linked q", "a", "e", True, 1000, concept="1A"
    )
    assert rid is not None
    ro = collect._revlog_outcomes(col)
    assert len(ro) == 1
    assert ro[0]["concept"] == "1A"
    assert ro[0]["section"] == "bio_biochem"
    col.close()


def test_fluency_items_surface_per_concept_transfer_gap():
    col = getEmptyCol()
    # strong recall on concept 1A (high-stability, recently reviewed cards)
    for i in range(4):
        _add_review_card(col, ["mcat::1A"], 60.0, 5, f"1a{i}")
    # its reworded application variants are mostly missed -> a fluency illusion
    for i in range(5):
        collect.log_reasoning_outcome(
            col, "bio_biochem", f"applied 1A q{i}", "ans", "why",
            correct=(i == 0), ms=1000, concept="1A",
        )
    dash = collect.gather(col)
    assert dash.fluency_items  # at least one concept surfaced
    top = dash.fluency_items[0]
    assert top.concept_id == "1A"
    assert top.section == "bio_biochem"
    assert top.n_app == 5
    assert top.recall > top.application  # recalls it but cannot yet apply it
    assert top.fluency_risk is True
    # the section-level paraphrase test still exists alongside the per-concept one
    assert isinstance(dash.transfer, dict)
    col.close()


# --------------------------------------------------------------------------- #
# perf: memoized tag->concept matching (identical results, O(distinct tags))
# --------------------------------------------------------------------------- #
def test_match_tag_memo_matches_the_uncached_result():
    outline = Outline.load()
    samples = [
        "mcat::bio_biochem::1A",
        "mcat::4E",
        "mcat::psych_soc::6B",
        "totally::unmapped::tag",
        "",
    ]
    for tag in samples:
        expected = outline._match_tag_uncached(tag)
        assert outline.match_tag(tag) == expected  # first call computes
        assert outline.match_tag(tag) == expected  # second call hits the cache
        assert tag in outline._match_cache
    # the cache is instance-scoped, so a fresh load starts empty (no cross-version leak)
    assert Outline.load()._match_cache == {}


# --------------------------------------------------------------------------- #
# perf: skip the reasoning-outcome revlog query when there are no reasoning cards
# --------------------------------------------------------------------------- #
def test_has_reasoning_cards_detects_presence():
    col = getEmptyCol()
    assert collect._has_reasoning_cards(col) is False
    _log_reasoning(col, "chem_phys", "a reasoning q", correct=True)
    assert collect._has_reasoning_cards(col) is True
    col.close()


def test_merged_outcomes_skips_revlog_query_when_no_reasoning_cards():
    col = getEmptyCol()
    # a legacy config-only outcome and zero reasoning anchor cards
    col.set_config(collect.PERF_CONFIG_KEY, [{"section": "chem_phys", "correct": True}])
    orig = collect._revlog_outcomes

    def boom(_c):
        raise AssertionError("revlog query must be skipped when no reasoning cards")

    collect._revlog_outcomes = boom
    try:
        merged = collect._merged_outcomes(col)
    finally:
        collect._revlog_outcomes = orig
    # identical result to before the guard: the config-only outcome, nothing lost
    assert merged == [{"section": "chem_phys", "correct": True}]
    col.close()


def test_merged_outcomes_still_reads_revlog_when_reasoning_cards_exist():
    col = getEmptyCol()
    for i in range(3):
        _log_reasoning(col, "chem_phys", f"stem {i}", correct=(i % 2 == 0))
    merged = collect._merged_outcomes(col)  # guard passes -> revlog is read
    assert len(merged) == 3
    assert sum(1 for o in merged if o["correct"]) == 2
    col.close()


# --------------------------------------------------------------------------- #
# confusability matrix: bias the Rust Mixed interleaver toward confused topics
# --------------------------------------------------------------------------- #
def test_confusability_pairs_target_most_comissed_within_section():
    concept_tags = {"A": ["mcat::s::A"], "B": ["mcat::s::B"], "C": ["mcat::s::C"]}
    outcomes = (
        [{"section": "s", "concept": "A", "correct": False}] * 3
        + [{"section": "s", "concept": "B", "correct": False}] * 3
        + [{"section": "s", "concept": "C", "correct": False}] * 1
    )
    pairs = collect.confusability_pairs(outcomes, concept_tags, CFG)
    # pairs are keyed by the review-bucket TAGS (not the concept ids)
    assert all(p["topic_a"].startswith("mcat::") for p in pairs)
    w = {(p["topic_a"], p["topic_b"]): p["weight"] for p in pairs}
    ab = w[("mcat::s::A", "mcat::s::B")]
    ac = w[("mcat::s::A", "mcat::s::C")]
    bc = w[("mcat::s::B", "mcat::s::C")]
    # A and B are both missed most -> the most-confusable (highest-weight) pair
    assert ab > ac and ab > bc
    assert ab == 1.0  # normalized to the max co-miss strength


def test_confusability_uses_only_missed_items():
    concept_tags = {"A": ["mcat::s::A"], "B": ["mcat::s::B"]}
    outcomes = (
        [{"section": "s", "concept": "A", "correct": True}] * 5  # correct -> ignored
        + [{"section": "s", "concept": "B", "correct": True}] * 5
        + [{"section": "s", "concept": "A", "correct": False}] * 2
        + [{"section": "s", "concept": "B", "correct": False}] * 2
    )
    pairs = collect.confusability_pairs(outcomes, concept_tags, CFG)
    assert len(pairs) == 1
    assert pairs[0]["weight"] == 1.0


def test_confusability_abstains_when_error_data_is_thin():
    concept_tags = {"A": ["mcat::s::A"], "B": ["mcat::s::B"]}
    # only 2 missed items, below cfg.min_mistakes -> empty map == naive interleaving
    outcomes = [
        {"section": "s", "concept": "A", "correct": False},
        {"section": "s", "concept": "B", "correct": False},
    ]
    assert collect.confusability_pairs(outcomes, concept_tags, CFG) == []


def test_confusability_only_pairs_concepts_within_the_same_section():
    concept_tags = {"A": ["mcat::chem_phys::A"], "B": ["mcat::bio_biochem::B"]}
    outcomes = (
        [{"section": "chem_phys", "concept": "A", "correct": False}] * 2
        + [{"section": "bio_biochem", "concept": "B", "correct": False}] * 2
    )
    # clears the give-up gate, but the two concepts are in different sections
    assert collect.confusability_pairs(outcomes, concept_tags, CFG) == []


def test_interleave_priorities_lead_with_the_most_missed_topic():
    concept_tags = {"A": ["mcat::s::A"], "B": ["mcat::s::B"], "C": ["mcat::s::C"]}
    outcomes = (
        [{"section": "s", "concept": "C", "correct": False}] * 5  # missed most -> leads
        + [{"section": "s", "concept": "A", "correct": False}] * 2
        + [{"section": "s", "concept": "A", "correct": True}] * 4  # correct -> ignored
    )
    pri = collect.interleave_priorities(outcomes, concept_tags, CFG)
    by_tag = {p["topic"]: p["weight"] for p in pri}
    assert by_tag["mcat::s::C"] == 1.0  # weakest topic leads the rotation
    assert by_tag["mcat::s::A"] < by_tag["mcat::s::C"]
    assert "mcat::s::B" not in by_tag  # never missed -> no priority


def test_interleave_priorities_abstain_below_the_gate():
    concept_tags = {"A": ["mcat::s::A"], "B": ["mcat::s::B"]}
    thin = [
        {"section": "s", "concept": "A", "correct": False},
        {"section": "s", "concept": "B", "correct": False},
    ]  # 2 misses, below cfg.min_mistakes -> empty == naive seed-chosen start
    assert collect.interleave_priorities(thin, concept_tags, CFG) == []


def test_interleave_priorities_ignore_topics_without_a_review_bucket():
    concept_tags = {"A": ["mcat::s::A"]}  # B teaches no card -> nothing to lead
    outcomes = (
        [{"section": "s", "concept": "A", "correct": False}] * 4
        + [{"section": "s", "concept": "B", "correct": False}] * 4
    )
    pri = collect.interleave_priorities(outcomes, concept_tags, CFG)
    assert [p["topic"] for p in pri] == ["mcat::s::A"]


def test_confusability_ignores_concepts_without_a_review_bucket():
    concept_tags = {"A": ["mcat::s::A"]}  # B teaches no card -> no bucket to reorder
    outcomes = (
        [{"section": "s", "concept": "A", "correct": False}] * 2
        + [{"section": "s", "concept": "B", "correct": False}] * 2
    )
    assert collect.confusability_pairs(outcomes, concept_tags, CFG) == []


def test_set_interleave_confusability_writes_tag_keyed_pairs_and_preserves_config():
    col = getEmptyCol()
    # real review buckets for two confusable bio concepts
    for i in range(3):
        _add_review_card(col, ["mcat::bio_biochem::1A"], 40.0, 10, f"1a{i}")
        _add_review_card(col, ["mcat::bio_biochem::1D"], 40.0, 10, f"1d{i}")
    # interleave already turned on (as the Rust toggle would have written it)
    col.set_config(
        collect.INTERLEAVE_CONFIG_KEY,
        {"mode": "Mixed", "topic_tag_prefix": "mcat", "seed": 7},
    )
    # the student misses both concepts repeatedly on application items
    for i in range(3):
        collect.log_reasoning_outcome(
            col, "bio_biochem", f"q1a {i}", "a", "e", correct=False, ms=1000, concept="1A"
        )
        collect.log_reasoning_outcome(
            col, "bio_biochem", f"q1d {i}", "a", "e", correct=False, ms=1000, concept="1D"
        )
    pairs = collect.set_interleave_confusability(col)
    mcat_tags = sorted(t for t in col.tags.all() if t.startswith("mcat::"))
    assert len(pairs) == 1
    # keyed by the exact note tags the interleaver buckets on, sorted, weight 1.0
    assert [pairs[0]["topic_a"], pairs[0]["topic_b"]] == mcat_tags
    assert pairs[0]["weight"] == 1.0
    # merged into the SAME config blob: mode / prefix / seed are preserved
    stored = col.get_config(collect.INTERLEAVE_CONFIG_KEY)
    assert stored["mode"] == "Mixed"
    assert stored["topic_tag_prefix"] == "mcat"
    assert stored["seed"] == 7
    assert stored["confusability"] == pairs
    # write-once: an unchanged map must not rewrite the collection every refresh
    writes = []
    orig_set = col.set_config

    def counting_set(key, val):
        if key == collect.INTERLEAVE_CONFIG_KEY:
            writes.append(val)
        return orig_set(key, val)

    col.set_config = counting_set
    again = collect.set_interleave_confusability(col)
    assert again == pairs
    assert writes == []
    col.close()


def test_set_interleave_confusability_abstains_to_empty_without_creating_config():
    col = getEmptyCol()
    _add_review_card(col, ["mcat::bio_biochem::1A"], 40.0, 10, "solo")
    # one lonely miss: below the gate -> empty map, and no config invented for it
    collect.log_reasoning_outcome(
        col, "bio_biochem", "q", "a", "e", correct=False, ms=1000, concept="1A"
    )
    assert collect.set_interleave_confusability(col) == []
    assert col.get_config(collect.INTERLEAVE_CONFIG_KEY, None) is None
    col.close()
