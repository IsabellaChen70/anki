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
    # Read the flags the scoring core actually set. Only the IRT path models CARS,
    # and only once CARS has enough real practice; the classic path and any
    # abstained result leave `extra` without the key, so default to False. Never
    # hardcode the CARS state here: the numbers are real, so the label must match.
    extra = s.extra or {}
    out = {
        "abstained": s.abstained,
        "how_sure": s.how_sure,
        "n": s.n,
        "reasons": list(s.reasons),
        "cars_modeled": bool(extra.get("cars_modeled", False)),
        "sections": {},
    }
    if s.band:
        out.update(point=s.band.point, low=s.band.low, high=s.band.high)
    for key, band in (extra.get("sections") or {}).items():
        out["sections"][key] = {"point": band.point, "low": band.low, "high": band.high}
    # Additive pass-through of the readiness extra: the partial-composite framing
    # and, when the latent-ability path is active, its per-section posterior. The
    # web UI uses these to describe "how sure" from the estimate; it never shows
    # the raw model internals to the student.
    if extra.get("modeled_sections") is not None:
        out["modeled_sections"] = list(extra.get("modeled_sections") or [])
    if extra.get("scale_note"):
        out["scale_note"] = extra.get("scale_note")
    if extra.get("model"):
        out["model"] = extra.get("model")
    if extra.get("irt"):
        out["irt"] = {sec: dict(vals) for sec, vals in extra["irt"].items()}
    return out


def _calibration(c) -> dict:
    if c is None:
        return {"abstained": True, "how_sure": "insufficient", "n": 0, "bins": []}
    return {
        "abstained": c.abstained,
        "how_sure": c.how_sure,
        "n": c.n,
        "reasons": list(c.reasons),
        "brier": c.brier,
        "mean_predicted": c.mean_predicted,
        "mean_observed": c.mean_observed,
        "well_calibrated": c.well_calibrated,
        "bins": [
            {"lo": b.lo, "hi": b.hi, "n": b.n, "pred_mean": b.pred_mean, "obs_rate": b.obs_rate}
            for b in c.bins
        ],
    }


def _study_pace(p) -> dict:
    if p is None:
        return {"has_exam_date": False}
    return {
        "has_exam_date": p.has_exam_date,
        "exam_date": p.exam_date,
        "days_left": p.days_left,
        "passed": p.passed,
        "reviews_due": p.reviews_due,
        "flashcards_per_day": p.flashcards_per_day,
        "new_remaining": p.new_remaining,
        "new_per_day": p.new_per_day,
        "reasoning_target": p.reasoning_target,
        "reasoning_done": p.reasoning_done,
        "reasoning_today": getattr(p, "reasoning_today", 0),
        "reasoning_remaining": p.reasoning_remaining,
        "reasoning_per_day": p.reasoning_per_day,
        "flashcards_to_exam": getattr(p, "flashcards_to_exam", 0),
        "reasoning_to_exam": getattr(p, "reasoning_to_exam", 0),
        "message": p.message,
    }


def _confidence(c) -> dict:
    if c is None:
        return {"abstained": True, "levels": []}
    return {
        "abstained": c.abstained,
        "n": c.n,
        "insight": c.insight,
        "levels": [{"level": lv.level, "n": lv.n, "rate": lv.rate} for lv in c.levels],
    }


def _mistakes(m) -> dict:
    if m is None:
        return {"abstained": True, "items": []}
    items = sorted(m.by_reason.items(), key=lambda kv: -kv[1])
    return {
        "abstained": m.abstained,
        "n_wrong": m.n_wrong,
        "top_reason": m.top_reason,
        "top_section": m.top_section,
        "items": [{"reason": r, "count": n} for r, n in items],
    }


def _plan(p) -> dict:
    def item(x) -> dict:
        return {"concept_id": x.concept_id, "name": x.name, "section": x.section, "recall": x.recall}

    p = p or {}
    return {
        "study": [item(x) for x in p.get("study", [])],
        "practice": [item(x) for x in p.get("practice", [])],
    }


