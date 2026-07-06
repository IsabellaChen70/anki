#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage held-out memory calibration: is the retrievability the app SHOWS
calibrated -- when it says p, does a cohort recall at ~p -- and does it beat a
simpler baseline?

WHAT IS UNDER TEST
    The exact retrievability the app displays and schedules on: Anki's shipped
    `extract_fsrs_retrievability` SQL (rslib/src/storage/sqlite.rs) -- FSRS (the
    open-source fsrs-rs engine, default parameters) evaluated on each card's inferred
    memory state. The Vantage layer adds NO trained model of its own; this is the one
    predictive function it leans on, so this is what we hold out.

WHAT THIS CHECK CAN AND CANNOT SHOW (read this before trusting a number)
    On a SIMULATED cohort you cannot honestly test whether FSRS's forgetting curve
    matches human memory: any ground truth you invent (exponential decay, fixed
    stability, ...) differs from FSRS's own assumptions and would conflate model
    mismatch with a wiring bug. So a fair simulation necessarily has the simulated
    learner follow the model, which makes this a PIPELINE self-consistency check --
    still worth running, because a real bug in any of the steps below breaks it:
        - the elapsed-time construction (predicting R at a chosen future delay),
        - the leakage-free split (a card is never in both fit and held-out),
        - the Brier / log-loss / ECE arithmetic and the binning,
        - and R being INFORMATIVE (it must beat a base-rate baseline).
    FSRS's real-world calibration (that the curve fits people) is the authors' result
    on hundreds of millions of held-out reviews
    (github.com/open-spaced-repetition/fsrs-rs); THAT is the headline, cited, not
    re-derived here.

DESIGN
    Each simulated card is studied through Anki's REAL scheduler; every review's
    outcome is drawn from the shipped retrievability at the card's CURRENT memory
    state over the elapsed gap (a learner who follows the model), so cards accumulate
    a realistic spread of memory states. Then, per card, we hold out one fresh test at
    a delay placed (by bisection on the shipped R) to hit a uniformly-drawn target R,
    so every reliability bin is swept; the test outcome is drawn from that predicted R.
    Calibration is predicted R vs the held-out outcome.

    The elapsed-time construction (our now = last_review + delay wiring) is validated by
    a decay-independent identity: stability is DEFINED as the delay at which R = 0.9
    (the shipped curve (1 + (0.9**(-1/decay)-1)*t/S)**(-decay) equals 0.9 at t == S), so
    a self-check asserts R(delay = stability) == 0.9 on every sampled card. The closed
    loop alone would hide such a bug; this catches it.

PRE-REGISTERED (written before looking at any result)
    - skill: held-out Brier + log-loss; FSRS must beat a base-rate baseline (lower
      Brier). A constant base rate carries no per-card information, so beating it means
      the predicted R is informative.
    - calibration: bin the held-out (predicted R, outcome) pairs; report the Expected
      Calibration Error (ECE = n-weighted mean |predicted - observed|).
      CUTOFF: calibrated if ECE < 0.10.  (A null/failed result is reported honestly.)

Usage:
    out/pyenv/bin/python vantage_tools/evaluate_memory.py
    (writes vantage_tools/memory_calibration.json)
