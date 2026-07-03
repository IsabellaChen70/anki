#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Render the held-out memory calibration as a dependency-free SVG reliability
diagram from vantage_tools/memory_calibration.json (produced by evaluate_memory.py).

matplotlib is not in the bundled pyenv, so this emits SVG directly (no third-party
deps). Points on the dashed diagonal are perfectly calibrated.

Re-run: out/pyenv/bin/python vantage_tools/plot_calibration.py
Writes docs/img/memory_calibration.svg.
"""

from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "memory_calibration.json")
OUT = os.path.join(HERE, "..", "docs", "img", "memory_calibration.svg")

W = H = 480
M = 64  # margin around the unit-square plot
PLOT = W - 2 * M


def _x(v: float) -> float:
    return M + v * PLOT


def _y(v: float) -> float:
    return (H - M) - v * PLOT  # invert: 0 at bottom


def _esc(s: object) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    bins = data.get("reliability_bins", [])
    ece = data.get("ece")
    brier_m = data.get("brier_model")
    brier_b = data.get("brier_baseline")
    n = data.get("held_out_n")

    s: list[str] = []
    s.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Outfit, system-ui, sans-serif">'
    )
    s.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    s.append(
        f'<text x="{W / 2}" y="26" text-anchor="middle" font-size="16" '
        f'font-weight="700" fill="#111827">Memory calibration (held-out, n={_esc(n)})</text>'
    )
    cap = (
        f"ECE {ece}  \u00b7  Brier {brier_m} (model) vs {brier_b} (base rate)  \u00b7  "
        f"points on the dashed line are perfectly calibrated"
    )
    s.append(
        f'<text x="{W / 2}" y="46" text-anchor="middle" font-size="10" '
        f'fill="#6b7280">{_esc(cap)}</text>'
    )
    s.append(
        f'<rect x="{M}" y="{M}" width="{PLOT}" height="{PLOT}" fill="none" '
        f'stroke="#e5e7eb" stroke-width="1"/>'
    )
    for t in (0.0, 0.5, 1.0):
        s.append(
            f'<line x1="{_x(t):.1f}" y1="{M}" x2="{_x(t):.1f}" y2="{H - M}" '
            f'stroke="#f3f4f6" stroke-width="1"/>'
        )
        s.append(
            f'<line x1="{M}" y1="{_y(t):.1f}" x2="{W - M}" y2="{_y(t):.1f}" '
            f'stroke="#f3f4f6" stroke-width="1"/>'
        )
        s.append(
            f'<text x="{_x(t):.1f}" y="{H - M + 18}" text-anchor="middle" '
            f'font-size="11" fill="#6b7280">{t:.1f}</text>'
        )
        s.append(
            f'<text x="{M - 10}" y="{_y(t) + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#6b7280">{t:.1f}</text>'
        )
    # diagonal: perfect calibration
    s.append(
        f'<line x1="{_x(0):.1f}" y1="{_y(0):.1f}" x2="{_x(1):.1f}" y2="{_y(1):.1f}" '
        f'stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="5 4"/>'
    )
    # observed curve through the bin points
    pts = [(b["mean_predicted"], b["observed_rate"]) for b in bins]
    if pts:
        poly = " ".join(f"{_x(px):.1f},{_y(py):.1f}" for px, py in pts)
        s.append(
            f'<polyline points="{poly}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        )
    for b in bins:
        cx, cy = _x(b["mean_predicted"]), _y(b["observed_rate"])
        r = 4 + math.sqrt(max(int(b.get("n", 1)), 1))
        s.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#2563eb" '
            f'fill-opacity="0.75" stroke="#1e40af" stroke-width="1"/>'
        )
        s.append(
            f'<text x="{cx:.1f}" y="{cy - r - 4:.1f}" text-anchor="middle" '
            f'font-size="9" fill="#374151">n={_esc(b.get("n"))}</text>'
        )
    s.append(
        f'<text x="{W / 2}" y="{H - 12}" text-anchor="middle" font-size="12" '
        f'fill="#374151">Predicted recall (FSRS)</text>'
    )
    s.append(
        f'<text x="18" y="{H / 2}" text-anchor="middle" font-size="12" fill="#374151" '
        f'transform="rotate(-90 18 {H / 2})">Observed recall</text>'
    )
    s.append("</svg>")
    svg = "\n".join(s) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(
        f"wrote {os.path.normpath(OUT)}  ({len(bins)} bins, ECE {ece}, "
        f"Brier {brier_m} vs {brier_b})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