def _pacing(p) -> dict:
    if p is None:
        return {"abstained": True, "sections": []}
    return {
        "abstained": p.abstained,
        "n": p.n,
        "overall_on_pace": p.overall_on_pace,
        "sections": [
            {
                "section": s.section, "n": s.n, "median_sec": s.median_sec, "target_sec": s.target_sec,
                "on_pace": s.on_pace, "projected_left": s.projected_left, "spare_min": s.spare_min,
            }
            for s in p.sections
        ],
    }


def _trajectory(t) -> dict:
    if t is None:
        return {"abstained": True}
    return {
        "abstained": t.abstained,
        "projected": t.projected,
        "target": t.target,
        "on_pace": t.on_pace,
        "per_week": t.per_week,
        "weakest_section": t.weakest_section,
        "scale_lo": getattr(t, "scale_lo", None),
        "scale_hi": getattr(t, "scale_hi", None),
        "reason": t.reason,
    }


def _fluency(items, name_by_id: dict) -> list:
    """Serialize the per-concept paraphrase test (the fluency illusion list),
    worst gap first, attaching each concept's student-facing name when the outline
    has one (falling back to the id on the web side). Additive; empty when the
    scoring layer had too little per-concept evidence to report a gap."""
    out = []
    for t in items or []:
        out.append(
            {
                "concept_id": t.concept_id,
                "name": name_by_id.get(t.concept_id, ""),
                "section": t.section,
                "recall": t.recall,
                "application": t.application,
                "gap": t.gap,
                "n_app": t.n_app,
                "fluency_risk": t.fluency_risk,
            }
        )
    return out


def dashboard_dict(col) -> dict:
    # Prefer the copy shipped inside Anki; fall back to the add-on's vendored
    # snapshot when it is missing (e.g. a packaged build predating the module).
    try:
        from anki.vantage import collect
        from anki.vantage.outline import Outline
        from anki.vantage.scoring import SECTION_LABELS, ScoringConfig
    except ModuleNotFoundError:
        from .vantage_core import collect
        from .vantage_core.outline import Outline
        from .vantage_core.scoring import SECTION_LABELS, ScoringConfig

    d = collect.gather(col)
    cfg = ScoringConfig()

    # Concept id -> student-facing name, for the fluency-illusion list. Guarded so
    # a missing outline degrades to showing concept ids, never a failed dashboard.
    name_by_id: dict[str, str] = {}
    try:
        name_by_id = {c.id: c.name for c in Outline.load().concepts}
    except Exception:
        name_by_id = {}
    return {
        "coverage": d.coverage,
        "coverage_by_section": dict(d.coverage_by_section),
        "topic_coverage": getattr(d, "topic_coverage", 0.0),
        "topic_coverage_by_section": dict(getattr(d, "topic_coverage_by_section", {}) or {}),
        "outline_version": d.outline_version,
        "n_reviews": d.n_reviews,
        "n_cards_seen": d.n_cards_seen,
        "ai_used": d.ai_used,
        "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.updated_ts)),
        "best_next": d.best_next,
        "next_topics": list(getattr(d, "next_topics", []) or []),
        "topic_gaps": list(getattr(d, "topic_gaps", []) or []),
        "book_set": getattr(d, "book_set", "kaplan"),
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
        "fluency_items": _fluency(getattr(d, "fluency_items", None), name_by_id),
        "calibration": _calibration(getattr(d, "calibration", None)),
        "study_pace": _study_pace(getattr(d, "study_pace", None)),
        "confidence": _confidence(getattr(d, "confidence", None)),
        "mistakes": _mistakes(getattr(d, "mistakes", None)),
        "study_plan": _plan(getattr(d, "study_plan", None)),
        "pacing": _pacing(getattr(d, "pacing", None)),
        "trajectory": _trajectory(getattr(d, "trajectory", None)),
    }


