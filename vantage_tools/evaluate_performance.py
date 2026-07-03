#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage held-out PERFORMANCE evaluation: does a simple performance model predict
accuracy on HELD-OUT application items better than a base-rate baseline, without
leakage?

MODEL UNDER TEST
    The performance model sketched in spec-readiness-score.md (~L51-60): a logistic
    regression that predicts P(correct on a novel application item) from four
    features
        features = [ topic_mastery,    # mean FSRS retrievability for the topic
                     item_difficulty,  # author/AI estimate
                     latency_signal,   # answer timing (accurate-but-slow edge case)
                     topic_coverage ]  # share of the topic's concepts covered
    implemented here in plain stdlib Python (gradient descent, no numpy/sklearn).

PRE-REGISTERED (written before looking at any result)
    - Main metric: HELD-OUT accuracy AND HELD-OUT Brier score (plus log-loss).
    - Baseline: predict the FIT-set mean P(correct) for every held-out item
      (a constant predictor; for accuracy this is the majority-class predictor).
    - SUCCESS CRITERION (both must hold on the held-out split):
          Brier(model)    <  Brier(baseline)      AND
          accuracy(model)  >  accuracy(baseline)
      If either fails, the result is reported honestly as NOT beating baseline.
    - Also reported (descriptive, not a pass/fail gate): a reliability table over
      predicted-probability deciles (predicted vs observed) and its Expected
      Calibration Error (ECE, n-weighted mean |predicted - observed|).

DATASET (seeded, documented, synthetic -- there is no real cohort yet)
    We generate CONCEPTS, each with a topic_mastery and topic_coverage, then a
    handful of application ITEMS per concept, each with an item_difficulty and a
    latency. The outcome is drawn as
        p_true = sigmoid( bias + w . centered_features )
        y      ~ Bernoulli(p_true),  then flipped to a fair coin with prob NOISE
    using the PRE-REGISTERED generator coefficients in TRUE_COEFFS below. The model
    does NOT see these coefficients; it must recover the structure from data.

    This validates the PIPELINE and METHODOLOGY (train/held-out split, no leakage,
    honest scoring) -- it is NOT evidence about real students. The real feature
    weights can only come from a real cohort of graded application items, which is
    Step-4 (out of scope here; see spec-readiness-score.md D-SCORE1 and
    spec-eval-harness.md).

NO LEAKAGE (spec-eval-harness.md: "Train / held-out split (no leakage)")
    topic_mastery and topic_coverage are CONCEPT-level features, so we split by
    CONCEPT: every item of a concept goes entirely to fit or entirely to held-out.
    A concept (and therefore any of its items, and its mastery/coverage values) is
    never in both halves. The script asserts the fit/held concept-id sets are
    disjoint and prints the check. Feature standardization uses FIT-set statistics
    only, then is applied to the held-out set (the held-out labels never touch the
    fit).

Usage:
    out/pyenv/bin/python vantage_tools/evaluate_performance.py
    (writes vantage_tools/performance_results.json and docs/results-performance.md)
"""

from __future__ import annotations

import json
import math
import os
import random

# --------------------------------------------------------------------------- #
# Pre-registered configuration (fixed before running; change only deliberately) #
# --------------------------------------------------------------------------- #
DATA_SEED = 20260702  # generates features + outcomes
SPLIT_SEED = 909  # assigns concepts to fit / held-out

N_CONCEPTS = 80
ITEMS_PER_CONCEPT_MIN = 6
ITEMS_PER_CONCEPT_MAX = 10  # -> ~640 items, so held-out deciles are populated
HELD_OUT_CONCEPT_FRAC = 0.20  # split BY CONCEPT (grouped), not by item
LABEL_FLIP_NOISE = 0.05  # irreducible noise: 5% of labels become a fair coin

# True data-generating coefficients, on CENTERED features (see generate_dataset).
# Signs encode the domain story: more mastery/coverage helps; harder items and
# slower answers hurt. The model never sees these.
TRUE_COEFFS = {
    "bias": 0.30,
    "mastery": 3.0,  # (mastery - 0.5),        higher recall -> more likely correct
    "difficulty": -2.6,  # (difficulty - 0.5),    harder item -> less likely correct
    "latency": -0.7,  # (latency_s - 45) / 18,  slower answer -> less likely correct
    "coverage": 1.4,  # (coverage - 0.5),      more of topic covered -> more likely
}

# Plain-Python logistic-regression training (deterministic: zero init, no PRNG).
LEARNING_RATE = 0.3
ITERATIONS = 5000
L2 = 1e-4  # tiny ridge on weights (not bias) for numerical stability
DECILES = 10

FEATURES = ("mastery", "difficulty", "latency", "coverage")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RESULTS_JSON = os.path.join(HERE, "performance_results.json")


# --------------------------------------------------------------------------- #
# Small numeric helpers (stdlib only)                                          #
# --------------------------------------------------------------------------- #
def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def logloss(pairs: list[tuple[float, int]]) -> float:
    eps = 1e-12
    total = 0.0
    for p, o in pairs:
        p = min(1 - eps, max(eps, p))
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / len(pairs)


def accuracy(pairs: list[tuple[float, int]]) -> float:
    return sum(1 for p, o in pairs if (1 if p >= 0.5 else 0) == o) / len(pairs)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion (deterministic; the honest 'range')."""
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


