# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — CLI readiness dashboard.

Usage:
    python -m anki.vantage.report /path/to/collection.anki2

Prints the three honest scores (memory / performance / readiness), each with a
range, plus weighted coverage, the give-up state, top reasons, and the single
best next topic. Read-only. This is the terminal surface of the same
`Dashboard` a GUI would render.
"""

from __future__ import annotations

import sys
import time

from .collect import Dashboard, gather
from .scoring import SECTION_LABELS, ScoreResult

_BAR = "=" * 64
_SUB = "-" * 64


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _how_sure(s: str) -> str:
    return {
        "insufficient": "insufficient evidence",
        "low": "low",
        "medium": "medium",
        "high": "high",
    }.get(s, s)


def _pct_score_block(title: str, r: ScoreResult) -> list[str]:
    lines = [f"{title}"]
    if r.abstained or r.band is None:
        lines.append(f"    — abstained ({_how_sure(r.how_sure)})")
    else:
        b = r.band
        lines.append(
            f"    {_pct(b.point)}   likely {_pct(b.low)}–{_pct(b.high)}"
            f"    · how sure: {_how_sure(r.how_sure)}   · n={r.n}"
        )
    for reason in r.reasons:
        lines.append(f"      · {reason}")
    return lines


def _readiness_block(r: ScoreResult) -> list[str]:
    lines = ["READINESS  (projected MCAT science score)"]
    if r.abstained or r.band is None:
        lines.append("    — NO SCORE YET (give-up rule): not enough evidence")
        for reason in r.reasons:
            lines.append(f"      · {reason}")
        return lines
    b = r.band
    # Reflect the real scale the core computed: CARS joins the composite (a full
    # 4-section total) once it has enough practice; otherwise it is the labeled
    # partial. Never hardcode "CARS not modeled" -- the numbers are real, so the
    # label must match. Defaults stay defensive if a path omitted the keys.
    extra = r.extra or {}
    cars_modeled = bool(extra.get("cars_modeled", False))
    modeled = extra.get("modeled_sections") or list((extra.get("sections") or {}).keys())
    n_sec = len(modeled)
    header = f"{n_sec}-section composite" if cars_modeled else f"{n_sec}-section partial"
    lines.append(
        f"    {header}: {b.point:.0f}   likely {b.low:.0f}–{b.high:.0f}"
        f"    · how sure: {_how_sure(r.how_sure)}"
    )
    scale_note = extra.get("scale_note")
    if scale_note:
        lines.append(f"    ({scale_note})")
    elif cars_modeled:
        lines.append("    (of the 472–528 scale; full 4-section total)")
    else:
        lines.append("    (of the 472–528 scale; CARS not modeled → no 4-section total)")
    for s, band in extra.get("sections", {}).items():
        label = SECTION_LABELS.get(s) or ("CARS" if s == "cars" else s)
        lines.append(
            f"      {label:<12} {band.point:.0f}   "
            f"(likely {band.low:.0f}–{band.high:.0f})   [118–132]"
        )
    for reason in r.reasons:
        lines.append(f"      · {reason}")
    return lines


def render(dash: Dashboard) -> str:
    out: list[str] = []
    out.append(_BAR)
    out.append("VANTAGE — honest readiness dashboard")
    out.append(
        f"coverage {_pct(dash.coverage)} of AAMC outline "
        f"({dash.outline_version})   ·   graded reviews: {dash.n_reviews}   ·   "
        f"seen cards: {dash.n_cards_seen}   ·   AI used: {'yes' if dash.ai_used else 'no'}"
    )
    cov = "   ".join(
        f"{SECTION_LABELS.get(s, s)} {_pct(v)}" for s, v in dash.coverage_by_section.items()
    )
    out.append(f"coverage by section:  {cov}")
    out.append(_SUB)
    out += _pct_score_block("MEMORY     (mean FSRS retrievability over seen cards)", dash.memory)
    out.append("")
    out += _pct_score_block("PERFORMANCE (accuracy on novel application items)", dash.performance)
    out.append("")
    out += _readiness_block(dash.readiness)
    out.append(_SUB)
    if dash.best_next:
        bn = dash.best_next
        state = "uncovered" if not bn["covered"] else f"mastery {_pct(bn['mastery'])}"
        out.append(
            f"BEST NEXT TOPIC:  [{bn['concept_id']}] {bn['name']}"
        )
        out.append(
            f"    {SECTION_LABELS.get(bn['section'], bn['section'])} · "
            f"weight {bn['weight']:g} · {state} · priority {bn['priority']:g}"
        )
    out.append(
        f"updated {time.strftime('%Y-%m-%d %H:%M', time.localtime(dash.updated_ts))}"
    )
    out.append(_BAR)
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    from anki.collection import Collection

    col = Collection(path)
    try:
        dash = gather(col)
    finally:
        col.close()
    print(render(dash))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