# Shown to students when a live render can't be computed. The raw Python error
# is never put in the UI; it is only logged to the JS console for debugging.
LOAD_ERROR_MESSAGE = "Something went wrong computing your scores. Tap Refresh to try again."


def _data_script(
    data: dict | None,
    error: str | None = None,
    live: bool = False,
    initial_tab: str = "dashboard",
) -> str:
    """Seed the window globals the web UI reads.

    `live` marks a real add-on render (not the offline preview): the UI then
    refuses to fall back to its built-in demo numbers and shows an honest error
    if data is missing. On failure we expose only a short, student-facing
    message; the raw error goes to the console for debugging, never the screen.

    `initial_tab` tells the page which tab to open after this (re)render. It is
    how returning from a study session lands the student back on Practice, the
    tab they launched from, instead of resetting to Dashboard. The web side
    validates it against its known tabs and defaults to Dashboard.
    """
    parts = [f"window.__VANTAGE_INITIAL_TAB__ = {json.dumps(initial_tab)};"]
    if live:
        parts.append("window.__VANTAGE_LIVE__ = true;")
    if data is not None:
        parts.append(f"window.__VANTAGE__ = {json.dumps(data)};")
    else:
        parts.append("window.__VANTAGE__ = null;")
        parts.append(f"window.__VANTAGE_ERR__ = {json.dumps(LOAD_ERROR_MESSAGE)};")
        if error:
            parts.append(f"console.error('Vantage could not load scores:', {json.dumps(error)});")
    return " ".join(parts)


# Reasoning question bank: authored per-section JSON files (reasoning_bank.<section>.json)
# loaded at build time so desktop and mobile serve the identical bank (parity).
# practice.js reads the injected window.__VANTAGE_REASONING_BANK__ global; if the files
# are absent it falls back to its small built-in item set.
_REASONING_SECTIONS = ("cars", "chem_phys", "bio_biochem", "psych_soc")


def _reasoning_bank_script() -> str:
    bank: dict = {}
    for sec in _REASONING_SECTIONS:
        path = _WEB / f"reasoning_bank.{sec}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        passages = data.get("passages") or []
        if passages:
            bank[sec] = {"title": data.get("title"), "passages": passages}
    if not bank:
        return ""
    return (
        "<script>window.__VANTAGE_REASONING_BANK__ = "
        f"{json.dumps(bank, ensure_ascii=False)};</script>"
    )


def build_body(
    data: dict | None,
    error: str | None = None,
    live: bool = False,
    initial_tab: str = "dashboard",
) -> str:
    css = (_WEB / "dashboard.css").read_text(encoding="utf-8")
    review_css = (_WEB / "reviewer.css").read_text(encoding="utf-8")
    practice_css = (_WEB / "practice.css").read_text(encoding="utf-8")
    js = (_WEB / "dashboard.js").read_text(encoding="utf-8")
    review_js = (_WEB / "reviewer.js").read_text(encoding="utf-8")
    practice_js = (_WEB / "practice.js").read_text(encoding="utf-8")
    data_js = _data_script(data, error, live, initial_tab)
    return (
        f"<style>{css}{review_css}{practice_css}</style>"
        f'<div class="app" id="app"></div>'
        f"<script>{data_js}</script>"
        f"<script>{js}</script>"
        f"<script>{review_js}</script>"
        f"{_reasoning_bank_script()}"
        f"<script>{practice_js}</script>"
    )


# --------------------------------------------------------------------------- #
# Compact home-screen summary (deck browser card)
# --------------------------------------------------------------------------- #
# A tiny snapshot rendered directly on Anki's home screen (the Deck Browser),
# reusing the exact numbers dashboard_dict already computed. It never recomputes
# anything: the add-on writes summary_cache(dashboard_dict(col)) to a collection
# config key whenever the full dashboard runs, and the home hook only READS that
# cache and hands it to build_summary. So the deck list stays instant.