# --------------------------------------------------------------------------- #
# Dataset (seeded, synthetic)                                                  #
# --------------------------------------------------------------------------- #
def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def generate_dataset(seed: int) -> list[dict]:
    """Seeded synthetic application items grouped under concepts.

    Concept-level: topic_mastery, topic_coverage.  Item-level: item_difficulty,
    latency_s.  Outcome ~ Bernoulli(sigmoid(bias + w . centered_features)) with a
    pre-registered fair-coin label-flip noise.  Fully determined by ``seed``.
    """
    rng = random.Random(seed)
    items: list[dict] = []
    item_id = 0
    for cid in range(N_CONCEPTS):
        mastery = _clip(rng.gauss(0.60, 0.18), 0.0, 1.0)  # concept-level
        coverage = _clip(rng.gauss(0.55, 0.20), 0.0, 1.0)  # concept-level
        n_items = rng.randint(ITEMS_PER_CONCEPT_MIN, ITEMS_PER_CONCEPT_MAX)
        for _ in range(n_items):
            difficulty = _clip(rng.gauss(0.50, 0.20), 0.0, 1.0)  # item-level
            latency_s = _clip(rng.gauss(45.0, 18.0), 5.0, 150.0)  # item-level
            z = (
                TRUE_COEFFS["bias"]
                + TRUE_COEFFS["mastery"] * (mastery - 0.5)
                + TRUE_COEFFS["difficulty"] * (difficulty - 0.5)
                + TRUE_COEFFS["latency"] * ((latency_s - 45.0) / 18.0)
                + TRUE_COEFFS["coverage"] * (coverage - 0.5)
            )
            p_true = sigmoid(z)
            y = 1 if rng.random() < p_true else 0
            if rng.random() < LABEL_FLIP_NOISE:  # irreducible label noise
                y = 1 if rng.random() < 0.5 else 0
            items.append(
                {
                    "item_id": item_id,
                    "concept_id": cid,
                    "mastery": mastery,
                    "difficulty": difficulty,
                    "latency": latency_s,
                    "coverage": coverage,
                    "p_true": p_true,
                    "y": y,
                }
            )
            item_id += 1
    return items


def split_by_concept(
    items: list[dict], seed: int, held_frac: float
) -> tuple[list[dict], list[dict], set[int], set[int]]:
    """Group split: whole concepts go to fit or held-out (no item is in both)."""
    concept_ids = sorted({it["concept_id"] for it in items})
    rng = random.Random(seed)
    rng.shuffle(concept_ids)
    n_held = max(1, round(len(concept_ids) * held_frac))
    held_ids = set(concept_ids[:n_held])
    fit_ids = set(concept_ids[n_held:])
    fit = [it for it in items if it["concept_id"] in fit_ids]
    held = [it for it in items if it["concept_id"] in held_ids]
    return fit, held, fit_ids, held_ids


# --------------------------------------------------------------------------- #
# Logistic regression (plain-Python gradient descent)                         #
# --------------------------------------------------------------------------- #
def _matrix(items: list[dict]) -> tuple[list[list[float]], list[int]]:
    x = [[it[f] for f in FEATURES] for it in items]
    y = [it["y"] for it in items]
    return x, y


