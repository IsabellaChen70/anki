#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Desktop <-> phone scoring parity: the JS port must equal the Python core.

Vantage scores on two engines: the Python core (`anki.vantage.scoring`, desktop)
and a hand-written JS port (`vantage_addon/web/mobile_scoring.js`, phone). The
fair critique was that this dual implementation can silently DRIFT with no test.
This asserts the deterministic transforms agree bit-for-bit (to 1e-6) on identical
inputs -- the desktop/mobile parity mandate:

    thetaToScale, mapAbilityToScale, irtProb, irtInformation, and the full
    irtEstimate EAP (theta, posterior SD, test information).

It runs the JS in node via `parity_check.js`. If no node is found the test SKIPS
(exit 0) rather than failing, so a node-less checkout can still run the rest.

Deterministic. Writes vantage_tools/scoring_parity_results.json.
Re-run:  out/pyenv/bin/python vantage_tools/scoring_parity_test.py   (or `just parity`)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from anki.vantage.scoring import (
    IrtItem,
    ScoringConfig,
    irt_estimate,
    irt_information,
    irt_prob,
    map_ability_to_scale,
    theta_to_scale,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RESULTS_PATH = os.path.join(HERE, "scoring_parity_results.json")
MOBILE_JS = os.path.join(REPO, "vantage_addon", "web", "mobile_scoring.js")
PARITY_JS = os.path.join(HERE, "parity_check.cjs")
TOL = 1e-6

THETAS = [-2.0, -1.0, -0.3, 0.0, 0.5, 1.0, 2.5]
ABILITIES = [0.3, 0.4, 0.5, 0.7, 0.9, 0.95]
TRIPLES = [[0.0, 1.0, 0.0], [0.5, 1.2, -0.5], [-1.0, 0.8, 0.7], [2.0, 1.5, 1.0]]
ITEM_SETS = [
    [
        {"correct": 1, "a": 1.0, "b": 0.0},
        {"correct": 0, "a": 1.2, "b": 0.5},
        {"correct": 1, "a": 0.8, "b": -0.5},
    ],
    [
        {"correct": 1, "a": 1.0, "b": -1.0},
        {"correct": 1, "a": 1.0, "b": 0.0},
        {"correct": 0, "a": 1.0, "b": 1.0},
        {"correct": 1, "a": 1.3, "b": 0.2},
        {"correct": 0, "a": 0.9, "b": -0.3},
    ],
]


def _find_node() -> str | None:
    for cand in (
        os.path.join(REPO, "out", "extracted", "node", "bin", "node"),
        os.path.join(REPO, "out", "extracted", "node", "node.exe"),
    ):
        if os.path.exists(cand):
            return cand
    return shutil.which("node")


def python_side(cfg: ScoringConfig) -> dict:
    out = {
        "thetaToScale": [theta_to_scale(t, cfg) for t in THETAS],
        "mapAbilityToScale": [map_ability_to_scale(a, cfg) for a in ABILITIES],
        "irtProb": [irt_prob(t, a, b) for (t, a, b) in TRIPLES],
        "irtInformation": [irt_information(t, a, b) for (t, a, b) in TRIPLES],
        "irtEstimate": [],
    }
    for items in ITEM_SETS:
        e = irt_estimate(
            [IrtItem(correct=d["correct"], a=d["a"], b=d["b"]) for d in items], cfg
        )
        out["irtEstimate"].append([e.theta, e.theta_sd, e.information])
    return out


def js_side(node: str) -> dict:
    inp = {
        "thetas": THETAS,
        "abilities": ABILITIES,
        "triples": TRIPLES,
        "itemSets": ITEM_SETS,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(inp, fh)
        inpath = fh.name
    try:
        res = subprocess.run(
            [node, PARITY_JS, MOBILE_JS, inpath],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        os.unlink(inpath)
    if res.returncode != 0:
        raise RuntimeError(f"node parity harness failed: {res.stderr.strip()}")
    return json.loads(res.stdout)


def _flatten(d: dict) -> list[tuple[str, float]]:
    flat: list[tuple[str, float]] = []
    for key, val in d.items():
        for i, item in enumerate(val):
            if isinstance(item, list):
                for j, x in enumerate(item):
                    flat.append((f"{key}[{i}][{j}]", float(x)))
            else:
                flat.append((f"{key}[{i}]", float(item)))
    return flat


def main() -> int:
    cfg = ScoringConfig()
    node = _find_node()
    if node is None:
        res = {"skipped": True, "reason": "no node binary found", "tolerance": TOL}
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print("SKIP: no node binary; cannot run the JS side of the parity test.")
        return 0

    py = python_side(cfg)
    js = js_side(node)
    py_flat = dict(_flatten(py))
    js_flat = dict(_flatten(js))

    mismatches = []
    for key, pv in py_flat.items():
        jv = js_flat.get(key)
        if jv is None or abs(pv - jv) > TOL:
            mismatches.append({"key": key, "python": pv, "js": jv})

    n = len(py_flat)
    max_abs = max(
        (abs(pv - js_flat[k]) for k, pv in py_flat.items() if k in js_flat), default=0.0
    )
    passed = not mismatches and set(py_flat) == set(js_flat)

    print("DESKTOP <-> PHONE SCORING PARITY (Python core vs mobile_scoring.js)")
    print(f"  node: {node}")
    print(f"  compared {n} deterministic values across 5 transforms")
    print(f"  max abs difference: {max_abs:.2e}   tolerance: {TOL:.0e}")
    if mismatches:
        print(f"  MISMATCHES ({len(mismatches)}):")
        for m in mismatches[:12]:
            print(f"    {m['key']}: py={m['python']} js={m['js']}")
    print("\n" + "-" * 62)
    print(f"RESULT: {'PARITY HOLDS' if passed else 'DRIFT DETECTED'}")
    print("-" * 62)

    res = {
        "passed": passed,
        "compared_values": n,
        "max_abs_diff": max_abs,
        "tolerance": TOL,
        "mismatches": mismatches,
        "transforms": ["thetaToScale", "mapAbilityToScale", "irtProb", "irtInformation", "irtEstimate"],
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, HERE)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