# Collection config key holding the last computed summary (see summary_cache).
SCORE_CACHE_KEY = "vantage.score_cache"

# The schema version of the cached summary. Bump if the shape below changes so a
# stale-shaped cache from an older add-on is ignored rather than mis-read.
SUMMARY_CACHE_VERSION = 1

# How old a cached summary may be before the card adds a quiet "may be out of
# date" note. The home screen can never recompute, so this is purely a freshness
# cue for the student; it is a display choice, not a scoring threshold, which is
# why it lives here and not in ScoringConfig.
SUMMARY_STALE_SECONDS = 24 * 60 * 60


def _esc(s) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _summary_pct(x) -> str:
    try:
        return f"{round(float(x) * 100)}%"
    except (TypeError, ValueError):
        return "0%"


def _round_or_none(x):
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def summary_cache(data: dict) -> dict:
    """Project the full dashboard dict down to the few fields the home card needs.

    This is a pure re-use of dashboard_dict's output: no scoring, no thresholds,
    no give-up rule are re-derived here. The abstain (give-up) state is copied
    straight from the readiness score the scoring layer already decided.
    """
    r = data.get("readiness") or {}
    labels = data.get("section_labels") or {}
    thresholds = data.get("thresholds") or {}
    perf = data.get("performance") or {}

    best = None
    bn = data.get("best_next")
    if bn:
        section = bn.get("section", "")
        best = {
            "name": bn.get("name", ""),
            "section": section,
            "section_label": labels.get(section, section),
            "covered": bool(bn.get("covered")),
            "mastery": bn.get("mastery"),
        }

    return {
        "v": SUMMARY_CACHE_VERSION,
        # give-up / abstain state, copied from the readiness score as-is
        "abstained": bool(r.get("abstained", True)),
        # projected readiness (partial composite), rounded for a glanceable card
        "point": _round_or_none(r.get("point")),
        "low": _round_or_none(r.get("low")),
        "high": _round_or_none(r.get("high")),
        "how_sure": r.get("how_sure", "insufficient"),
        "n_sections": len(r.get("sections") or {}),
        # whether CARS is actually in the composite, copied from the readiness
        # score as-is so the home card frames the scale honestly (a full 4-section
        # projection vs the 3-section partial). Absent on older caches -> False.
        "cars_modeled": bool(r.get("cars_modeled", False)),
        "scale_note": r.get("scale_note"),
        # progress + thresholds, so the abstain card can say what is still missing
        "coverage": data.get("coverage", 0.0),
        "n_reviews": data.get("n_reviews", 0),
        "performance_n": perf.get("n", 0),
        "thresholds": {
            "reviews": thresholds.get("reviews"),
            "coverage": thresholds.get("coverage"),
            "performance_outcomes": thresholds.get("performance_outcomes"),
        },
        "best_next": best,
        "updated_ts": int(time.time()),
        "updated": data.get("updated")
        or time.strftime("%Y-%m-%d %H:%M", time.localtime()),
    }