def fit_scaler(x: list[list[float]]) -> tuple[list[float], list[float]]:
    """Mean/std per feature, computed on the FIT set only (no leakage)."""
    n = len(x)
    dim = len(FEATURES)
    means = [sum(row[j] for row in x) / n for j in range(dim)]
    stds = []
    for j in range(dim):
        var = sum((row[j] - means[j]) ** 2 for row in x) / n
        stds.append(math.sqrt(var) if var > 1e-12 else 1.0)
    return means, stds


def apply_scaler(
    x: list[list[float]], means: list[float], stds: list[float]
) -> list[list[float]]:
    return [[(row[j] - means[j]) / stds[j] for j in range(len(FEATURES))] for row in x]


def train_logreg(
    x: list[list[float]], y: list[int]
) -> tuple[list[float], float]:
    """Full-batch gradient descent on standardized features. Deterministic."""
    n = len(x)
    dim = len(FEATURES)
    w = [0.0] * dim
    b = 0.0
    for _ in range(ITERATIONS):
        gw = [0.0] * dim
        gb = 0.0
        for i in range(n):
            xi = x[i]
            p = sigmoid(sum(w[j] * xi[j] for j in range(dim)) + b)
            err = p - y[i]
            for j in range(dim):
                gw[j] += err * xi[j]
            gb += err
        for j in range(dim):
            w[j] -= LEARNING_RATE * (gw[j] / n + L2 * w[j])
        b -= LEARNING_RATE * (gb / n)
    return w, b


def predict(w: list[float], b: float, x: list[list[float]]) -> list[float]:
    dim = len(FEATURES)
    return [sigmoid(sum(w[j] * row[j] for j in range(dim)) + b) for row in x]


# --------------------------------------------------------------------------- #
# Calibration                                                                  #
# --------------------------------------------------------------------------- #
def reliability_deciles(pairs: list[tuple[float, int]], k: int = DECILES) -> list[dict]:
    """Equal-frequency deciles: sort by predicted p, split into k groups."""
    ordered = sorted(pairs, key=lambda t: t[0])
    n = len(ordered)
    rows = []
    for i in range(k):
        grp = ordered[i * n // k : (i + 1) * n // k]
        if not grp:
            rows.append({"decile": i + 1, "n": 0})
            continue
        mean_pred = sum(p for p, _ in grp) / len(grp)
        observed = sum(o for _, o in grp) / len(grp)
        rows.append(
            {
                "decile": i + 1,
                "n": len(grp),
                "pred_lo": round(grp[0][0], 4),
                "pred_hi": round(grp[-1][0], 4),
                "mean_predicted": round(mean_pred, 4),
                "observed_rate": round(observed, 4),
                "gap": round(abs(mean_pred - observed), 4),
            }
        )
    return rows


def ece(bins: list[dict], n_total: int) -> float:
    if not n_total:
        return 0.0
    return sum(b["n"] / n_total * b["gap"] for b in bins if b.get("n"))


# --------------------------------------------------------------------------- #
# Reporting                                                                     #
# --------------------------------------------------------------------------- #
def _resolve_results_md() -> str:
    """Vantage docs (where the specs live) if found, else this repo's docs/."""
    candidates = [
        os.path.join(REPO_ROOT, os.pardir, "mcat anki", "docs"),
        os.path.join(REPO_ROOT, "docs"),
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "spec-readiness-score.md")):
            return os.path.abspath(os.path.join(d, "results-performance.md"))
    return os.path.abspath(os.path.join(candidates[0], "results-performance.md"))


