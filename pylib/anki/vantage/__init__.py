# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — the honest scoring layer.

Three separate scores, each with a range, plus an abstention (give-up) rule:
memory (FSRS) != performance (application items) != readiness (projection),
never blended (decision D8). See docs/spec-readiness-score.md.

Only the pure, dependency-free core (`scoring`, `outline`) is imported here so
this package can be unit-tested without constructing a Collection. The
collection adapter lives in `anki.vantage.collect` and is imported on demand.
"""

from __future__ import annotations

from .outline import Concept, Outline
from .scoring import (
    SECTION_LABELS,
    SECTIONS,
    Band,
    Calibration,
    CalibrationBin,
    ConfidenceCalibration,
    ConfidenceLevel,
    MistakeTaxonomy,
    Pacing,
    ScoreResult,
    ScoringConfig,
    SectionPace,
    SectionTransfer,
    StudyPace,
    Trajectory,
    brier,
    calibration,
    confidence_calibration,
    give_up,
    map_ability_to_scale,
    memory_score,
    mistake_taxonomy,
    pacing_coach,
    performance_score,
    readiness,
    study_pace,
    trajectory,
    transfer_gap,
)

__all__ = [
    "Outline",
    "Concept",
    "ScoringConfig",
    "ScoreResult",
    "Band",
    "SectionTransfer",
    "Calibration",
    "CalibrationBin",
    "StudyPace",
    "ConfidenceCalibration",
    "ConfidenceLevel",
    "MistakeTaxonomy",
    "Pacing",
    "SectionPace",
    "Trajectory",
    "SECTIONS",
    "SECTION_LABELS",
    "memory_score",
    "performance_score",
    "readiness",
    "transfer_gap",
    "calibration",
    "study_pace",
    "confidence_calibration",
    "mistake_taxonomy",
    "pacing_coach",
    "trajectory",
    "give_up",
    "map_ability_to_scale",
    "brier",
]
