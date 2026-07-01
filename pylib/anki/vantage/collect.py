# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — collection adapter for the scoring layer.

Turns a live Anki `Collection` into the inputs the pure scoring core needs:

* memory: real per-card FSRS retrievability `R` via Anki's own
  `extract_fsrs_retrievability` SQLite function (the same one the browser
  "Retrievability" column and review ordering use) — never reimplemented.
* coverage: card tags -> AAMC concepts -> weighted coverage (D11).
* readiness gate: count of graded reviews from the revlog (D10).
* performance: application-item outcomes (interim store in collection config
  until spec-performance-items lands; keeps the score honest and off-by-default).

This module imports Anki and is loaded on demand (not from the package __init__),
so the pure core stays testable without a backend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from . import scoring
from .outline import Outline
from .scoring import SECTIONS, ScoreResult, ScoringConfig

if TYPE_CHECKING:
    from anki.collection import Collection

# Interim store for application-item outcomes: a list of dicts
# {"section": <str>, "correct": <bool>, "predicted": <float|None>, "ts": <int>}.
# Replaced by real app-item cards/revlog when spec-performance-items is built.
PERF_CONFIG_KEY = "vantage_perf_outcomes"


@dataclass
class Dashboard:
    memory: ScoreResult
    performance: ScoreResult
    readiness: ScoreResult
    coverage: float
    coverage_by_section: dict[str, float]
    outline_version: str
    n_reviews: int
    n_cards_seen: int
    best_next: Optional[dict] = None
    updated_ts: int = 0
    ai_used: bool = False  # the scoring path never calls a model (D12)
    extra: dict = field(default_factory=dict)


def _cards_r_and_tags(col: "Collection") -> list[tuple[str, Optional[float]]]:
    """Return (tags, R) for every non-suspended card. R is None if no FSRS state."""
    now = int(time.time())
    today = col.sched.today
    next_day_at = col.sched.day_cutoff
    rows = col.db.all(
        """
        select n.tags,
               extract_fsrs_retrievability(
                   c.data,
                   case when c.odue != 0 then c.odue else c.due end,
                   c.ivl, ?, ?, ?)
        from cards c
        join notes n on c.nid = n.id
        where c.queue != -1
        """,
        today,
        next_day_at,
        now,
    )
    return [(tags or "", r) for tags, r in rows]


def _graded_reviews(col: "Collection") -> int:
    """Number of graded reviews (Again/Hard/Good/Easy) in the revlog."""
    return col.db.scalar("select count() from revlog where ease between 1 and 4") or 0


def _perf_outcomes(col: "Collection") -> list[dict]:
    raw = col.get_config(PERF_CONFIG_KEY, [])
    return raw if isinstance(raw, list) else []


def gather(
    col: "Collection",
    cfg: Optional[ScoringConfig] = None,
    outline: Optional[Outline] = None,
) -> Dashboard:
    """Compute the three honest scores + coverage + best-next-topic for a collection."""
    cfg = cfg or ScoringConfig()
    outline = outline or Outline.load()

    # --- memory + coverage + per-concept mastery in one pass over the cards ---
    r_values: list[float] = []
    covered: set[str] = set()
    concept_r: dict[str, list[float]] = {}
    for tags, r in _cards_r_and_tags(col):
        card_concepts = {
            cid
            for cid in (outline.match_tag(t) for t in tags.split())
            if cid is not None
        }
        covered |= card_concepts
        if r is not None:
            r_values.append(r)
            for cid in card_concepts:
                concept_r.setdefault(cid, []).append(r)

    coverage = outline.weighted_coverage(covered)
    coverage_by_section = outline.coverage_by_section(covered)
    n_reviews = _graded_reviews(col)

    memory = scoring.memory_score(r_values, coverage, cfg)

    # --- performance (application-item outcomes; abstains until enough exist) ---
    perf = _perf_outcomes(col)
    perf_flat = [1 if o.get("correct") else 0 for o in perf]
    performance = scoring.performance_score(perf_flat, coverage, cfg)

    section_outcomes: dict[str, list[int]] = {s: [] for s in SECTIONS}
    for o in perf:
        s = o.get("section")
        if s in section_outcomes:
            section_outcomes[s].append(1 if o.get("correct") else 0)

    readiness = scoring.readiness(
        section_outcomes, coverage, coverage_by_section, n_reviews, cfg
    )

    best_next = _best_next_topic(outline, covered, concept_r)

    return Dashboard(
        memory=memory,
        performance=performance,
        readiness=readiness,
        coverage=coverage,
        coverage_by_section=coverage_by_section,
        outline_version=outline.version,
        n_reviews=n_reviews,
        n_cards_seen=len(r_values),
        best_next=best_next,
        updated_ts=int(time.time()),
        ai_used=False,
    )


def _best_next_topic(
    outline: Outline, covered: set[str], concept_r: dict[str, list[float]]
) -> Optional[dict]:
    """Highest weight x (1 - mastery); uncovered concepts count as mastery 0 (D10)."""
    best = None
    best_score = -1.0
    for c in outline.concepts:
        rs = concept_r.get(c.id, [])
        mastery = (sum(rs) / len(rs)) if rs else 0.0
        priority = c.weight * (1.0 - mastery)
        if priority > best_score:
            best_score = priority
            best = {
                "concept_id": c.id,
                "name": c.name,
                "section": c.section,
                "weight": c.weight,
                "mastery": round(mastery, 3),
                "covered": c.id in covered,
                "priority": round(priority, 3),
            }
    return best


def set_perf_outcomes(col: "Collection", outcomes: list[dict]) -> None:
    """Write the interim application-item outcomes store (used for demos/tests)."""
    col.set_config(PERF_CONFIG_KEY, outcomes)
