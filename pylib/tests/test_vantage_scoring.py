# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — tests for the honest scoring core.

Pure-function tests: no Collection needed. They pin the invariants the brief
grades on — three separate ranged scores, the give-up rule, coverage gating,
the documented mapping, calibration (Brier), and the negative acceptance
criteria (no number below the line; 'how sure' never high when the evidence is
thin or the range is wide).
"""

from __future__ import annotations

import pytest

from anki.vantage import outline as outline_mod
from anki.vantage import scoring
from anki.vantage.scoring import (
    HIGH,
    INSUFFICIENT,
    SECTIONS,
    IrtItem,
    ScoringConfig,
    brier,
    calibration,
    concept_transfer_gaps,
    confidence_calibration,
    give_up,
    irt_estimate,
    irt_information,
    irt_next_item,
    irt_prob,
    irt_readiness,
    map_ability_to_scale,
    memory_score,
    mistake_taxonomy,
    pacing_coach,
    performance_score,
    readiness,
    study_pace,
    theta_to_scale,
    trajectory,
    transfer_gap,
)

CFG = ScoringConfig()


# --------------------------------------------------------------------------- #
# outline + coverage
# --------------------------------------------------------------------------- #
def test_outline_loads_all_three_sections():
    o = outline_mod.Outline.load()
    assert set(o.sections) == set(SECTIONS)
    assert len(o.concepts) == 31
    assert o.total_weight() > 0
    for s in SECTIONS:
        assert o.section_weight(s) > 0


def test_match_tag_exact_id_and_alias():
    o = outline_mod.Outline.load()
    assert o.match_tag("1A") == "1A"
    assert o.match_tag("mcat::4E") == "4E"
    assert o.match_tag("10a") == "10A"
    # aliases
    assert o.match_tag("amino_acids") == "1A"
    assert o.match_tag("mcat::chem::thermodynamics") == "5E"
    # no match
    assert o.match_tag("marked") is None
    assert o.match_tag("") is None


def test_weighted_coverage_bounds_and_sections():
    o = outline_mod.Outline.load()
    assert o.weighted_coverage([]) == 0.0
    all_ids = [c.id for c in o.concepts]
    assert o.weighted_coverage(all_ids) == pytest.approx(1.0)
    partial = o.covered_concepts(["1A", "1D", "4E"])
    assert partial == {"1A", "1D", "4E"}
    cov = o.weighted_coverage(partial)
    assert 0.0 < cov < 1.0
    by_sec = o.coverage_by_section(partial)
    assert set(by_sec) == set(SECTIONS)
    assert by_sec["bio_biochem"] > 0
    assert by_sec["psych_soc"] == 0.0
    # heaviest missing concept comes first
    missing = o.missing_concepts(partial)
    assert missing[0].weight >= missing[-1].weight


# --------------------------------------------------------------------------- #
# memory score
# --------------------------------------------------------------------------- #
def test_memory_abstains_below_min_cards():
    r = memory_score([0.9] * 5, coverage=0.3, cfg=CFG)
    assert r.abstained
    assert r.band is None
    assert r.how_sure == INSUFFICIENT


def test_memory_point_is_mean_and_range_brackets_it():
    vals = [0.8] * 100 + [0.6] * 100
    r = memory_score(vals, coverage=0.7, cfg=CFG)
    assert not r.abstained
    assert r.band is not None
    assert r.band.point == pytest.approx(0.70, abs=1e-6)
    assert r.band.low <= r.band.point <= r.band.high
    assert r.n == 200
    # deterministic normal approximation of the mean (mean +- z * SE), so the
    # mobile JS port reproduces the range bit-for-bit (no Monte-Carlo bootstrap)
    assert r.band.low == pytest.approx(0.688)
    assert r.band.high == pytest.approx(0.712)


def test_memory_is_deterministic():
    vals = [0.5, 0.9] * 60
    a = memory_score(vals, 0.7, CFG).band
    b = memory_score(vals, 0.7, CFG).band
    assert a == b
    # closed-form, no RNG: pins the exact cross-device band
    assert (a.point, a.low, a.high) == pytest.approx((0.7, 0.67, 0.73))


def test_memory_high_confidence_only_when_tight_and_plentiful():
    tight = memory_score([0.85] * 200, coverage=0.8, cfg=CFG)
    assert tight.how_sure == HIGH
    # NEGATIVE AC: wide spread must NOT read "high"
    wide = memory_score([0.1, 0.95] * 25, coverage=0.8, cfg=CFG)
    assert wide.how_sure != HIGH


# --------------------------------------------------------------------------- #
# performance score
# --------------------------------------------------------------------------- #
def test_performance_abstains_below_min_outcomes():
    r = performance_score([1, 0, 1], coverage=0.6, cfg=CFG)
    assert r.abstained
    assert r.band is None


def test_performance_point_and_interval():
    outcomes = [1] * 30 + [0] * 20  # 30/50 = 0.6
    r = performance_score(outcomes, coverage=0.6, cfg=CFG)
    assert not r.abstained
    assert r.band.point == pytest.approx(0.6, abs=1e-9)
    assert 0.0 <= r.band.low < r.band.point < r.band.high <= 1.0
    assert r.n == 50


# --------------------------------------------------------------------------- #
# give-up rule (readiness only, D10)
# --------------------------------------------------------------------------- #
def test_give_up_both_conditions_fail():
    abstain, reasons = give_up(n_reviews=10, coverage=0.10, cfg=CFG)
    assert abstain
    assert len(reasons) == 2


def test_give_up_reviews_ok_but_coverage_low():
    abstain, reasons = give_up(n_reviews=500, coverage=0.30, cfg=CFG)
    assert abstain
    assert len(reasons) == 1
    assert "coverage" in reasons[0]


def test_give_up_passes_when_both_met():
    abstain, reasons = give_up(n_reviews=500, coverage=0.80, cfg=CFG)
    assert not abstain
    assert reasons == []


# --------------------------------------------------------------------------- #
# readiness
# --------------------------------------------------------------------------- #
def _full_section_outcomes(acc=0.7, n=60):
    k = int(round(acc * n))
    outs = [1] * k + [0] * (n - k)
    return {s: list(outs) for s in SECTIONS}


def test_readiness_abstains_below_the_line_shows_no_number():
    # NEGATIVE AC 10.3.3: no readiness number below the give-up line.
    r = readiness(
        section_outcomes=_full_section_outcomes(),
        coverage=0.20,  # below 50%
        coverage_by_section={s: 0.2 for s in SECTIONS},
        n_reviews=1000,
        cfg=CFG,
    )
    assert r.abstained
    assert r.band is None
    assert r.how_sure == INSUFFICIENT
    assert any("coverage" in reason for reason in r.reasons)


def test_readiness_projects_partial_composite_when_gate_passes():
    r = readiness(
        section_outcomes=_full_section_outcomes(acc=0.75, n=80),
        coverage=0.70,
        coverage_by_section={s: 0.7 for s in SECTIONS},
        n_reviews=500,
        cfg=CFG,
    )
    assert not r.abstained
    assert r.band is not None
    # three sections each 118..132 -> partial composite in [354, 396], never 472..528
    assert 354.0 <= r.band.low <= r.band.point <= r.band.high <= 396.0
    assert r.extra["cars_modeled"] is False
    assert set(r.extra["modeled_sections"]) <= set(SECTIONS)
    sections = r.extra["sections"]
    for s, band in sections.items():
        assert 118.0 <= band.low <= band.point <= band.high <= 132.0
    # composite point == sum of section points (allow rounding slack)
    assert r.band.point == pytest.approx(
        sum(b.point for b in sections.values()), abs=0.3
    )


def test_readiness_is_deterministic():
    args = dict(
        section_outcomes=_full_section_outcomes(acc=0.68, n=70),
        coverage=0.66,
        coverage_by_section={s: 0.66 for s in SECTIONS},
        n_reviews=300,
        cfg=CFG,
    )
    a = readiness(**args)
    b = readiness(**args)
    assert a.band == b.band
    assert a.extra["sections"] == b.extra["sections"]


def test_readiness_not_high_confidence_when_coverage_thin():
    # NEGATIVE AC: even with tight per-section bands, coverage just over the gate
    # (below the high-confidence threshold) must not read "high".
    r = readiness(
        section_outcomes=_full_section_outcomes(acc=0.7, n=400),  # tight bands
        coverage=0.52,  # >= 0.50 gate, < 0.65 high threshold
        coverage_by_section={s: 0.52 for s in SECTIONS},
        n_reviews=1000,
        cfg=CFG,
    )
    assert not r.abstained
    assert r.how_sure != HIGH


# --------------------------------------------------------------------------- #
# mapping + calibration
# --------------------------------------------------------------------------- #
def test_map_ability_anchors_and_clamps():
    assert map_ability_to_scale(0.40, CFG) == pytest.approx(118.0)
    assert map_ability_to_scale(0.90, CFG) == pytest.approx(132.0)
    assert map_ability_to_scale(0.65, CFG) == pytest.approx(125.0)
    # clamps outside the anchor range
    assert map_ability_to_scale(0.0, CFG) == pytest.approx(118.0)
    assert map_ability_to_scale(1.0, CFG) == pytest.approx(132.0)
    # monotonic
    assert map_ability_to_scale(0.5, CFG) < map_ability_to_scale(0.7, CFG)


def test_brier_known_values():
    assert brier([(1.0, 1), (0.0, 0)]) == pytest.approx(0.0)
    assert brier([(1.0, 0), (0.0, 1)]) == pytest.approx(1.0)
    assert brier([(0.5, 1), (0.5, 0)]) == pytest.approx(0.25)


def test_wilson_interval_brackets_proportion():
    b = scoring.wilson_interval(30, 50, 0.90)
    assert b.low < b.point < b.high
    assert 0.0 <= b.low and b.high <= 1.0


# --------------------------------------------------------------------------- #
# paraphrase test (transfer gap: memory vs application)
# --------------------------------------------------------------------------- #
def test_transfer_gap_flags_fluency_illusion():
    # recall high, application low -> large gap -> fluency illusion flagged
    recall = {"bio_biochem": 0.9}
    app = {"bio_biochem": [1, 1, 0, 0, 1, 0, 1, 0, 1, 0]}  # 5/10 correct
    out = transfer_gap(recall, app, CFG)
    assert set(out) == {"bio_biochem"}
    t = out["bio_biochem"]
    assert t.recall == pytest.approx(0.9)
    assert t.application == pytest.approx(0.5)
    assert t.gap == pytest.approx(0.4)
    assert t.n_app == 10
    assert t.fluency_risk is True


def test_transfer_gap_no_flag_when_memory_and_application_align():
    recall = {"chem_phys": 0.8}
    app = {"chem_phys": [1] * 8 + [0] * 2}  # 0.8 correct
    t = transfer_gap(recall, app, CFG)["chem_phys"]
    assert t.gap == pytest.approx(0.0)
    assert t.fluency_risk is False


def test_transfer_gap_abstains_without_enough_application_items():
    # below min_outcomes_transfer -> excluded, never guesses
    assert transfer_gap({"psych_soc": 0.9}, {"psych_soc": [1, 0, 1]}, CFG) == {}


def test_transfer_gap_requires_a_memory_signal():
    # application data but no studied cards in the section -> excluded
    assert transfer_gap({}, {"chem_phys": [1] * 10}, CFG) == {}


# --------------------------------------------------------------------------- #
# readiness projection: exact calculation (worked examples)
# --------------------------------------------------------------------------- #
def _ok(k, n):
    return [1] * k + [0] * (n - k)


def test_readiness_section_points_equal_mapped_accuracy():
    # each section's projected score is exactly the documented map of its accuracy
    so = {
        "chem_phys": _ok(70, 100),  # 0.70 -> 126.4
        "bio_biochem": _ok(80, 100),  # 0.80 -> 129.2
        "psych_soc": _ok(60, 100),  # 0.60 -> 123.6
    }
    r = readiness(
        so, coverage=0.6, coverage_by_section={s: 0.6 for s in SECTIONS}, n_reviews=300, cfg=CFG
    )
    secs = r.extra["sections"]
    assert secs["chem_phys"].point == pytest.approx(126.4)
    assert secs["bio_biochem"].point == pytest.approx(129.2)
    assert secs["psych_soc"].point == pytest.approx(123.6)
    # composite point is the sum of the section points (3-section partial)
    assert r.band.point == pytest.approx(379.2, abs=0.15)
    # every section band sits inside 118..132 and brackets its point
    for b in secs.values():
        assert 118.0 <= b.low <= b.point <= b.high <= 132.0
    # the composite range brackets the composite point
    assert r.band.low <= r.band.point <= r.band.high


def test_readiness_range_narrows_with_more_evidence():
    args = dict(coverage=0.6, coverage_by_section={s: 0.6 for s in SECTIONS}, n_reviews=300, cfg=CFG)
    thin = readiness({s: _ok(7, 10) for s in SECTIONS}, **args)
    thick = readiness({s: _ok(700, 1000) for s in SECTIONS}, **args)
    assert thick.band.width < thin.band.width


def test_readiness_clamps_to_section_band():
    args = dict(coverage=0.6, coverage_by_section={s: 0.6 for s in SECTIONS}, n_reviews=300, cfg=CFG)
    assert readiness({s: _ok(100, 100) for s in SECTIONS}, **args).band.point == pytest.approx(396.0, abs=0.5)
    assert readiness({s: _ok(0, 100) for s in SECTIONS}, **args).band.point == pytest.approx(354.0, abs=0.5)


def test_readiness_combines_memory_and_reasoning():
    # memory (flashcards) priors the projection; reasoning (evidence) overrides it.
    # Pad a second section so the overall reasoning-evidence gate passes while
    # chem_phys stays thin (5 items) enough for the memory prior to move it.
    args = dict(coverage=0.6, coverage_by_section={s: 0.6 for s in SECTIONS}, n_reviews=300, cfg=CFG)
    mem = {"chem_phys": 0.9}
    thin = {"chem_phys": _ok(3, 5), "bio_biochem": _ok(9, 15)}  # 20 outcomes total
    p_uniform = readiness(thin, **args).extra["sections"]["chem_phys"].point
    p_memory = readiness(thin, **args, section_memory=mem).extra["sections"]["chem_phys"].point
    assert p_memory > p_uniform  # strong recall pulls a thin estimate upward
    # with plenty of reasoning data, the memory prior washes out
    thick = {"chem_phys": _ok(600, 1000)}  # 0.60 observed, lots of evidence
    p_thick = readiness(thick, **args, section_memory=mem).extra["sections"]["chem_phys"].point
    assert p_thick == pytest.approx(map_ability_to_scale(0.6, CFG), abs=0.5)


def test_readiness_abstains_when_reasoning_evidence_is_thin():
    # NEGATIVE AC: reviews + coverage clear the gate, but with too few application
    # items readiness must abstain, not quietly mirror the memory prior back.
    r = readiness(
        section_outcomes={"chem_phys": _ok(3, 5)},  # 5 < min_outcomes_performance
        coverage=0.70,
        coverage_by_section={s: 0.7 for s in SECTIONS},
        n_reviews=1000,
        cfg=CFG,
        section_memory={"chem_phys": 0.9},  # strong recall must not rescue it
    )
    assert r.abstained
    assert r.band is None
    assert r.how_sure == INSUFFICIENT
    assert any("application items" in reason for reason in r.reasons)


def test_readiness_excludes_a_section_with_too_few_outcomes():
    # a section below min_outcomes_readiness is left out of the composite, exactly
    # like a coverage-excluded section; the rest still project as a labeled partial
    r = readiness(
        section_outcomes={
            "chem_phys": _ok(14, 20),
            "bio_biochem": _ok(12, 20),
            "psych_soc": _ok(2, 3),  # below min_outcomes_readiness -> excluded
        },
        coverage=0.70,
        coverage_by_section={s: 0.7 for s in SECTIONS},
        n_reviews=1000,
        cfg=CFG,
    )
    assert not r.abstained
    assert set(r.extra["modeled_sections"]) == {"chem_phys", "bio_biochem"}
    assert "psych_soc" not in r.extra["sections"]
    assert r.band.point == pytest.approx(
        sum(b.point for b in r.extra["sections"].values()), abs=0.3
    )


# --------------------------------------------------------------------------- #
# calibration (reliability of the predicted probabilities)
# --------------------------------------------------------------------------- #
def test_calibration_abstains_below_threshold():
    c = calibration([(0.9, 1)] * (CFG.min_outcomes_calibration - 1), CFG)
    assert c.abstained and c.how_sure == INSUFFICIENT and c.brier is None


def test_calibration_flags_overconfidence():
    # predict 90% but only 60% come true -> not well calibrated, predictions high
    pairs = [(0.9, 1)] * 12 + [(0.9, 0)] * 8
    c = calibration(pairs, CFG)
    assert not c.abstained
    assert c.mean_predicted == pytest.approx(0.9)
    assert c.mean_observed == pytest.approx(0.6)
    assert c.well_calibrated is False


def test_calibration_accepts_honest_predictions():
    # predict 70% and 70% come true -> well calibrated, low Brier
    pairs = [(0.7, 1)] * 14 + [(0.7, 0)] * 6
    c = calibration(pairs, CFG)
    assert c.well_calibrated is True
    assert c.mean_predicted == pytest.approx(c.mean_observed, abs=CFG.calibration_well_within)


def test_calibration_bins_track_predicted_bands():
    # two prediction levels land in two separate reliability bins
    pairs = [(0.7, 1)] * 7 + [(0.7, 0)] * 3 + [(0.9, 1)] * 6 + [(0.9, 0)] * 4
    c = calibration(pairs, CFG)
    by_hi = {b.hi: b for b in c.bins}
    assert by_hi[0.8].pred_mean == pytest.approx(0.7) and by_hi[0.8].obs_rate == pytest.approx(0.7)
    assert by_hi[1.0].pred_mean == pytest.approx(0.9) and by_hi[1.0].obs_rate == pytest.approx(0.6)


# --------------------------------------------------------------------------- #
# study pace (days-to-exam + daily targets)
# --------------------------------------------------------------------------- #
def test_study_pace_abstains_without_a_date():
    p = study_pace(None, "2026-07-01", reviews_due=10, new_remaining=0, reasoning_done=0, cfg=CFG)
    assert p.has_exam_date is False and p.days_left is None and "exam date" in p.message


def test_study_pace_reasoning_goal_scales_with_exam_breadth():
    # 30 concepts still to get ready x 10 each = 300, over 30 days -> 10/day.
    # reasoning_remaining stays the confidence milestone (60 - 12 = 48).
    p = study_pace("2026-07-31", "2026-07-01", reviews_due=25, new_remaining=90,
                   reasoning_done=12, cfg=CFG, concepts_to_practice=30)
    assert p.has_exam_date and p.days_left == 30 and p.passed is False
    assert p.reviews_due == 25
    assert p.new_per_day == 3  # ceil(90 / 30)
    assert p.reasoning_remaining == 48  # 60 - 12, the "confident score" milestone
    assert p.reasoning_per_day == 10  # ceil(30 * 10 / 30)


def test_study_pace_reasoning_goal_shrinks_with_fewer_concepts_left():
    # Same 90 days: more concepts left -> a bigger daily goal.
    many = study_pace("2026-09-29", "2026-07-01", reviews_due=0, new_remaining=0,
                      reasoning_done=0, cfg=CFG, concepts_to_practice=30)
    few = study_pace("2026-09-29", "2026-07-01", reviews_due=0, new_remaining=0,
                     reasoning_done=0, cfg=CFG, concepts_to_practice=6)
    assert many.reasoning_per_day == 4  # ceil(300 / 90)
    assert few.reasoning_per_day == CFG.pace_reasoning_floor  # ceil(60/90)=1 -> floored to 3
    assert many.reasoning_per_day > few.reasoning_per_day


def test_study_pace_reasoning_never_dips_below_the_floor():
    # A distant exam with almost no breadth left still recommends a few a day.
    p = study_pace("2026-07-01", "2026-01-01", reviews_due=5, new_remaining=0,
                   reasoning_done=0, cfg=CFG, concepts_to_practice=1)
    assert p.days_left == 181
    assert p.reasoning_per_day == CFG.pace_reasoning_floor  # max(3, ceil(10/181)) == 3


def test_study_pace_flashcards_ramp_toward_exam():
    # Flashcards hold at the FSRS-due count far out, then ramp to a full pass as
    # the exam nears (deck of 4 new + 86 studied = 90 cards to get through).
    far = study_pace("2026-08-30", "2026-07-01", reviews_due=19, new_remaining=4,
                     reasoning_done=0, cfg=CFG, cards_studied=86)  # 60 days
    near = study_pace("2026-07-04", "2026-07-01", reviews_due=19, new_remaining=4,
                      reasoning_done=0, cfg=CFG, cards_studied=86)  # 3 days
    assert far.flashcards_per_day == 19  # max(19, ceil(90/60)=2)
    assert near.flashcards_per_day == 30  # max(19, ceil(90/3)=30)
    assert near.flashcards_per_day > far.flashcards_per_day


def test_study_pace_flags_a_past_date():
    p = study_pace("2026-06-01", "2026-07-01", reviews_due=5, new_remaining=0, reasoning_done=0, cfg=CFG)
    assert p.has_exam_date and p.passed and p.days_left == -30 and "passed" in p.message


def test_study_pace_carries_today_progress_through_every_branch():
    # reasoning_today is the day's practice count that drives the "X of Y today"
    # counter; it is display-only and must survive on the abstain, past-date, and
    # live branches alike (it never changes the pace math).
    live = study_pace("2026-07-31", "2026-07-01", reviews_due=0, new_remaining=0,
                      reasoning_done=12, cfg=CFG, concepts_to_practice=30, reasoning_today=7)
    assert live.reasoning_today == 7 and live.reasoning_per_day == 10  # unaffected by today's count
    no_date = study_pace(None, "2026-07-01", reviews_due=0, new_remaining=0,
                         reasoning_done=0, cfg=CFG, reasoning_today=4)
    assert no_date.reasoning_today == 4 and no_date.has_exam_date is False
    passed = study_pace("2026-06-01", "2026-07-01", reviews_due=0, new_remaining=0,
                        reasoning_done=0, cfg=CFG, reasoning_today=2)
    assert passed.reasoning_today == 2 and passed.passed
    # Default stays 0 for callers that don't track it (e.g. older collections).
    assert study_pace("2026-07-31", "2026-07-01", reviews_due=0, new_remaining=0,
                      reasoning_done=0, cfg=CFG).reasoning_today == 0


def test_study_pace_handles_exam_today_without_dividing_by_zero():
    p = study_pace("2026-07-01", "2026-07-01", reviews_due=5, new_remaining=10,
                   reasoning_done=0, cfg=CFG, concepts_to_practice=30)
    assert p.days_left == 0 and p.new_per_day == 10
    assert p.reasoning_per_day == 30 * CFG.pace_reasoning_per_concept


# --------------------------------------------------------------------------- #
# confidence calibration (metacognition)
# --------------------------------------------------------------------------- #
def test_confidence_abstains_below_threshold():
    c = confidence_calibration([("sure", 1)] * 5, CFG)
    assert c.abstained and c.levels == []


def test_confidence_flags_overconfidence():
    # 10 "sure" but only 50% right -> overconfident
    items = [("sure", 1)] * 5 + [("sure", 0)] * 5
    c = confidence_calibration(items, CFG)
    assert not c.abstained
    assert "sure" in c.insight.lower()
    sure = next(lv for lv in c.levels if lv.level == "sure")
    assert sure.rate == pytest.approx(0.5)


def test_confidence_flags_underconfidence():
    # 12 "guess" but 75% right -> too cautious
    items = [("guess", 1)] * 9 + [("guess", 0)] * 3
    c = confidence_calibration(items, CFG)
    assert not c.abstained and "guess" in c.insight.lower()


# --------------------------------------------------------------------------- #
# mistake taxonomy (how you lose points)
# --------------------------------------------------------------------------- #
def test_mistake_taxonomy_abstains_below_threshold():
    m = mistake_taxonomy([("psych_soc", "trap")] * 3, CFG)
    assert m.abstained and m.top_reason is None


def test_mistake_taxonomy_finds_top_reason_and_section():
    wrong = (
        [("psych_soc", "trap")] * 4
        + [("chem_phys", "content")] * 2
        + [("psych_soc", "misread")]
    )
    m = mistake_taxonomy(wrong, CFG)
    assert not m.abstained and m.n_wrong == 7
    assert m.top_reason == "trap" and m.top_section == "psych_soc"
    assert m.by_reason["trap"] == 4


# --------------------------------------------------------------------------- #
# pacing coach
# --------------------------------------------------------------------------- #
def test_pacing_abstains_below_threshold():
    p = pacing_coach([("chem_phys", 90000)] * 5, CFG)
    assert p.abstained


def test_pacing_flags_running_out_of_time():
    # chem/phys budget is 95min/59q ~= 96.6s; 150s/q is too slow
    items = [("chem_phys", 150000)] * 8
    p = pacing_coach(items, CFG)
    assert not p.abstained
    sp = next(s for s in p.sections if s.section == "chem_phys")
    assert sp.on_pace is False and sp.projected_left > 0 and p.overall_on_pace is False


def test_pacing_on_pace_finishes_with_spare():
    items = [("bio_biochem", 70000)] * 8  # 70s < ~96.6s budget
    p = pacing_coach(items, CFG)
    sp = next(s for s in p.sections if s.section == "bio_biochem")
    assert sp.on_pace is True and sp.projected_left == 0 and sp.spare_min > 0


# --------------------------------------------------------------------------- #
# score trajectory
# --------------------------------------------------------------------------- #
def test_trajectory_abstains_without_target_or_history():
    assert trajectory([], None, 30, "psych_soc", CFG).abstained
    one = [{"d": "2026-07-01", "point": 380.0}]
    assert trajectory(one, 400, 30, "psych_soc", CFG).abstained


def test_trajectory_projects_and_compares_to_target():
    # +2 points/day over 5 days; 3 days to exam -> ~ +6 from the latest point,
    # which stays inside the 354..396 band (no clamp).
    hist = [{"d": f"2026-07-0{i}", "point": 380.0 + 2 * (i - 1)} for i in range(1, 6)]
    t = trajectory(hist, 390, 3, "psych_soc", CFG)
    assert not t.abstained
    assert t.projected == pytest.approx(388.0 + 6.0, abs=0.5)  # latest 388 + 2*3
    assert t.on_pace is True and t.per_week == pytest.approx(14.0, abs=0.1)
    assert t.weakest_section == "psych_soc"


def test_trajectory_anchors_on_most_recent_by_date():
    # history arrives out of order: the base is the latest DATE's point (382),
    # not the last entry in list order (380).
    hist = [
        {"d": "2026-07-05", "point": 382.0},
        {"d": "2026-07-01", "point": 380.0},
    ]
    t = trajectory(hist, 390, 0, "chem_phys", CFG)
    assert not t.abstained
    assert t.projected == pytest.approx(382.0, abs=0.5)  # anchored on 07-05, not 07-01


def test_trajectory_clamps_to_three_section_band():
    # a steep recent slope can't project past the 3-section maximum (3 * 132 = 396).
    # Target is on the 3-section scale so it's the clamp, not the scale gate, we test.
    hist = [{"d": f"2026-07-0{i}", "point": 380.0 + 4 * (i - 1)} for i in range(1, 6)]
    t = trajectory(hist, 390, 30, "bio_biochem", CFG)
    assert not t.abstained
    assert t.projected == pytest.approx(396.0)  # clamped to the band ceiling


def test_trajectory_abstains_when_target_is_off_the_current_scale():
    # A full-scale target (472-528) can't be compared to a 3-section projection
    # (354-396): the trajectory abstains and asks for an in-scale target rather than
    # always reading "behind". Once CARS lifts it to 4 sections, 500 becomes valid.
    hist = [{"d": f"2026-07-0{i}", "point": 380.0} for i in range(1, 6)]
    t3 = trajectory(hist, 500, 30, "bio_biochem", CFG, n_sections=3)
    assert t3.abstained and t3.scale_lo == 354 and t3.scale_hi == 396
    t4 = trajectory(hist, 500, 30, "bio_biochem", CFG, n_sections=4)
    assert not t4.abstained and t4.scale_lo == 472 and t4.scale_hi == 528


# --------------------------------------------------------------------------- #
# IRT latent-ability readiness (2PL, EAP over a fixed quadrature grid)
# --------------------------------------------------------------------------- #
def _irt_items(k, n):
    return [IrtItem(1)] * k + [IrtItem(0)] * (n - k)


def test_irt_prob_is_logistic():
    assert irt_prob(0.0, 1.0, 0.0) == pytest.approx(0.5)  # at difficulty -> 50/50
    assert irt_prob(5.0, 1.0, 0.0) > 0.99  # far above difficulty -> near-certain
    assert irt_prob(-5.0, 1.0, 0.0) < 0.01


def test_theta_to_scale_anchors_clamps_and_monotonic():
    assert theta_to_scale(0.0, CFG) == pytest.approx(125.0)  # average ability = midpoint
    assert theta_to_scale(10.0, CFG) == pytest.approx(132.0)  # clamps at the ceiling
    assert theta_to_scale(-10.0, CFG) == pytest.approx(118.0)  # clamps at the floor
    assert theta_to_scale(-0.5, CFG) < theta_to_scale(0.5, CFG)  # strictly increasing


def test_irt_estimate_theta_monotonic_in_accuracy():
    # IRT MONOTONICITY: higher application accuracy -> higher latent ability ->
    # higher section score.
    low = irt_estimate(_irt_items(60, 100), CFG)
    mid = irt_estimate(_irt_items(70, 100), CFG)
    high = irt_estimate(_irt_items(80, 100), CFG)
    assert low.theta < mid.theta < high.theta
    assert (
        theta_to_scale(low.theta, CFG)
        < theta_to_scale(mid.theta, CFG)
        < theta_to_scale(high.theta, CFG)
    )


def test_irt_posterior_sd_widens_with_less_data():
    # POSTERIOR SD WIDENS WITH LESS DATA: same accuracy, fewer items -> wider band.
    few = irt_estimate(_irt_items(6, 8), CFG)  # 75% over 8 items
    many = irt_estimate(_irt_items(150, 200), CFG)  # 75% over 200 items
    assert many.theta_sd < few.theta_sd
    assert few.theta > 0 and many.theta > 0


def test_irt_estimate_is_deterministic_and_reproducible():
    # DESKTOP-REPRODUCIBLE DETERMINISM: no PRNG, so repeated calls are identical and
    # a symmetric response set pins ability exactly at the prior mean (a value the
    # mobile JS port must reproduce bit-for-bit).
    a = irt_estimate(_irt_items(70, 100), CFG)
    b = irt_estimate(_irt_items(70, 100), CFG)
    assert (a.theta, a.theta_sd, a.information) == (b.theta, b.theta_sd, b.information)
    sym = irt_estimate(_irt_items(10, 20), CFG)
    assert sym.theta == pytest.approx(0.0, abs=1e-12)
    assert sym.information == pytest.approx(5.0)  # 20 items * a^2 * 0.5 * 0.5


def test_irt_information_and_next_item_pick_most_diagnostic():
    # ADAPTIVE NEXT ITEM: Fisher information is maximal for the item nearest the
    # student's current ability, so next-item returns that index.
    pool = [IrtItem(1, b=-2.0), IrtItem(1, b=0.0), IrtItem(1, b=2.0)]
    assert irt_next_item(pool, 0.0, CFG) == 1
    assert irt_next_item(pool, 2.0, CFG) == 2
    assert irt_next_item(pool, -2.0, CFG) == 0
    assert irt_next_item([], 0.0, CFG) is None
    # info peaks at p = 0.5 (item difficulty == ability)
    assert irt_information(0.0, 1.0, 0.0) == pytest.approx(0.25)
    assert irt_information(0.0, 1.0, 3.0) < irt_information(0.0, 1.0, 0.0)


def test_irt_readiness_partial_composite_and_bands():
    so = {
        "chem_phys": _irt_items(70, 100),
        "bio_biochem": _irt_items(80, 100),
        "psych_soc": _irt_items(60, 100),
    }
    r = irt_readiness(
        so, coverage=0.66, coverage_by_section={s: 0.66 for s in SECTIONS},
        n_reviews=300, cfg=CFG,
    )
    assert not r.abstained
    # 3-section partial in [354, 396]; never a 472..528 total
    assert 354.0 <= r.band.low <= r.band.point <= r.band.high <= 396.0
    assert r.extra["cars_modeled"] is False
    assert r.extra["model"] == "irt_2pl_eap"
    for band in r.extra["sections"].values():
        assert 118.0 <= band.low <= band.point <= band.high <= 132.0
    # every usable section exposes its latent estimate for adaptive practice
    assert set(r.extra["irt"]) == set(r.extra["modeled_sections"])
    # deterministic + cross-device reproducible: pinned band values
    assert (r.band.point, r.band.low, r.band.high) == pytest.approx((382.7, 380.8, 384.6))


def test_irt_readiness_abstains_below_give_up_line():
    # NEGATIVE AC: the give-up gate is preserved (coverage below 50% -> no number).
    r = irt_readiness(
        {s: _irt_items(70, 100) for s in SECTIONS},
        coverage=0.20, coverage_by_section={s: 0.2 for s in SECTIONS},
        n_reviews=1000, cfg=CFG,
    )
    assert r.abstained and r.band is None and r.how_sure == INSUFFICIENT
    assert any("coverage" in reason for reason in r.reasons)


def test_irt_readiness_keeps_low_information_section_with_range():
    # OPTION A: a section the student aces carries little Fisher information, so IRT
    # can't pin the exact score -- it is kept with an honest (wide) range, not
    # dropped. Sections gate on item COUNT (like the classic path), not information,
    # so a well-answered section always shows.
    r = irt_readiness(
        {"chem_phys": _irt_items(18, 18),  # aced -> low info, but >= min items -> kept
         "bio_biochem": _irt_items(12, 20)},  # mixed -> kept
        coverage=0.70, coverage_by_section={s: 0.7 for s in SECTIONS},
        n_reviews=1000, cfg=CFG,
    )
    assert not r.abstained
    assert set(r.extra["modeled_sections"]) == {"chem_phys", "bio_biochem"}
    assert "chem_phys" in r.extra["sections"]  # aced section is not dropped


def test_irt_readiness_range_narrows_with_more_evidence():
    args = dict(
        coverage=0.66, coverage_by_section={s: 0.66 for s in SECTIONS},
        n_reviews=300, cfg=CFG,
    )
    thin = irt_readiness({s: _irt_items(21, 30) for s in SECTIONS}, **args)
    thick = irt_readiness({s: _irt_items(700, 1000) for s in SECTIONS}, **args)
    assert thick.band.width < thin.band.width


def test_irt_readiness_excludes_thin_section_keeps_rest():
    # a section below the item-count line is excluded like a coverage-excluded one;
    # the rest still project as a labeled partial.
    r = irt_readiness(
        {
            "chem_phys": _irt_items(70, 100),
            "bio_biochem": _irt_items(80, 100),
            "psych_soc": _irt_items(2, 3),  # only 3 items (< min_outcomes_readiness) -> excluded
        },
        coverage=0.70, coverage_by_section={s: 0.7 for s in SECTIONS},
        n_reviews=1000, cfg=CFG,
    )
    assert not r.abstained
    assert set(r.extra["modeled_sections"]) == {"chem_phys", "bio_biochem"}
    assert "psych_soc" not in r.extra["sections"]


# --------------------------------------------------------------------------- #
# card-level paraphrase test (per-concept transfer gap)
# --------------------------------------------------------------------------- #
def test_concept_transfer_gaps_ranks_fluency_illusions_first():
    recall = {"1A": 0.95, "1D": 0.70, "2A": 0.60}
    app = {
        "1A": [0, 0, 1, 0],  # 0.25 applied -> 0.70 gap (a fluency illusion)
        "1D": [1, 1, 1, 0],  # 0.75 applied -> slight negative gap
        "2A": [1, 1, 1, 1],  # applies better than it recalls -> negative gap
    }
    sec = {"1A": "bio_biochem", "1D": "bio_biochem", "2A": "bio_biochem"}
    out = concept_transfer_gaps(recall, app, sec, CFG)
    assert [t.concept_id for t in out] == ["1A", "1D", "2A"]  # worst gap first
    assert out[0].gap == pytest.approx(0.70)
    assert out[0].recall == pytest.approx(0.95)
    assert out[0].application == pytest.approx(0.25)
    assert out[0].section == "bio_biochem"
    assert out[0].fluency_risk is True
    assert out[-1].fluency_risk is False


def test_concept_transfer_gaps_needs_memory_and_enough_items():
    # too few application items for the concept -> excluded (never guesses)
    assert (
        concept_transfer_gaps({"1A": 0.9}, {"1A": [1, 0]}, {"1A": "bio_biochem"}, CFG)
        == []
    )
    # application items but no memory signal for the concept -> excluded
    assert (
        concept_transfer_gaps({}, {"1A": [1, 0, 1]}, {"1A": "bio_biochem"}, CFG) == []
    )