def write_markdown(path: str, r: dict) -> None:
    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    verdict = "BEATS" if r["beats_baseline"] else "does NOT beat"
    lines = []
    lines.append("# Vantage performance model: held-out evaluation")
    lines.append("")
    lines.append(
        "> Generated by `vantage_tools/evaluate_performance.py` (seeded, "
        "stdlib-only, re-runnable). Every number below is produced by the run, "
        "not hand-typed. Validates spec-readiness-score.md ~L51-60."
    )
    lines.append("")
    lines.append("## What this measures")
    lines.append("")
    lines.append(
        "Whether a simple logistic-regression performance model predicts "
        "`P(correct)` on **held-out** application items better than a base-rate "
        "baseline, from the four spec features "
        "`[topic_mastery, item_difficulty, latency_signal, topic_coverage]`, with "
        "a leakage-free split."
    )
    lines.append("")
    lines.append("## Pre-registered (before results)")
    lines.append("")
    lines.append(
        "- Main metric: held-out **accuracy** and held-out **Brier** (plus log-loss)."
    )
    lines.append(
        "- Baseline: predict the fit-set mean `P(correct)` for every held-out item."
    )
    lines.append(
        "- Success criterion (both): `Brier(model) < Brier(baseline)` **and** "
        "`accuracy(model) > accuracy(baseline)`."
    )
    lines.append("")
    lines.append("## Dataset (seeded, synthetic)")
    lines.append("")
    lines.append(
        f"- {r['n_items']} synthetic application items across {r['n_concepts']} "
        f"concepts (data seed {r['data_seed']}, split seed {r['split_seed']})."
    )
    lines.append(
        f"- Split **by concept** (grouped, no leakage): "
        f"fit = {r['fit_items']} items / {r['fit_concepts']} concepts, "
        f"held-out = {r['held_items']} items / {r['held_concepts']} concepts."
    )
    lines.append(
        f"- Leakage check (fit/held concept ids disjoint): "
        f"**{'clean' if r['leakage_clean'] else 'LEAK DETECTED'}**."
    )
    lines.append(
        f"- Outcomes drawn from `sigmoid(bias + w . features)` with pre-registered "
        f"coefficients {json.dumps(r['true_coeffs'])} plus "
        f"{pct(r['label_flip_noise'])} fair-coin label noise. The model does not "
        f"see these coefficients."
    )
    lines.append("")
    lines.append(
        "**Honesty note.** This is synthetic data, so the numbers validate the "
        "pipeline and methodology (split, no-leakage, honest scoring), **not** real "
        "students. Real feature weights need a real cohort of graded application "
        "items (Step-4; see spec-readiness-score.md D-SCORE1)."
    )
    lines.append("")
    lines.append("## Result (held-out split)")
    lines.append("")
    lines.append("| predictor | accuracy | Brier | log-loss |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(
        f"| logistic model | {r['accuracy_model']:.4f} | "
        f"{r['brier_model']:.4f} | {r['logloss_model']:.4f} |"
    )
    lines.append(
        f"| base-rate baseline | {r['accuracy_baseline']:.4f} | "
        f"{r['brier_baseline']:.4f} | {r['logloss_baseline']:.4f} |"
    )
    lines.append("")
    lines.append(
        f"Held-out accuracy 95% Wilson interval: model "
        f"[{r['accuracy_model_ci'][0]:.3f}, {r['accuracy_model_ci'][1]:.3f}], "
        f"baseline [{r['accuracy_baseline_ci'][0]:.3f}, "
        f"{r['accuracy_baseline_ci'][1]:.3f}]."
    )
    lines.append("")
    lines.append(
        f"**Verdict: the model {verdict} the baseline** "
        f"(Brier {pct(r['brier_improvement'])} "
        f"{'lower' if r['brier_improvement'] >= 0 else 'higher'}, accuracy "
        f"{r['accuracy_model'] - r['accuracy_baseline']:+.4f}). "
        f"Success criterion (Brier lower AND accuracy higher): "
        f"**{'PASS' if r['beats_baseline'] else 'FAIL'}**."
    )
    lines.append("")
    lines.append("## Recovered structure (sanity check)")
    lines.append("")
    lines.append(
        "Learned coefficients are on standardized features, so magnitudes are not "
        "directly the generator's; signs and rank should match the domain story."
    )
    lines.append("")
    lines.append("| feature | learned (standardized) | expected sign | match |")
    lines.append("| --- | ---: | :---: | :---: |")
    for f in FEATURES:
        lc = r["coeffs_standardized"][f]
        es = r["expected_signs"][f]
        ok = "yes" if (lc >= 0) == (es >= 0) else "NO"
        lines.append(f"| {f} | {lc:+.3f} | {'+' if es >= 0 else '-'} | {ok} |")
    lines.append("")
    lines.append(f"All signs match generator: **{r['all_signs_match']}**.")
    lines.append("")
    lines.append("## Calibration (held-out, equal-frequency deciles)")
    lines.append("")
    lines.append("| decile | n | pred range | mean predicted | observed | \\|gap\\| |")
    lines.append("| ---: | ---: | :--- | ---: | ---: | ---: |")
    for b in r["reliability_deciles"]:
        if not b.get("n"):
            lines.append(f"| {b['decile']} | 0 | (empty) | | | |")
            continue
        lines.append(
            f"| {b['decile']} | {b['n']} | {b['pred_lo']:.3f}-{b['pred_hi']:.3f} | "
            f"{b['mean_predicted']:.3f} | {b['observed_rate']:.3f} | {b['gap']:.3f} |"
        )
    lines.append("")
    lines.append(
        f"Expected Calibration Error (ECE, n-weighted mean gap): "
        f"**{r['ece']:.4f}**."
    )
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```")
    lines.append("out/pyenv/bin/python vantage_tools/evaluate_performance.py")
    lines.append("```")
    lines.append("")
    lines.append(
        "Deterministic: fixed data seed, split seed, and zero-initialised "
        "gradient descent (no PRNG in training). Writes "
        "`vantage_tools/performance_results.json` and this file."
    )
    lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    items = generate_dataset(DATA_SEED)
    fit, held, fit_ids, held_ids = split_by_concept(
        items, SPLIT_SEED, HELD_OUT_CONCEPT_FRAC
    )
    leakage_clean = fit_ids.isdisjoint(held_ids)
    assert leakage_clean, "LEAKAGE: a concept is in both fit and held-out"

    x_fit_raw, y_fit = _matrix(fit)
    x_held_raw, y_held = _matrix(held)
    means, stds = fit_scaler(x_fit_raw)  # fit-set stats only
    x_fit = apply_scaler(x_fit_raw, means, stds)
    x_held = apply_scaler(x_held_raw, means, stds)

    w, b = train_logreg(x_fit, y_fit)
    p_held = predict(w, b, x_held)

    base_rate = sum(y_fit) / len(y_fit)  # fit-set mean P(correct)

    model_pairs = list(zip(p_held, y_held))
    base_pairs = [(base_rate, o) for o in y_held]

    acc_model, acc_base = accuracy(model_pairs), accuracy(base_pairs)
    brier_model, brier_base = brier(model_pairs), brier(base_pairs)
    ll_model, ll_base = logloss(model_pairs), logloss(base_pairs)

    k_model = sum(1 for p, o in model_pairs if (1 if p >= 0.5 else 0) == o)
    k_base = sum(1 for p, o in base_pairs if (1 if p >= 0.5 else 0) == o)
    acc_model_ci = wilson(k_model, len(model_pairs))
    acc_base_ci = wilson(k_base, len(base_pairs))

    bins = reliability_deciles(model_pairs)
    ece_val = ece(bins, len(model_pairs))

    beats = (brier_model < brier_base) and (acc_model > acc_base)
    brier_impr = (brier_base - brier_model) / brier_base if brier_base else 0.0

    # map standardized coeffs back to raw-feature units for interpretability
    coeffs_std = {f: w[j] for j, f in enumerate(FEATURES)}
    coeffs_raw = {f: w[j] / stds[j] for j, f in enumerate(FEATURES)}
    expected_signs = {
        f: (1.0 if TRUE_COEFFS[f] >= 0 else -1.0) for f in FEATURES
    }
    all_signs_match = all(
        (coeffs_std[f] >= 0) == (expected_signs[f] >= 0) for f in FEATURES
    )

    # ---- console report -------------------------------------------------- #
    print("Vantage performance model -- held-out evaluation (synthetic, seeded)")
    print(
        f"items: {len(items)} across {N_CONCEPTS} concepts  "
        f"(data seed {DATA_SEED}, split seed {SPLIT_SEED})"
    )
    print(
        f"split BY CONCEPT (no leakage): fit {len(fit)} items / {len(fit_ids)} "
        f"concepts, held-out {len(held)} items / {len(held_ids)} concepts"
    )
    print(
        f"leakage check (fit/held concept ids disjoint): "
        f"{'CLEAN' if leakage_clean else 'LEAK'}"
    )
    print(f"fit-set base rate P(correct): {base_rate:.4f}\n")

    print(f"{'predictor':<22}{'accuracy':<12}{'Brier':<12}{'log-loss'}   (held-out)")
    print(f"{'logistic model':<22}{acc_model:<12.4f}{brier_model:<12.4f}{ll_model:.4f}")
    print(f"{'base-rate baseline':<22}{acc_base:<12.4f}{brier_base:<12.4f}{ll_base:.4f}")
    print(
        f"\nheld-out accuracy 95% CI: model "
        f"[{acc_model_ci[0]:.3f}, {acc_model_ci[1]:.3f}], "
        f"baseline [{acc_base_ci[0]:.3f}, {acc_base_ci[1]:.3f}]"
    )
    print(
        f"\nBrier: model {brier_model:.4f} vs baseline {brier_base:.4f} "
        f"({brier_impr * 100:+.1f}% {'lower' if brier_impr >= 0 else 'higher'})"
    )
    print(
        f"accuracy: model {acc_model:.4f} vs baseline {acc_base:.4f} "
        f"({acc_model - acc_base:+.4f})"
    )
    print(
        f"\nPRE-REGISTERED success (Brier lower AND accuracy higher): "
        f"{'PASS -- model BEATS baseline' if beats else 'FAIL -- does NOT beat baseline'}\n"
    )

    print("recovered coefficients (standardized features; sign/rank should match DGP):")
    print(f"  {'feature':<12}{'learned':>10}{'exp.sign':>10}{'match':>7}")
    for f in FEATURES:
        ok = "yes" if (coeffs_std[f] >= 0) == (expected_signs[f] >= 0) else "NO"
        print(
            f"  {f:<12}{coeffs_std[f]:>+10.3f}"
            f"{'+' if expected_signs[f] >= 0 else '-':>10}{ok:>7}"
        )
    print(f"  all signs match generator: {all_signs_match}\n")

    print(f"calibration reliability (held-out, {len(model_pairs)} items, deciles):")
    print(f"  {'dec':>3}{'n':>5}{'pred':>9}{'observed':>11}{'|gap|':>8}")
    for bn in bins:
        if not bn.get("n"):
            print(f"  {bn['decile']:>3}{0:>5}   (empty)")
            continue
        bar = "#" * int(round(bn["observed_rate"] * 20))
        print(
            f"  {bn['decile']:>3}{bn['n']:>5}{bn['mean_predicted']:>9.3f}"
            f"{bn['observed_rate']:>11.3f}{bn['gap']:>8.3f}  {bar}"
        )
    print(f"  ECE (n-weighted mean gap): {ece_val:.4f}")

    # ---- persist --------------------------------------------------------- #
    out = {
        "n_items": len(items),
        "n_concepts": N_CONCEPTS,
        "fit_items": len(fit),
        "held_items": len(held),
        "fit_concepts": len(fit_ids),
        "held_concepts": len(held_ids),
        "leakage_clean": leakage_clean,
        "data_seed": DATA_SEED,
        "split_seed": SPLIT_SEED,
        "held_out_concept_frac": HELD_OUT_CONCEPT_FRAC,
        "label_flip_noise": LABEL_FLIP_NOISE,
        "base_rate": round(base_rate, 6),
        "accuracy_model": round(acc_model, 6),
        "accuracy_baseline": round(acc_base, 6),
        "accuracy_model_ci": [round(c, 6) for c in acc_model_ci],
        "accuracy_baseline_ci": [round(c, 6) for c in acc_base_ci],
        "brier_model": round(brier_model, 6),
        "brier_baseline": round(brier_base, 6),
        "brier_improvement": round(brier_impr, 6),
        "logloss_model": round(ll_model, 6),
        "logloss_baseline": round(ll_base, 6),
        "beats_baseline": beats,
        "ece": round(ece_val, 6),
        "reliability_deciles": bins,
        "true_coeffs": TRUE_COEFFS,
        "coeffs_standardized": {f: round(coeffs_std[f], 6) for f in FEATURES},
        "coeffs_raw_units": {f: round(coeffs_raw[f], 6) for f in FEATURES},
        "bias": round(b, 6),
        "expected_signs": {f: expected_signs[f] for f in FEATURES},
        "all_signs_match": all_signs_match,
        "scaler_means": {f: round(means[j], 6) for j, f in enumerate(FEATURES)},
        "scaler_stds": {f: round(stds[j], 6) for j, f in enumerate(FEATURES)},
        "learning_rate": LEARNING_RATE,
        "iterations": ITERATIONS,
        "l2": L2,
        "cohort": "synthetic (generate_dataset); validates methodology, not a real cohort",
    }
    with open(RESULTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_JSON, REPO_ROOT)}")

    md_path = _resolve_results_md()
    write_markdown(md_path, out)
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
