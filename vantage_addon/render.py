# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage dashboard rendering, pure (no aqt), so it is reusable headlessly.

`dashboard_dict(col)` flattens anki.vantage's Dashboard into the JSON the web UI
consumes; `build_body(data)` inlines the CSS/JS with that data. The add-on
(__init__.py) and offline previews both call these.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_WEB = Path(__file__).parent / "web"

FONT_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)


def _pct_score(s) -> dict:
    return {
        "abstained": s.abstained,
        "how_sure": s.how_sure,
        "n": s.n,
        "reasons": list(s.reasons),
        "point": (s.band.point if s.band else None),
        "low": (s.band.low if s.band else None),
        "high": (s.band.high if s.band else None),
    }


def _readiness(s) -> dict:
    out = {
        "abstained": s.abstained,
        "how_sure": s.how_sure,
        "n": s.n,
        "reasons": list(s.reasons),
        "cars_modeled": False,
        "sections": {},
    }
    if s.band:
        out.update(point=s.band.point, low=s.band.low, high=s.band.high)
    for key, band in (s.extra.get("sections") or {}).items():
        out["sections"][key] = {"point": band.point, "low": band.low, "high": band.high}
    return out


def dashboard_dict(col) -> dict:
    from anki.vantage import collect
    from anki.vantage.scoring import SECTION_LABELS, ScoringConfig

    d = collect.gather(col)
    cfg = ScoringConfig()
    return {
        "coverage": d.coverage,
        "coverage_by_section": dict(d.coverage_by_section),
        "outline_version": d.outline_version,
        "n_reviews": d.n_reviews,
        "n_cards_seen": d.n_cards_seen,
        "ai_used": d.ai_used,
        "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.updated_ts)),
        "best_next": d.best_next,
        "section_labels": dict(SECTION_LABELS),
        "thresholds": {
            "memory_cards": cfg.min_cards_memory,
            "performance_outcomes": cfg.min_outcomes_performance,
            "reviews": cfg.giveup_min_reviews,
            "coverage": cfg.giveup_min_coverage,
        },
        "memory": _pct_score(d.memory),
        "performance": _pct_score(d.performance),
        "readiness": _readiness(d.readiness),
    }


def build_body(data: dict | None, error: str | None = None) -> str:
    css = (_WEB / "dashboard.css").read_text(encoding="utf-8")
    js = (_WEB / "dashboard.js").read_text(encoding="utf-8")
    if data is not None:
        data_js = f"window.__VANTAGE__ = {json.dumps(data)};"
    else:
        data_js = f"window.__VANTAGE__ = null; window.__VANTAGE_ERR__ = {json.dumps(error or '')};"
    return (
        f"<style>{css}</style>"
        f'<div class="app" id="app"></div>'
        f"<script>{data_js}</script>"
        f"<script>{js}</script>"
    )


def build_page(data: dict | None, error: str | None = None) -> str:
    """Full standalone HTML page (for offline preview / non-Anki webviews)."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{FONT_HEAD}</head><body>{build_body(data, error)}</body></html>"
    )