# Scoped, theme-agnostic styles for the home card. Everything is namespaced under
# .vtg-home and uses translucent grays + inherited text so it reads correctly in
# both Anki's light and dark themes without any night-mode detection.
_SUMMARY_CSS = (
    ".vtg-home{max-width:640px;margin:18px auto;text-align:left;"
    "font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;}"
    ".vtg-home *{box-sizing:border-box;}"
    ".vtg-card{border:1px solid rgba(128,128,128,.28);border-radius:12px;"
    "padding:18px 20px;background:rgba(128,128,128,.06);}"
    ".vtg-eyebrow{font-size:12px;font-weight:700;letter-spacing:.14em;"
    "text-transform:uppercase;opacity:.6;}"
    ".vtg-eyebrow .vtg-dot{color:#3b82f6;}"
    ".vtg-label{margin-top:10px;font-size:13px;font-weight:600;opacity:.7;}"
    ".vtg-range{margin-top:2px;font-size:34px;font-weight:800;letter-spacing:-.02em;"
    "color:#3b82f6;line-height:1.05;}"
    ".vtg-abstain{margin-top:8px;font-size:20px;font-weight:800;letter-spacing:-.01em;}"
    ".vtg-lead{margin-top:6px;font-size:13px;font-weight:500;opacity:.8;}"
    ".vtg-meta{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px 16px;"
    "font-size:13px;font-weight:600;}"
    ".vtg-meta .vtg-k{opacity:.55;font-weight:500;}"
    ".vtg-missing{margin:10px 0 0;padding-left:18px;font-size:13px;font-weight:500;opacity:.85;}"
    ".vtg-missing li{margin:2px 0;}"
    ".vtg-next{margin-top:12px;font-size:14px;font-weight:600;}"
    ".vtg-next .vtg-k{display:block;font-size:11px;letter-spacing:.1em;"
    "text-transform:uppercase;opacity:.55;font-weight:700;margin-bottom:2px;}"
    ".vtg-foot{margin-top:16px;display:flex;align-items:center;justify-content:space-between;"
    "gap:12px;flex-wrap:wrap;}"
    ".vtg-updated{font-size:12px;font-weight:500;opacity:.55;}"
    ".vtg-updated .vtg-stale{color:#d97706;opacity:1;}"
    ".vtg-btn{appearance:none;-webkit-appearance:none;border:0;cursor:pointer;"
    "background:#3b82f6;color:#fff;font-family:inherit;font-weight:700;font-size:13px;"
    "border-radius:8px;padding:9px 14px;}"
    ".vtg-btn:hover{background:#2563eb;}"
)

# The pycmd message the "Open full dashboard" button sends. Namespaced away from
# the standalone dashboard's own "vantage:*" bridge so the two never collide; the
# add-on routes this through webview_did_receive_js_message.
SUMMARY_OPEN_CMD = "vantagehome:open"


def _summary_best_next(best: dict | None) -> str:
    if not best or not best.get("name"):
        return ""
    name = _esc(best.get("name"))
    label = best.get("section_label") or best.get("section") or ""
    tail = f" ({_esc(label)})" if label else ""
    if best.get("covered"):
        state = f"{_summary_pct(best.get('mastery'))} recalled so far"
    else:
        state = "not studied yet"
    return (
        '<div class="vtg-next"><span class="vtg-k">Study this next</span>'
        f"{name}{tail} &middot; {state}</div>"
    )


def _summary_missing(cache: dict) -> list[str]:
    """What the student still needs before an honest readiness range appears.

    Mirrors the dashboard's readiness abstain copy, driven by the same thresholds
    the scoring layer reported (never re-derived here)."""
    th = cache.get("thresholds") or {}
    out: list[str] = []
    rev_need = th.get("reviews")
    cov_need = th.get("coverage")
    perf_need = th.get("performance_outcomes")
    if rev_need is not None and cache.get("n_reviews", 0) < rev_need:
        out.append(f"{rev_need} graded reviews (you have {cache.get('n_reviews', 0)})")
    if cov_need is not None and cache.get("coverage", 0) < cov_need:
        out.append(
            f"{_summary_pct(cov_need)} of the exam covered "
            f"(you have {_summary_pct(cache.get('coverage', 0))})"
        )
    if perf_need is not None and cache.get("performance_n", 0) < perf_need:
        out.append(
            f"{perf_need} exam-style practice questions answered "
            f"(you have {cache.get('performance_n', 0)})"
        )
    return out


