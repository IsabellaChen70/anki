# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — CARS labeling honesty.

The scoring core can model CARS once the student has enough real CARS practice
(the IRT path sets extra["cars_modeled"] = True and a full 4-section scale_note).
When it does, the numbers are real, so the UI/report labels must match: they may
NOT keep claiming "CARS not modeled" / a 3-section partial. These tests pin the
consumers (render payload, home-card summary, CLI report) to the REAL computed
flag, in both directions, and also confirm the core actually sets the flag so the
fix is grounded in real behavior, not an assumption.
"""

from __future__ import annotations

import importlib.util
import pathlib

from anki.vantage.report import _readiness_block
from anki.vantage.scoring import (
    Band,
    IrtItem,
    ScoreResult,
    ScoringConfig,
    irt_readiness,
    readiness,
)

_REPO = pathlib.Path(__file__).resolve().parents[2]
_RENDER_PATH = _REPO / "vantage_addon" / "render.py"


def _load_render():
    """Load vantage_addon/render.py in isolation.

    render.py is documented as pure/headless (its anki + vantage_core imports live
    inside functions we don't call here), so we load it straight from its file to
    avoid importing the add-on package, which pulls in aqt/Qt.
    """
    spec = importlib.util.spec_from_file_location("vantage_render_under_test", _RENDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


render = _load_render()


def _readiness_result(cars_modeled: bool) -> ScoreResult:
    """A live (non-abstained) readiness ScoreResult shaped exactly like the IRT
    path produces it, with CARS either in or out of the composite."""
    sections = {
        "chem_phys": Band(124.0, 120.0, 128.0),
        "bio_biochem": Band(126.0, 122.0, 129.0),
        "psych_soc": Band(125.0, 121.0, 128.0),
    }
    modeled = ["chem_phys", "bio_biochem", "psych_soc"]
    if cars_modeled:
        sections["cars"] = Band(127.0, 123.0, 130.0)
        modeled.append("cars")
        scale_note = "full 4-section 472-528 composite"
    else:
        scale_note = "3-section partial of the 472-528 scale; CARS not modeled"
    point = sum(b.point for b in sections.values())
    return ScoreResult(
        kind="readiness",
        abstained=False,
        how_sure="medium",
        reasons=["partial composite"],
        band=Band(point, point - 8.0, point + 6.0),
        coverage=0.7,
        n=240,
        extra={
            "sections": sections,
            "modeled_sections": modeled,
            "cars_modeled": cars_modeled,
            "scale_note": scale_note,
            "model": "irt_2pl_eap",
        },
    )


def _dash_data(cars_modeled: bool) -> dict:
    """Minimal dashboard dict (as dashboard_dict would emit) for summary_cache."""
    return {
        "readiness": render._readiness(_readiness_result(cars_modeled)),
        "section_labels": {
            "chem_phys": "Chem/Phys",
            "bio_biochem": "Bio/Biochem",
            "psych_soc": "Psych/Soc",
        },
        "thresholds": {"reviews": 200, "coverage": 0.5, "performance_outcomes": 20},
        "performance": {"n": 96},
        "coverage": 0.7,
        "n_reviews": 240,
        "best_next": None,
        "updated": "2026-07-01 08:00",
    }


# --------------------------------------------------------------------------- #
# render._readiness payload
# --------------------------------------------------------------------------- #
def test_readiness_payload_reflects_cars_modeled_true():
    out = render._readiness(_readiness_result(True))
    assert out["cars_modeled"] is True
    assert "cars" in out["sections"]
    assert out["scale_note"] == "full 4-section 472-528 composite"
    assert "cars" in (out.get("modeled_sections") or [])


def test_readiness_payload_reflects_cars_modeled_false():
    out = render._readiness(_readiness_result(False))
    assert out["cars_modeled"] is False
    assert "cars" not in out["sections"]
    assert "CARS not modeled" in out["scale_note"]


def test_readiness_payload_defaults_false_when_abstained_no_extra():
    r = ScoreResult(
        kind="readiness",
        abstained=True,
        how_sure="insufficient",
        reasons=["not enough evidence"],
        band=None,
        n=10,
    )
    out = render._readiness(r)
    assert out["cars_modeled"] is False
    assert out["sections"] == {}


# --------------------------------------------------------------------------- #
# render.summary_cache / build_summary (home-screen card)
# --------------------------------------------------------------------------- #
def test_summary_cache_carries_cars_modeled_flag():
    assert render.summary_cache(_dash_data(True))["cars_modeled"] is True
    assert render.summary_cache(_dash_data(False))["cars_modeled"] is False


def test_build_summary_scale_copy_is_conditional():
    html_true = render.build_summary(render.summary_cache(_dash_data(True)))
    html_false = render.build_summary(render.summary_cache(_dash_data(False)))

    # CARS modeled -> a full four-section projection, no "not included" caveat.
    assert "all 4 sections" in html_true
    assert "CARS not included" not in html_true

    # CARS not modeled -> the honest labeled partial.
    assert "3 of 4 sections" in html_false
    assert "CARS not included" in html_false


# --------------------------------------------------------------------------- #
# report._readiness_block (CLI)
# --------------------------------------------------------------------------- #
def test_report_block_says_full_composite_when_cars_modeled():
    text = "\n".join(_readiness_block(_readiness_result(True)))
    assert "CARS not modeled" not in text
    assert "full 4-section 472-528 composite" in text
    assert "4-section composite" in text


def test_report_block_says_partial_when_cars_not_modeled():
    text = "\n".join(_readiness_block(_readiness_result(False)))
    assert "3-section partial" in text
    assert "CARS not modeled" in text


# --------------------------------------------------------------------------- #
# scoring core: confirm the flag is real (grounds the fix; guards both paths)
# --------------------------------------------------------------------------- #
def test_irt_core_models_cars_once_it_has_enough_items():
    cfg = ScoringConfig()
    items = {
        "chem_phys": [IrtItem(correct=i % 2) for i in range(8)],
        "bio_biochem": [IrtItem(correct=1) for _ in range(8)],
        "psych_soc": [IrtItem(correct=0) for _ in range(8)],
        "cars": [IrtItem(correct=i % 2) for i in range(8)],
    }
    res = irt_readiness(items, coverage=0.7, coverage_by_section={}, n_reviews=250, cfg=cfg)
    assert not res.abstained
    assert res.extra["cars_modeled"] is True
    assert "cars" in res.extra["modeled_sections"]
    assert res.extra["scale_note"] == "full 4-section 472-528 composite"


def test_classic_core_never_models_cars():
    cfg = ScoringConfig()
    outs = {s: [1, 0, 1, 0, 1, 1, 0, 1] for s in ("chem_phys", "bio_biochem", "psych_soc")}
    res = readiness(outs, coverage=0.7, coverage_by_section={}, n_reviews=250, cfg=cfg)
    assert not res.abstained
    assert res.extra["cars_modeled"] is False
    assert "CARS not modeled" in res.extra["scale_note"]
