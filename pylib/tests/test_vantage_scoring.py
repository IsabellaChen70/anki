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
    ScoringConfig,
    brier,
    give_up,
    map_ability_to_scale,
    memory_score,
    performance_score,
    readiness,
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


def test_memory_is_deterministic():
    vals = [0.5, 0.9] * 60
    a = memory_score(vals, 0.7, CFG).band
    b = memory_score(vals, 0.7, CFG).band
    assert a == b


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