def _summary_footer(cache: dict, now_ts: float, open_button: bool = True) -> str:
    updated = cache.get("updated")
    updated_ts = cache.get("updated_ts") or 0
    stale = updated_ts and (now_ts - updated_ts) > SUMMARY_STALE_SECONDS
    if updated:
        note = (
            ' <span class="vtg-stale">(may be out of date)</span>' if stale else ""
        )
        left = f'<span class="vtg-updated">Updated {_esc(updated)}{note}</span>'
    else:
        # No timestamp only happens in the "not calculated yet" state, whose
        # headline already says so; keep the footer to just the action.
        left = "<span></span>"
    btn = (
        f"<button class=\"vtg-btn\" onclick=\"pycmd('{SUMMARY_OPEN_CMD}')\">"
        "Open full dashboard</button>"
        if open_button
        else ""
    )
    return f'<div class="vtg-foot">{left}{btn}</div>'


def _summary_shell(inner: str) -> str:
    return f'<style>{_SUMMARY_CSS}</style><div class="vtg-home"><div class="vtg-card">{inner}</div></div>'


def build_summary(cache: dict | None, now_ts: float | None = None) -> str:
    """Render the compact home-screen card from a cached summary (see
    summary_cache). Pure and headless: no aqt, no collection, no scoring.

    Three honest states:
      * cache missing  -> no number, prompt to open the dashboard to calculate.
      * abstained/thin -> no number, "Not enough data yet" + what is missing.
      * ready          -> the projected readiness RANGE (a labeled partial), the
                          % of the exam covered, a "how sure" word, and the best
                          next topic. Never a fabricated single point sold as
                          certainty, and never a stale range shown as current.
    """
    now = time.time() if now_ts is None else now_ts
    eyebrow = '<div class="vtg-eyebrow"><span class="vtg-dot">Vantage</span> readiness</div>'

    # State 1: nothing computed yet. Be honest that there is no number, don't
    # invent a "not enough data" verdict we haven't actually earned.
    if not cache or not isinstance(cache, dict):
        inner = (
            f"{eyebrow}"
            '<div class="vtg-abstain">Not calculated yet</div>'
            '<div class="vtg-lead">Open the full dashboard to calculate your '
            "readiness from your reviews and practice.</div>"
            f"{_summary_footer({}, now)}"
        )
        return _summary_shell(inner)

    best = _summary_best_next(cache.get("best_next"))

    # State 2: below the give-up line (or no band). Show no number; say plainly
    # what is still needed, then point at the best next topic.
    if cache.get("abstained") or cache.get("low") is None or cache.get("high") is None:
        missing = _summary_missing(cache)
        missing_html = ""
        if missing:
            lis = "".join(f"<li>{_esc(m)}</li>" for m in missing)
            missing_html = f'<p class="vtg-lead">You still need:</p><ul class="vtg-missing">{lis}</ul>'
        else:
            missing_html = (
                '<div class="vtg-lead">A little more studying and practice and '
                "your projected score range will appear here.</div>"
            )
        inner = (
            f"{eyebrow}"
            '<div class="vtg-abstain">Not enough data yet</div>'
            f"{missing_html}{best}{_summary_footer(cache, now)}"
        )
        return _summary_shell(inner)

    # State 3: an honest projected range. Framed as exactly what it covers: the
    # full four-section projection once CARS has real practice, otherwise the
    # three-section partial. Driven by the real cars_modeled flag, never assumed.
    low = cache.get("low")
    high = cache.get("high")
    how = cache.get("how_sure") or "medium"
    scale_line = (
        "Covers all 4 sections"
        if cache.get("cars_modeled")
        else "Covers 3 of 4 sections, CARS not included yet"
    )
    meta = (
        '<div class="vtg-meta">'
        f'<span>{_summary_pct(cache.get("coverage"))} <span class="vtg-k">of the exam covered</span></span>'
        f'<span class="vtg-k">How sure:</span><span>{_esc(how)}</span>'
        "</div>"
    )
    inner = (
        f"{eyebrow}"
        '<div class="vtg-label">Projected score range</div>'
        f'<div class="vtg-range">{low} to {high}</div>'
        f'<div class="vtg-lead">{scale_line}</div>'
        f"{meta}{best}{_summary_footer(cache, now)}"
    )
    return _summary_shell(inner)


