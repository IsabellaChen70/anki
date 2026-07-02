#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage held-out evaluation: does the memory model beat a simpler baseline?

MODEL UNDER TEST
    FSRS (the memory model shipped in Anki's Rust core; open source, project
    "fsrs-rs"). The Vantage layer itself adds NO trained model: its scores are
    deterministic statistics (mean retrievability, Wilson/Beta intervals,
    bootstrap CIs). The one predictive model the app relies on is FSRS, so that
    is what we hold out and compare against a baseline here.

SETUP (reproducible, someone else can re-run and get the same numbers)
    1. Build the seeded exam collection (build_exam_collection.build, fixed seed)
       so its FSRS memory states come from real reviews through the real engine.
    2. Per card, take FSRS's predicted recall R (extract_fsrs_retrievability, the
       same function the browser and scheduler use) and the actual outcome of its
       most recent review (pass = rating 2..4).
    3. Split cards into fit/held-out 80/20 with a fixed seed.
    4. On the HELD-OUT cards only, score two predictors with the Brier score
       (mean squared error of the probability; lower is better):
          - model:    FSRS predicted recall R
          - baseline: predict the fit-set base rate for everyone (no per-card info)

    A lower held-out Brier for FSRS than for the base rate means the model carries
    real per-card signal a simpler method does not.

HONESTY NOTE
    This runs on a simulated study history (documented in build_exam_collection),
    so the absolute numbers validate the *methodology and pipeline*, not a real
    cohort. FSRS's real-world superiority over SM-2 is established by its authors
    on hundreds of millions of held-out reviews (github.com/open-spaced-
    repetition/fsrs-rs); this harness is the re-runnable local check.

Usage:
    out/pyenv/bin/python vantage_tools/evaluate_memory.py
"""

from __future__ import annotations

import os
import random
import tempfile
import time

import build_exam_collection as bx
from anki.collection import Collection

SPLIT_SEED = 1234
HELD_OUT_FRAC = 0.20


def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def gather(col: Collection) -> list[tuple[int, float, int]]:
    """(card_id, predicted_recall, actual_last_outcome) for cards with both."""
    now = int(time.time())
    r_by_cid = {
        cid: r
        for cid, r in col.db.all(
            "select c.id, extract_fsrs_retrievability("
            "c.data, case when c.odue!=0 then c.odue else c.due end, c.ivl, ?, ?, ?) "
            "from cards c where c.queue != -1",
            col.sched.today,
            col.sched.day_cutoff,
            now,
        )
        if r is not None
    }
    # ease of each card's most recent review; SQLite returns the row of max(id)
    last = {
        cid: (1 if ease >= 2 else 0)
        for cid, ease, _ in col.db.all(
            "select cid, ease, max(id) from revlog where ease between 1 and 4 group by cid"
        )
    }
    return [(cid, r, last[cid]) for cid, r in r_by_cid.items() if cid in last]


def main() -> None:
    path = os.path.join(tempfile.mkdtemp(), "eval.anki2")
    bx.build(path)  # seeded, deterministic
    col = Collection(path)
    rows = gather(col)
    col.close()

    rng = random.Random(SPLIT_SEED)
    rng.shuffle(rows)
    cut = int(len(rows) * (1 - HELD_OUT_FRAC))
    fit, held = rows[:cut], rows[cut:]

    base_rate = sum(o for _, _, o in fit) / len(fit)
    model_pairs = [(r, o) for _, r, o in held]
    base_pairs = [(base_rate, o) for _, _, o in held]
    b_model = brier(model_pairs)
    b_base = brier(base_pairs)

    print(f"cards with recall + outcome: {len(rows)}  (fit {len(fit)}, held-out {len(held)})")
    print(f"fit-set base pass rate: {base_rate:.3f}")
    print()
    print(f"{'predictor':<26}{'held-out Brier (lower=better)'}")
    print(f"{'FSRS predicted recall':<26}{b_model:.4f}")
    print(f"{'base-rate baseline':<26}{b_base:.4f}")
    print()
    improvement = (b_base - b_model) / b_base * 100 if b_base else 0.0
    if b_model < b_base:
        print(f"result: FSRS BEATS the baseline on held-out data ({improvement:.1f}% lower Brier)")
    else:
        print(f"result: FSRS does NOT beat the baseline here ({improvement:.1f}%)")


if __name__ == "__main__":
    main()