"""

from __future__ import annotations

import json
import math
import os
import random
import tempfile

# Reproducibility: Anki derives its interval-fuzz seed from each card's id, which is
# a wall-clock timestamp at creation, so fuzz -- and therefore every downstream
# interval, elapsed gap, and predicted R -- would otherwise vary run to run (same
# BUILD_SEED/SPLIT_SEED, different numbers). ANKI_TEST_MODE is Anki's own switch
# (rslib get_fuzz_seed_for_id_and_reps) that disables fuzz, making this harness
# deterministic. It must be set before the Rust backend first reads it.
os.environ.setdefault("ANKI_TEST_MODE", "1")

from anki import scheduler_pb2  # noqa: E402
from anki.collection import Collection  # noqa: E402

CardAnswer = scheduler_pb2.CardAnswer
RATING_ENUM = {
    "again": CardAnswer.AGAIN,
    "hard": CardAnswer.HARD,
    "good": CardAnswer.GOOD,
    "easy": CardAnswer.EASY,
}

BUILD_SEED = 20260701
SPLIT_SEED = 1234
HELD_OUT_FRAC = 0.20
ECE_CUTOFF = 0.10  # pre-registered: calibrated if ECE below this
N_CARDS = 1500  # enough that the held-out reliability bins are populated, not thin
# Each card is reviewed WHEN THE ENGINE SAYS IT IS DUE (adaptive spacing, as in real
# use), a random number of times in this range. Reviewing at the due interval keeps
# recall near the target retention so the inferred stability grows in a controlled way
# (fixed gaps let a lucky card's stability run away, which then floors its reachable R
# and piles a bin). More reviews -> a more durable card, giving a spread of stabilities.
N_REVIEWS_MIN, N_REVIEWS_MAX = 2, 6
# Keep now = last_review + delay below the shipped SQL's u32 cast of `now` (~year 2106,
# 4.294e9 s); a wrapped `now` would corrupt the elapsed and the predicted R.
U32_SECONDS_CAP = 4_250_000_000
# Held-out test: draw a target predicted R uniformly here and place E* (by per-card
# bisection on the shipped R) to hit it, so all reliability bins are swept, not just
# the high-R ones a blind delay would cluster in.
TARGET_R_LO, TARGET_R_HI = 0.4, 0.99
# Fixed reliability bins over predicted recall R. Pre-registered before results.
BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.0001)]
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "memory_calibration.json")


def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def logloss(pairs: list[tuple[float, int]]) -> float:
    eps = 1e-6
    total = 0.0
    for p, o in pairs:
        p = min(1 - eps, max(eps, p))
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / len(pairs)


def reliability(pairs: list[tuple[float, int]]) -> list[dict]:
    """Per-bin predicted mean vs observed pass rate on held-out data."""
    rows = []
    for lo, hi in BINS:
        members = [(p, o) for p, o in pairs if lo <= p < hi]
        if not members:
            rows.append({"lo": lo, "hi": min(hi, 1.0), "n": 0})
            continue
        mean_pred = sum(p for p, _ in members) / len(members)
        observed = sum(o for _, o in members) / len(members)
        rows.append(
            {
                "lo": lo,
                "hi": min(hi, 1.0),
                "n": len(members),
                "mean_predicted": round(mean_pred, 4),
                "observed_rate": round(observed, 4),
                "gap": round(abs(mean_pred - observed), 4),
            }
        )
    return rows


def ece(bins: list[dict], n_total: int) -> float:
    if not n_total:
        return 0.0
    return sum(b["n"] / n_total * b["gap"] for b in bins if b["n"])


def _answer(col: Collection, card, rating: str, answered_ms: int) -> None:
    """Grade one review through the real scheduler at a chosen timestamp."""
    card.load()
    states = col._backend.get_scheduling_states(card.id)
    answer = CardAnswer(
        card_id=card.id,
        current_state=states.current,
        new_state=getattr(states, rating),
        rating=RATING_ENUM[rating],
        answered_at_millis=answered_ms,
        milliseconds_taken=3000,
    )
    col._backend.answer_card_raw(answer.SerializeToString())


def _stability(col: Collection, cid: int) -> float | None:
    return col.db.scalar(
        "select extract_fsrs_variable(data, 's') from cards where id=?", cid
    )


def _r_at_delay(col: Collection, cid: int, last_secs: int, delay_days: float):
    """Shipped predicted recall for card `cid` at `delay_days` after its last review.
    last_review_time is stored in seconds and the shipped fn uses now - last_review as
    the elapsed, so now = last_review + delay evaluates R at exactly that delay."""
    now_test = last_secs + int(round(delay_days * 86400))
    return col.db.scalar(
        "select extract_fsrs_retrievability("
        "data, case when odue!=0 then odue else due end, ivl, 0, 0, ?) "
        "from cards where id=?",
        now_test,
        cid,
    )


def _delay_for_target_r(
    col: Collection,
    cid: int,
    last_secs: int,
    s_hat: float,
    target: float,
    max_delay_days: float,
) -> float:
    """Delay (days) at which the shipped R for this card equals `target`, by bisection
    on R (monotone decreasing in delay). Uses each card's own curve, so no assumption
    about its decay. hi is capped at `max_delay_days` (the shipped SQL casts `now` to
    u32, so an over-long delay would wrap); if the target is below the reachable floor
    the card simply clamps to that floor, which honestly lands it in the lowest bin."""
    lo, hi = 1e-4 * s_hat, min(1e5 * s_hat, max_delay_days)
    mid = hi
    for _ in range(34):
        mid = 0.5 * (lo + hi)
        r = _r_at_delay(col, cid, last_secs, mid)
        if r is None:
            break
        if r > target:
            lo = mid  # R too high -> need a longer delay
        else:
            hi = mid
    return mid


def build_pairs(path: str) -> list[tuple[int, float, int]]:
    """Drive the real engine over N_CARDS cards (each a learner who follows the model)
    and return one held-out (card_id, predicted_R, outcome) test per card. Predicted R
    is always the shipped SQL; the held-out outcome is drawn from that predicted R."""
    col = Collection(path)
    col.set_config("fsrs", True)
    basic = col.models.by_name("Basic")
    deck_id = col.decks.id("Calibration")
    rng = random.Random(BUILD_SEED)
    # Fixed study anchor (2014-05-13) so the run is fully reproducible: a wall-clock
    # start would shift last_review_time -> the u32-safe delay cap -> a few borderline
    # cards, making results wobble between runs. Absolute date is irrelevant to FSRS
    # (only the elapsed gaps matter); it just needs headroom under the u32 `now` cast.
    start_ms = 1_400_000_000_000
    seq = [0]

    pairs: list[tuple[int, float, int]] = []
    checks: list[float] = []  # |R(delay = stability) - 0.9| self-check (see below)
    for i in range(N_CARDS):
        n_reviews = rng.randint(N_REVIEWS_MIN, N_REVIEWS_MAX)
        note = col.new_note(basic)
        note["Front"] = f"card {i}"
        note["Back"] = "answer"
        col.add_note(note, deck_id)
        card = note.cards()[0]

        seq[0] += 1
        last_ms = start_ms + seq[0]
        _answer(col, card, "good", last_ms)  # acquisition
        cum_days = 0.0
        for _ in range(n_reviews):
            card.load()
            gap = float(max(1, card.ivl))  # review when the engine schedules it
            last_secs = last_ms // 1000
            # outcome for THIS review from the shipped R at the current state over gap
            r_now = _r_at_delay(col, card.id, last_secs, gap)
            if r_now is None:
                r_now = 0.9
            if rng.random() < r_now:
                rating = "good" if rng.random() < 0.85 else "easy"
            else:
                rating = "again"
            cum_days += gap
            seq[0] += 1
            last_ms = start_ms + int(cum_days * 86400 * 1000) + seq[0]
            _answer(col, card, rating, last_ms)

        card.load()
        s_hat = _stability(col, card.id)
        if not s_hat or s_hat <= 0:
            continue
        last_secs = last_ms // 1000
        # Keep now = last + delay under the shipped SQL's u32 cast of `now` (~year 2106);
        # a delay past this would wrap and corrupt R, so it bounds every query below.
        max_delay_days = (U32_SECONDS_CAP - last_secs) / 86400.0

        # Self-check of the elapsed-time construction, independent of the per-card decay:
        # stability is DEFINED as the delay at which R = 0.9 (the shipped forgetting
        # curve is (1 + (0.9**(-1/decay)-1)*t/S)**(-decay), which is 0.9 at t == S). So
        # if our now = last_review + delay wiring is right, R(delay = s_hat) must be 0.9.
        # Only checkable when s_hat itself fits the u32-safe window.
        if len(checks) < 300 and s_hat <= max_delay_days:
            r_at_s = _r_at_delay(col, card.id, last_secs, s_hat)
            if r_at_s is not None:
                checks.append(abs(float(r_at_s) - 0.9))

        # Place the held-out test to hit a uniform target R, so every bin is swept.
        target = rng.uniform(TARGET_R_LO, TARGET_R_HI)
        e_star = _delay_for_target_r(
            col, card.id, last_secs, s_hat, target, max_delay_days
        )
        pred_r = _r_at_delay(col, card.id, last_secs, e_star)
        if pred_r is None:
            continue
        pred_r = float(pred_r)
        outcome = 1 if rng.random() < pred_r else 0
        pairs.append((card.id, pred_r, outcome))

    col.close()

    if checks:
        max_dev = max(checks)
        assert max_dev < 0.02, f"R(delay=stability) != 0.9 (max dev {max_dev:.4f})"
    return pairs


def main() -> int:
    path = os.path.join(tempfile.mkdtemp(), "eval.anki2")
    rows = build_pairs(path)

    # Sanity: predicted R must be a probability and must actually vary (otherwise the
    # binning below is meaningless). Cheap guard, not a substitute for the metrics.
    preds = [r for _, r, _ in rows]
    assert preds and all(0.0 <= p <= 1.0 for p in preds), "predicted R out of [0,1]"
    assert max(preds) - min(preds) > 0.3, "predicted R does not span a usable range"

    rng = random.Random(SPLIT_SEED)
    rng.shuffle(rows)
    cut = int(len(rows) * (1 - HELD_OUT_FRAC))
    fit, held = rows[:cut], rows[cut:]

    base_rate = sum(o for _, _, o in fit) / len(fit)
    model_pairs = [(r, o) for _, r, o in held]
    base_pairs = [(base_rate, o) for _, _, o in held]

    b_model, b_base = brier(model_pairs), brier(base_pairs)
    ll_model, ll_base = logloss(model_pairs), logloss(base_pairs)
    bins = reliability(model_pairs)
    ece_val = ece(bins, len(model_pairs))

    print(
        f"cards with recall + outcome: {len(rows)}  (fit {len(fit)}, held-out {len(held)})"
    )
    print(f"fit-set base pass rate: {base_rate:.3f}\n")
    print(f"{'predictor':<26}{'Brier':<12}{'log-loss'}   (held-out, lower=better)")
    print(f"{'FSRS predicted recall':<26}{b_model:<12.4f}{ll_model:.4f}")
    print(f"{'base-rate baseline':<26}{b_base:<12.4f}{ll_base:.4f}")
    beats = b_model < b_base
    impr = (b_base - b_model) / b_base * 100 if b_base else 0.0
    print(
        f"\nskill: FSRS {'BEATS' if beats else 'does NOT beat'} the baseline "
        f"({impr:+.1f}% Brier)\n"
    )

    print(f"reliability (held-out, {len(model_pairs)} cards; pre-registered bins):")
    print(f"  {'bin':<14}{'n':>4}{'pred':>9}{'observed':>11}{'|gap|':>8}")
    for b in bins:
        if not b["n"]:
            empty_label = f"{b['lo']:.2f}-{b['hi']:.2f}"
            print(f"  {empty_label:<14}{0:>4}   (empty)")
            continue
        label = f"{b['lo']:.2f}-{b['hi']:.2f}"
        bar = "#" * int(round(b["observed_rate"] * 20))
        print(
            f"  {label:<14}{b['n']:>4}{b['mean_predicted']:>9.3f}"
            f"{b['observed_rate']:>11.3f}{b['gap']:>8.3f}  {bar}"
        )
    calibrated = ece_val < ECE_CUTOFF
    print(
        f"\ncalibration: ECE = {ece_val:.3f}  (cutoff {ECE_CUTOFF}) -> "
        f"{'CALIBRATED' if calibrated else 'NOT within cutoff'}"
    )
    thin = len(model_pairs) < 50
    if thin:
        print(
            "  NOTE: held-out n is thin (<50); bins are illustrative and the "
            "aggregate Brier/log-loss is the robust headline."
        )

    out = {
        "held_out_n": len(model_pairs),
        "fit_n": len(fit),
        "base_rate": round(base_rate, 4),
        "brier_model": round(b_model, 4),
        "brier_baseline": round(b_base, 4),
        "logloss_model": round(ll_model, 4),
        "logloss_baseline": round(ll_base, 4),
        "beats_baseline": beats,
        "ece": round(ece_val, 4),
        "ece_cutoff": ECE_CUTOFF,
        "calibrated": calibrated,
        "reliability_bins": bins,
        "split_seed": SPLIT_SEED,
        "held_out_frac": HELD_OUT_FRAC,
        "n_cards": N_CARDS,
        "thin_warning": thin,
        "design": "pipeline self-consistency: learner follows the model; predicted R = "
        "shipped extract_fsrs_retrievability; delay math checked via R(t=stability)=0.9",
        "validates": "elapsed-time construction, leakage-free split, ECE/Brier wiring, "
        "R informative vs base rate -- NOT FSRS-vs-humans (authors' result, cited)",
        "cohort": "simulated; validates calibration pipeline, not a real cohort",
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