def build_reviewer_preview() -> str:
    """Standalone reviewer page for offline previews (host pushes live cards)."""
    css = (_WEB / "dashboard.css").read_text(encoding="utf-8")
    review_css = (_WEB / "reviewer.css").read_text(encoding="utf-8")
    review_js = (_WEB / "reviewer.js").read_text(encoding="utf-8")
    body = f"<style>{css}{review_css}</style><div id='app'></div><script>{review_js}</script>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{FONT_HEAD}</head><body>{body}</body></html>"
    )


def build_page(data: dict | None, error: str | None = None) -> str:
    """Full standalone HTML page (for offline preview / non-Anki webviews)."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{FONT_HEAD}</head><body>{build_body(data, error)}</body></html>"
    )


def build_practice_page() -> str:
    """Standalone CARS practice page (passage + questions). Same design system."""
    css = (_WEB / "practice.css").read_text(encoding="utf-8")
    js = (_WEB / "practice.js").read_text(encoding="utf-8")
    body = (
        f"<style>{css}</style><div id='app'></div>{_reasoning_bank_script()}<script>{js}</script>"
        "<script>window.addEventListener('load',function(){vpractice.open();});</script>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{FONT_HEAD}</head><body>{body}</body></html>"
    )


def _outline_topics_script() -> str:
    """Inline the AAMC topic grain (topics per concept + aliases + the deck->topic
    map) so the mobile page can compute the depth-aware `topic_coverage` (the header's
    "% of the exam covered") that desktop computes in Python. Read from the vendored
    outline so mobile and desktop share ONE source (no hand-copied drift). If the files
    are missing the script is empty and mobile_scoring.js falls back to category
    coverage rather than showing NaN."""
    core = Path(__file__).parent / "vantage_core"
    try:
        outline = json.loads((core / "aamc_outline.json").read_text(encoding="utf-8"))
        deck_map = json.loads(
            (core / "deck_topic_map.json").read_text(encoding="utf-8")
        ).get("map", {})
    except Exception:
        return ""
    payload = {
        "concepts": [
            {
                "id": c["id"],
                "topics": [
                    {"id": t["id"], "aliases": list(t.get("aliases", []))}
                    for t in c.get("topics", [])
                ],
            }
            for c in outline.get("concepts", [])
        ],
        "deck_topic_map": deck_map,
    }
    return (
        "<script>window.__VANTAGE_TOPICS__ = "
        f"{json.dumps(payload, ensure_ascii=False)};</script>"
    )


def build_mobile_page(data: dict | None, error: str | None = None) -> str:
    """Standalone page for the AnkiDroid WebView.

    Same UI as the desktop, plus the on-device scoring port (mobile_scoring.js).
    `data` is a baked fallback; the host then injects live collection data via
    window.vantageComputeFromRaw + window.__vantageRender.
    """
    css = (_WEB / "dashboard.css").read_text(encoding="utf-8")
    practice_css = (_WEB / "practice.css").read_text(encoding="utf-8")
    scoring = (_WEB / "mobile_scoring.js").read_text(encoding="utf-8")
    js = (_WEB / "dashboard.js").read_text(encoding="utf-8")
    practice_js = (_WEB / "practice.js").read_text(encoding="utf-8")
    # live=True mirrors the desktop honesty contract: the mobile page never falls
    # back to MOCK demo numbers; if the on-device compute fails it shows the error
    # card instead. The AnkiDroid host injects real scores right after load.
    data_js = _data_script(data, error, live=True)
    body = (
        f"<style>{css}{practice_css}</style>"
        f'<div class="app" id="app"></div>'
        f"{_outline_topics_script()}"
        f"<script>{scoring}</script>"
        f"<script>{data_js}</script>"
        f"<script>{js}</script>"
        f"{_reasoning_bank_script()}"
        f"<script>{practice_js}</script>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{FONT_HEAD}</head><body>{body}</body></html>"
    )
