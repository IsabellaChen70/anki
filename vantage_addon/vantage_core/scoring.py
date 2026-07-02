# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — the honest scoring core.

Pure functions only: no Anki/backend imports, no I/O. Everything here is
deterministic given a seed, so it can be unit-tested without a collection.

Three separate scores, each with a range, and an abstention (give-up) rule —
memory != performance != readiness, never blended (decision D8). See
docs/spec-readiness-score.md for the design and the D-SCORE decisions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence

SECTIONS: tuple[str, ...] = ("chem_phys", "bio_biochem", "psych_soc")
SECTION_LABELS: dict[str, str] = {
    "chem_phys": "Chem/Phys",
    "bio_biochem": "Bio/Biochem",
    "psych_soc": "Psych/Soc",
}

# "how sure" levels, ordered.
INSUFFICIENT = "insufficient"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"


@dataclass(frozen=True)
class ScoringConfig:
    """All thresholds live here so they are tunable, not hard-coded (D-SCORE4)."""

    seed: int = 42
    resample_iters: int = 2000
    ci_mass: float = 0.90  # central interval mass (90% -> 5th..95th pct)

    # per-score minimum evidence to show a number at all
    min_cards_memory: int = 20
    min_outcomes_performance: int = 20

    # readiness give-up gate (D10): abstain unless BOTH hold
    giveup_min_reviews: int = 200
    giveup_min_coverage: float = 0.50
    # a section joins the readiness composite only with real reasoning evidence:
    # below this many application outcomes it is excluded (like coverage gating),
    # so a 1-2 item section can't just echo its memory prior back as readiness
    min_outcomes_readiness: int = 5

    # readiness ability -> 118..132 section scale (documented monotonic, D-SCORE1)
    map_low_ability: float = 0.40
    map_low_scale: float = 118.0
    map_high_ability: float = 0.90
    map_high_scale: float = 132.0
    section_scale_min: float = 118.0
    section_scale_max: float = 132.0

    # "high" confidence guards (negative AC: never "high" when wide/thin)
    memory_high_max_width: float = 0.06
    memory_high_min_n: int = 100
    perf_high_max_width: float = 0.10
    perf_high_min_n: int = 60
    ready_high_max_width: float = 4.0  # scale points across a section band
    ready_high_min_coverage: float = 0.65

    # paraphrase test / transfer gap (memory vs application on the same section)
    min_outcomes_transfer: int = 10
    fluency_gap_threshold: float = 0.15
    # card-level paraphrase test (per concept, not per section): a concept links a
    # recall card to its reworded application variants, so it has fewer outcomes
    # than a whole section -> a smaller minimum before we report its gap.
    min_outcomes_transfer_card: int = 3

    # calibration (does a predicted P(correct) match the observed rate?)
    min_outcomes_calibration: int = 15
    calibration_well_within: float = 0.10  # |mean predicted - mean observed| under this = calibrated

    # study pace. Deliberately separate quantities:
    #  - target: scored items until the readiness score is confident (a data
    #    milestone, drives "N more to a confident score", not a study goal).
    #  - per_concept: reasoning questions budgeted per AAMC concept you still
    #    need to get exam-ready. The daily goal is (concepts left x this) over
    #    the days left, so it scales to real exam breadth, not a fixed number.
    #  - floor: never prescribe fewer than a few reasoning items a day.
    pace_reasoning_target: int = 60
    pace_reasoning_per_concept: int = 10
    pace_reasoning_floor: int = 3

    # item-level confidence calibration (metacognition)
    min_confidence_items: int = 10
    overconfident_sure_max: float = 0.85  # "sure" but below this accuracy = overconfident
    underconfident_guess_min: float = 0.55  # "guess" but above this accuracy = too cautious

    # mistake taxonomy (why misses happen)
    min_mistakes: int = 4

    # pacing coach (time per question vs the real section budget)
    min_pace_per_section: int = 3
    min_pace_total: int = 8

    # score trajectory (project readiness to exam day)
    min_trajectory_days: int = 2

    # adaptive plan: a concept is "content-ready" for reasoning practice once its
    # recall clears this line; below it (or uncovered) it is a content gap to study
    content_ready_recall: float = 0.80

    # readiness projection: how strongly section memory (recall) priors the
    # application-ability estimate before reasoning evidence overrides it. Small,
    # so a handful of real reasoning items dominates. In pseudo-observations.
    projection_prior_strength: float = 8.0

    # --- IRT latent-ability readiness (2PL, EAP over a fixed quadrature grid) --
    # Which readiness path feeds the dashboard. When on, the IRT score is used
    # only if it clears every honesty gate; otherwise we fall back to the classic
    # ability->scale readiness. Both paths stay available (additive).
    readiness_use_irt: bool = True
    # 2PL item defaults when an item carries no calibrated parameters yet: b is
    # difficulty on the latent axis (0 = average), a is discrimination (1 =
    # standard). Seeded from a fixed, reasonable prior so a fresh item bank still
    # yields an estimate; real item metadata overrides these when present.
    irt_default_difficulty: float = 0.0
    irt_default_discrimination: float = 1.0
    # EAP quadrature: a fixed, deterministic grid over the ability axis with a
    # normal prior. No PRNG anywhere, so the mobile JS port reproduces theta
    # bit-for-bit (desktop/mobile parity rule).
    irt_prior_mean: float = 0.0
    irt_prior_sd: float = 1.0
    irt_grid_points: int = 61
    irt_theta_min: float = -4.0
    irt_theta_max: float = 4.0
    # theta (logits) -> 118..132 section scale: a documented monotonic linear map
    # centered on the scale midpoint. per_theta = scale points per unit ability.
    irt_scale_midpoint: float = 125.0
    irt_scale_per_theta: float = 3.0
    # a section joins the IRT composite only once its TEST INFORMATION (sum of
    # item Fisher information at the estimate) clears this line -- the IRT analogue
    # of a minimum sample size, so a thin/uninformative section can't post a
    # confident-looking score.
    irt_min_information: float = 4.0


@dataclass
class Band:
    """A point estimate with a likely range [low, high]."""

    point: float
    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low

    def rounded(self, ndigits: int = 3) -> "Band":
        return Band(
            round(self.point, ndigits),
            round(self.low, ndigits),
            round(self.high, ndigits),
        )


@dataclass
class ScoreResult:
    kind: str  # "memory" | "performance" | "readiness"
    abstained: bool
    how_sure: str
    reasons: list[str] = field(default_factory=list)
    band: Optional[Band] = None
    coverage: float = 0.0
    n: int = 0
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# small numeric helpers (stdlib only, so tests need no third-party deps)
# --------------------------------------------------------------------------- #
def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile; q in [0, 1]. `sorted_vals` must be sorted."""
    if not sorted_vals:
        raise ValueError("percentile of empty sequence")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_vals[int(pos)])
    frac = pos - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(sorted_vals[hi]) * frac


def _ci_bounds(mass: float) -> tuple[float, float]:
    tail = (1.0 - mass) / 2.0
    return tail, 1.0 - tail


def bootstrap_mean_ci(
    values: Sequence[float], cfg: ScoringConfig, rng: random.Random
) -> Band:
    """Percentile bootstrap CI for the mean of `values`."""
    n = len(values)
    point = sum(values) / n
    if n == 1:
        return Band(point, point, point)
    means = []
    for _ in range(cfg.resample_iters):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo_q, hi_q = _ci_bounds(cfg.ci_mass)
    return Band(point, _percentile(means, lo_q), _percentile(means, hi_q))


def wilson_interval(k: int, n: int, mass: float) -> Band:
    """Wilson score interval for a binomial proportion (better than normal for small n)."""
    if n == 0:
        raise ValueError("wilson_interval of zero trials")
    p = k / n
    # two-sided z for the requested central mass
    z = _inv_norm_cdf(1.0 - (1.0 - mass) / 2.0)
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return Band(p, clamp(center - half, 0.0, 1.0), clamp(center + half, 0.0, 1.0))


def _inv_norm_cdf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def brier(pairs: Sequence[tuple[float, int]]) -> float:
    """Brier score: mean((predicted - outcome)^2). Lower is better; 0 is perfect."""
    if not pairs:
        raise ValueError("brier of empty sequence")
    return sum((pred - actual) ** 2 for pred, actual in pairs) / len(pairs)


# --------------------------------------------------------------------------- #
# memory score  (mean FSRS retrievability R over seen cards, with a range)
# --------------------------------------------------------------------------- #
def memory_score(r_values: Sequence[float], coverage: float, cfg: ScoringConfig) -> ScoreResult:
    n = len(r_values)
    if n < cfg.min_cards_memory:
        return ScoreResult(
            kind="memory",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=[f"only {n} cards with a memory state (need >= {cfg.min_cards_memory})"],
            coverage=coverage,
            n=n,
        )
    # Deterministic normal approximation of the mean's range (mean +- z * SE), so
    # desktop and the mobile JS port compute an identical band from the same
    # cards; a Monte-Carlo bootstrap could not be reproduced bit-for-bit.
    vals = [clamp(r, 0.0, 1.0) for r in r_values]
    mean = sum(vals) / n
    sd = 0.0 if n < 2 else math.sqrt(sum((x - mean) ** 2 for x in vals) / (n - 1))
    z = 1.6448536269514722  # 90% two-sided normal quantile
    se = sd / math.sqrt(n)
    band = Band(mean, clamp(mean - z * se, 0.0, 1.0), clamp(mean + z * se, 0.0, 1.0))
    how_sure = HIGH if (band.width <= cfg.memory_high_max_width and n >= cfg.memory_high_min_n) \
        else MEDIUM if band.width <= 2 * cfg.memory_high_max_width else LOW
    reasons = [
        f"mean retrievability {band.point:.0%} over {n} seen cards",
        f"range width {band.width:.0%}",
    ]
    return ScoreResult(
        kind="memory",
        abstained=False,
        how_sure=how_sure,
        reasons=reasons,
        band=band.rounded(),
        coverage=coverage,
        n=n,
    )


# --------------------------------------------------------------------------- #
# performance score  (accuracy on application/reworded items, with a range)
# --------------------------------------------------------------------------- #
def performance_score(
    outcomes: Sequence[int], coverage: float, cfg: ScoringConfig
) -> ScoreResult:
    """`outcomes`: 1 = correct, 0 = incorrect on a novel application item."""
    n = len(outcomes)
    if n < cfg.min_outcomes_performance:
        return ScoreResult(
            kind="performance",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=[
                f"only {n} application-item outcomes (need >= {cfg.min_outcomes_performance})"
            ],
            coverage=coverage,
            n=n,
        )
    k = sum(1 for o in outcomes if o)
    band = wilson_interval(k, n, cfg.ci_mass)
    how_sure = HIGH if (band.width <= cfg.perf_high_max_width and n >= cfg.perf_high_min_n) \
        else MEDIUM if band.width <= 2 * cfg.perf_high_max_width else LOW
    reasons = [
        f"{k}/{n} application items correct ({band.point:.0%})",
        f"range width {band.width:.0%}",
    ]
    return ScoreResult(
        kind="performance",
        abstained=False,
        how_sure=how_sure,
        reasons=reasons,
        band=band.rounded(),
        coverage=coverage,
        n=n,
    )


# --------------------------------------------------------------------------- #
# readiness  (per-section projection on the 118..132 scale, gated + ranged)
# --------------------------------------------------------------------------- #
def map_ability_to_scale(ability: float, cfg: ScoringConfig) -> float:
    """Documented, anchored, monotonic transform ability(0..1) -> 118..132 (D-SCORE1)."""
    span_a = cfg.map_high_ability - cfg.map_low_ability
    span_s = cfg.map_high_scale - cfg.map_low_scale
    scaled = cfg.map_low_scale + (ability - cfg.map_low_ability) / span_a * span_s
    return clamp(scaled, cfg.section_scale_min, cfg.section_scale_max)


def give_up(n_reviews: int, coverage: float, cfg: ScoringConfig) -> tuple[bool, list[str]]:
    """Return (should_abstain, reasons). Readiness only (D10)."""
    reasons: list[str] = []
    if n_reviews < cfg.giveup_min_reviews:
        reasons.append(
            f"only {n_reviews} graded reviews (need >= {cfg.giveup_min_reviews})"
        )
    if coverage < cfg.giveup_min_coverage:
        reasons.append(
            f"weighted coverage {coverage:.0%} (need >= {cfg.giveup_min_coverage:.0%})"
        )
    return (bool(reasons), reasons)


def _beta_draw(k: int, n: int, rng: random.Random, a0: float = 1.0, b0: float = 1.0) -> float:
    """Draw from Beta(k+a0, n-k+b0), the posterior accuracy under a Beta(a0,b0)
    prior. a0=b0=1 is the uniform prior; a memory-derived prior passes a0/b0 so
    section recall regularizes the application estimate when reasoning data is thin."""
    a = k + a0
    b = n - k + b0
    x = rng.gammavariate(a, 1.0)
    y = rng.gammavariate(b, 1.0)
    return x / (x + y)


def readiness(
    section_outcomes: dict[str, Sequence[int]],
    coverage: float,
    coverage_by_section: dict[str, float],
    n_reviews: int,
    cfg: ScoringConfig,
    section_memory: Optional[dict[str, float]] = None,
) -> ScoreResult:
    """Project the three science sections + a labeled partial composite, with a range.

    Abstains (give-up rule) unless reviews, coverage, AND enough real reasoning
    items clear the gate; without that last piece readiness would just mirror the
    memory score. Ability per section combines reasoning and memory: observed
    application accuracy is the evidence, and section recall (`section_memory`,
    from the flashcards) is a weak prior that regularizes it while reasoning data
    is thin, then is overridden as that data grows. A section only joins the
    composite once it has `min_outcomes_readiness` application outcomes of its own.
    Range via Monte-Carlo over the per-section Beta posteriors (D-SCORE2). Never a
    4-section 472..528 total — CARS is not modeled (D2/D-SCORE3).
    """
    abstain, reasons = give_up(n_reviews, coverage, cfg)
    total_outcomes = sum(len(section_outcomes.get(s, [])) for s in SECTIONS)
    if total_outcomes < cfg.min_outcomes_performance:
        abstain = True
        reasons.append(
            f"only {total_outcomes} application items answered "
            f"(need >= {cfg.min_outcomes_performance})"
        )
    if abstain:
        return ScoreResult(
            kind="readiness",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=reasons,
            coverage=coverage,
            n=n_reviews,
        )

    rng = random.Random(cfg.seed)
    per_section_point: dict[str, float] = {}
    section_kn: dict[str, tuple[int, int]] = {}
    section_prior: dict[str, tuple[float, float]] = {}
    usable_sections: list[str] = []
    for s in SECTIONS:
        outs = list(section_outcomes.get(s, []))
        n = len(outs)
        if n < cfg.min_outcomes_readiness:
            continue
        k = sum(1 for o in outs if o)
        section_kn[s] = (k, n)
        if section_memory is not None and s in section_memory:
            m = clamp(section_memory[s], 0.0, 1.0)
            kappa = cfg.projection_prior_strength
            a0, b0 = m * kappa, (1.0 - m) * kappa
            ability = (k + a0) / (n + a0 + b0)  # memory-priored posterior mean
        else:
            a0, b0 = 1.0, 1.0
            ability = k / n  # observed accuracy (uniform prior)
        section_prior[s] = (a0, b0)
        per_section_point[s] = map_ability_to_scale(ability, cfg)
        usable_sections.append(s)

    if not usable_sections:
        return ScoreResult(
            kind="readiness",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=["no application-item outcomes in any section"],
            coverage=coverage,
            n=n_reviews,
        )

    # Monte-Carlo the partial composite (sum of usable-section scaled scores).
    composite_samples = []
    per_section_samples: dict[str, list[float]] = {s: [] for s in usable_sections}
    for _ in range(cfg.resample_iters):
        total = 0.0
        for s in usable_sections:
            k, n = section_kn[s]
            scaled = map_ability_to_scale(_beta_draw(k, n, rng, *section_prior[s]), cfg)
            per_section_samples[s].append(scaled)
            total += scaled
        composite_samples.append(total)
    composite_samples.sort()
    lo_q, hi_q = _ci_bounds(cfg.ci_mass)
    composite_point = sum(per_section_point[s] for s in usable_sections)
    band = Band(
        composite_point,
        _percentile(composite_samples, lo_q),
        _percentile(composite_samples, hi_q),
    ).rounded(1)

    sections_out = {}
    for s in usable_sections:
        ss = sorted(per_section_samples[s])
        sections_out[s] = Band(
            round(per_section_point[s], 1),
            round(_percentile(ss, lo_q), 1),
            round(_percentile(ss, hi_q), 1),
        )

    # how_sure: narrow composite band AND decent coverage, else lower.
    avg_section_width = (
        sum(sections_out[s].width for s in usable_sections) / len(usable_sections)
    )
    if avg_section_width <= cfg.ready_high_max_width and coverage >= cfg.ready_high_min_coverage:
        how_sure = HIGH
    elif avg_section_width <= 2 * cfg.ready_high_max_width:
        how_sure = MEDIUM
    else:
        how_sure = LOW

    reasons = [
        f"partial composite over {len(usable_sections)} of 3 science sections",
        f"weighted coverage {coverage:.0%}",
    ]
    weakest = min(usable_sections, key=lambda s: per_section_point[s])
    reasons.append(
        f"weakest modeled section: {SECTION_LABELS[weakest]} "
        f"({section_kn[weakest][0]}/{section_kn[weakest][1]} items)"
    )

    return ScoreResult(
        kind="readiness",
        abstained=False,
        how_sure=how_sure,
        reasons=reasons,
        band=band,
        coverage=coverage,
        n=n_reviews,
        extra={
            "sections": {s: sections_out[s].rounded(1) for s in usable_sections},
            "modeled_sections": usable_sections,
            "cars_modeled": False,
            "scale_note": "3-section partial of the 472-528 scale; CARS not modeled",
        },
    )


# --------------------------------------------------------------------------- #
# IRT latent-ability readiness  (2PL item-response model, EAP over a fixed grid)
# --------------------------------------------------------------------------- #
# Why IRT (and not just k/n or a Beta posterior mean)?
#   The classic readiness path maps a raw application-accuracy (k/n, optionally
#   memory-priored) through map_ability_to_scale. That treats every reasoning
#   item as equally hard and equally informative, so 15 easy items and 15 hard
#   items read the same. A 2-parameter-logistic (2PL) Item-Response model instead
#   places the student and every item on ONE shared latent-ability axis (theta):
#   each item has a difficulty b (where on the axis it separates who gets it
#   right) and a discrimination a (how sharply it does so). Ability is then
#   estimated from WHICH items were right, not merely how many -- clearing a hard
#   item moves theta more than clearing an easy one. This is the model real
#   standardized exams (including the MCAT's own scaling/equating) are built on;
#   it yields a principled posterior SD for the honest range, and its per-item
#   Fisher information gives a first-class abstain gate (too little information ->
#   no number) and drives adaptive next-item selection. Kept fully deterministic
#   (Expected A Posteriori over a FIXED quadrature grid, no PRNG) so the mobile
#   JS port reproduces theta bit-for-bit, per the desktop/mobile parity rule.


@dataclass
class IrtItem:
    """One answered application item under the 2PL model."""

    correct: int  # 1 right, 0 wrong
    b: float = 0.0  # difficulty on the latent axis (0 = average)
    a: float = 1.0  # discrimination (> 0; 1 = standard)


@dataclass
class IrtEstimate:
    """A section's latent-ability estimate: point, spread, and test information."""

    theta: float  # EAP (posterior mean) latent ability
    theta_sd: float  # posterior SD (drives the honest range)
    information: float  # test information (sum of item Fisher info) at theta
    n: int


def irt_prob(theta: float, a: float, b: float) -> float:
    """2PL probability of a correct response: logistic in a * (theta - b)."""
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


def irt_information(theta: float, a: float, b: float) -> float:
    """Fisher information one 2PL item carries at `theta`: a^2 * p * (1 - p).
    Maximal where the item sits at the student's level (p = 0.5, i.e. b == theta),
    which is exactly what makes it the right quantity for adaptive item choice."""
    p = irt_prob(theta, a, b)
    return a * a * p * (1.0 - p)


def _normal_pdf(x: float, mu: float, sd: float) -> float:
    z = (x - mu) / sd
    return math.exp(-0.5 * z * z) / (sd * math.sqrt(2.0 * math.pi))


def _irt_grid(cfg: ScoringConfig) -> list[tuple[float, float]]:
    """The fixed (node, prior-weight) quadrature grid. Evenly spaced nodes over
    [irt_theta_min, irt_theta_max] with the normal-prior density as each weight.
    Deterministic and PRNG-free; the absolute normalization is irrelevant (it
    cancels in the EAP ratio), so the JS port rebuilds the identical grid."""
    n = cfg.irt_grid_points
    if n < 2:
        raise ValueError("irt_grid_points must be >= 2")
    lo, hi = cfg.irt_theta_min, cfg.irt_theta_max
    step = (hi - lo) / (n - 1)
    return [
        (lo + step * i, _normal_pdf(lo + step * i, cfg.irt_prior_mean, cfg.irt_prior_sd))
        for i in range(n)
    ]


def irt_estimate(items: Sequence[IrtItem], cfg: ScoringConfig) -> IrtEstimate:
    """EAP (Expected A Posteriori) estimate of latent ability from 2PL responses.

    posterior(theta) is proportional to
        prior(theta) * product_i P_i(theta)^u_i * (1 - P_i(theta))^(1 - u_i).
    Evaluated on the fixed grid: theta is the posterior mean, theta_sd its SD, and
    `information` is the 2PL test information at that theta. Done in log-space with
    a max-subtraction so a long item list can't underflow. Fully deterministic --
    no PRNG -- so desktop and mobile agree exactly."""
    grid = _irt_grid(cfg)
    log_post: list[float] = []
    for x, w in grid:
        ll = math.log(w) if w > 0.0 else -math.inf
        for it in items:
            p = clamp(irt_prob(x, it.a, it.b), 1e-12, 1.0 - 1e-12)
            ll += math.log(p) if it.correct else math.log(1.0 - p)
        log_post.append(ll)
    max_ll = max(log_post)
    weights = [math.exp(lp - max_ll) for lp in log_post]
    total = sum(weights)
    if total <= 0.0:
        # degenerate; fall back to the prior (should not happen with a real prior)
        return IrtEstimate(cfg.irt_prior_mean, cfg.irt_prior_sd, 0.0, len(items))
    theta = sum(grid[i][0] * weights[i] for i in range(len(grid))) / total
    var = sum(weights[i] * (grid[i][0] - theta) ** 2 for i in range(len(grid))) / total
    sd = math.sqrt(max(0.0, var))
    info = sum(irt_information(theta, it.a, it.b) for it in items)
    return IrtEstimate(theta, sd, info, len(items))


def theta_to_scale(theta: float, cfg: ScoringConfig) -> float:
    """Documented monotonic transform: latent ability theta -> 118..132 section
    scale as midpoint + per_theta * theta, clamped to the section band. Strictly
    increasing, and centered so theta = 0 (population-average ability) lands on
    the scale midpoint. Monotone, so it maps a theta interval to a scale interval
    order-preservingly (the posterior SD becomes an honest scale range)."""
    scaled = cfg.irt_scale_midpoint + cfg.irt_scale_per_theta * theta
    return clamp(scaled, cfg.section_scale_min, cfg.section_scale_max)


def irt_next_item(
    pool: Sequence[IrtItem], theta: float, cfg: ScoringConfig
) -> Optional[int]:
    """Adaptive next-item selection: the index of the pool item carrying the most
    Fisher information at the student's current ability `theta` (the practice
    layer will consume this to serve the most diagnostic question next). Returns
    None for an empty pool. Deterministic: ties resolve to the lowest index."""
    best_idx: Optional[int] = None
    best_info = -1.0
    for i, it in enumerate(pool):
        info = irt_information(theta, it.a, it.b)
        if info > best_info:
            best_info = info
            best_idx = i
    return best_idx


def irt_readiness(
    section_items: dict[str, Sequence[IrtItem]],
    coverage: float,
    coverage_by_section: dict[str, float],
    n_reviews: int,
    cfg: ScoringConfig,
) -> ScoreResult:
    """Readiness via 2PL IRT latent ability: per science section + a labeled
    3-section partial composite, each with an honest range.

    Honesty gates, all preserved from the classic path plus one IRT-native gate:
      * the give-up rule (reviews AND coverage, D10);
      * a minimum TOTAL of application items (min_outcomes_performance);
      * per section, a minimum count of application items
        (`min_outcomes_readiness`), the same gate as the classic path. A section
        the student aces carries little Fisher information, so IRT cannot pin its
        exact score; that surfaces as a wide honest range (large posterior SD),
        not as an excluded section. If no section clears the count gate, readiness
        abstains.

    Section score = theta_to_scale(EAP theta); the range is
    theta_to_scale(theta +/- z * posterior_sd) (monotone map, so a thinner
    posterior gives a tighter band). The composite point is the sum of usable
    section points; its range combines the (independent) section bands by error
    propagation, kept inside the partial band. Always a 3-section partial of the
    472..528 scale -- CARS is never modeled (D2). No PRNG (EAP on a fixed grid),
    so desktop and mobile agree bit-for-bit.
    """
    abstain, reasons = give_up(n_reviews, coverage, cfg)
    total_items = sum(len(section_items.get(s, [])) for s in SECTIONS)
    if total_items < cfg.min_outcomes_performance:
        abstain = True
        reasons.append(
            f"only {total_items} application items answered "
            f"(need >= {cfg.min_outcomes_performance})"
        )
    if abstain:
        return ScoreResult(
            kind="readiness",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=reasons,
            coverage=coverage,
            n=n_reviews,
        )

    z = _inv_norm_cdf(1.0 - (1.0 - cfg.ci_mass) / 2.0)
    sections_out: dict[str, Band] = {}
    per_section_est: dict[str, IrtEstimate] = {}
    usable: list[str] = []
    for s in SECTIONS:
        items = list(section_items.get(s, []))
        # Include a section once it has enough answered items (the same count gate
        # as the classic path). A section the student aces carries little Fisher
        # information, so IRT cannot pin the exact score -- that surfaces as a WIDE
        # honest range (a large posterior SD), not as dropping the section. The
        # whole readiness still abstains below if no section clears this gate.
        if len(items) < cfg.min_outcomes_readiness:
            continue
        est = irt_estimate(items, cfg)
        sections_out[s] = Band(
            round(theta_to_scale(est.theta, cfg), 1),
            round(theta_to_scale(est.theta - z * est.theta_sd, cfg), 1),
            round(theta_to_scale(est.theta + z * est.theta_sd, cfg), 1),
        )
        per_section_est[s] = est
        usable.append(s)

    if not usable:
        return ScoreResult(
            kind="readiness",
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=[
                f"no science section has >= {cfg.min_outcomes_readiness} "
                "application items yet"
            ],
            coverage=coverage,
            n=n_reviews,
        )

    # Composite: sum of section points (always inside the partial band, since each
    # section point is clamped to 118..132). Its range propagates the independent
    # section bands (sigma_s ~ band_width / 2z), narrower than naively adding the
    # per-section bounds, then is clamped to the partial band.
    comp_lo_bound = len(usable) * cfg.section_scale_min
    comp_hi_bound = len(usable) * cfg.section_scale_max
    composite_point = sum(sections_out[s].point for s in usable)
    comp_sigma = math.sqrt(
        sum(((sections_out[s].high - sections_out[s].low) / (2.0 * z)) ** 2 for s in usable)
    )
    band = Band(
        round(composite_point, 1),
        round(clamp(composite_point - z * comp_sigma, comp_lo_bound, comp_hi_bound), 1),
        round(clamp(composite_point + z * comp_sigma, comp_lo_bound, comp_hi_bound), 1),
    )

    avg_width = sum(sections_out[s].width for s in usable) / len(usable)
    if avg_width <= cfg.ready_high_max_width and coverage >= cfg.ready_high_min_coverage:
        how_sure = HIGH
    elif avg_width <= 2 * cfg.ready_high_max_width:
        how_sure = MEDIUM
    else:
        how_sure = LOW

    reasons = [
        f"IRT latent-ability estimate over {len(usable)} of 3 science sections",
        f"weighted coverage {coverage:.0%}",
    ]
    weakest = min(usable, key=lambda s: sections_out[s].point)
    reasons.append(
        f"weakest modeled section: {SECTION_LABELS[weakest]} "
        f"({per_section_est[weakest].n} items)"
    )

    return ScoreResult(
        kind="readiness",
        abstained=False,
        how_sure=how_sure,
        reasons=reasons,
        band=band,
        coverage=coverage,
        n=n_reviews,
        extra={
            "sections": {s: sections_out[s] for s in usable},
            "modeled_sections": usable,
            "cars_modeled": False,
            "scale_note": "3-section partial of the 472-528 scale; CARS not modeled",
            "model": "irt_2pl_eap",
            # per-section latent estimates, so an adaptive practice layer can call
            # irt_next_item against the student's current theta.
            "irt": {
                s: {
                    "theta": round(per_section_est[s].theta, 4),
                    "theta_sd": round(per_section_est[s].theta_sd, 4),
                    "information": round(per_section_est[s].information, 4),
                    "n": per_section_est[s].n,
                }
                for s in usable
            },
        },
    )


# --------------------------------------------------------------------------- #
# paraphrase test  (transfer gap: memory vs application on the same section)
# --------------------------------------------------------------------------- #
@dataclass
class SectionTransfer:
    """One section's memory-to-application comparison (the paraphrase test)."""

    section: str
    recall: float  # mean FSRS retrievability on studied cards (0..1)
    application: float  # accuracy on novel application items (0..1)
    gap: float  # recall - application; positive means memory outruns application
    n_app: int
    fluency_risk: bool  # gap wide enough to flag the fluency illusion


def transfer_gap(
    section_recall: dict[str, float],
    section_app: dict[str, Sequence[int]],
    cfg: ScoringConfig,
) -> dict[str, SectionTransfer]:
    """Per-section paraphrase test.

    Compares recall (memory: mean retrievability) against accuracy on novel
    application items in the same section. A large positive gap is the fluency
    illusion: the student recalls the fact but cannot yet use it. Grounded in
    transfer-appropriate processing (Morris, Bransford & Franks 1977) and the
    fluency-illusion work (Bjork, Dunlosky & Kornell 2013; Kornell & Bjork 2008).

    Only reported for a section that has both a memory signal and at least
    `min_outcomes_transfer` application outcomes, so it never guesses.
    """
    out: dict[str, SectionTransfer] = {}
    for s in SECTIONS:
        recall = section_recall.get(s)
        outs = list(section_app.get(s, []))
        if recall is None or len(outs) < cfg.min_outcomes_transfer:
            continue
        application = sum(1 for o in outs if o) / len(outs)
        gap = recall - application
        out[s] = SectionTransfer(
            section=s,
            recall=round(clamp(recall, 0.0, 1.0), 3),
            application=round(application, 3),
            gap=round(gap, 3),
            n_app=len(outs),
            fluency_risk=gap >= cfg.fluency_gap_threshold,
        )
    return out


@dataclass
class ConceptTransfer:
    """One concept's memory-to-application comparison (card-level paraphrase test)."""

    concept_id: str
    section: str
    recall: float  # mean FSRS retrievability over the concept's recall cards
    application: float  # accuracy on the concept's reworded application variants
    gap: float  # recall - application; positive means memory outruns application
    n_app: int
    fluency_risk: bool  # gap wide enough to flag the fluency illusion


def concept_transfer_gaps(
    concept_recall: dict[str, float],
    concept_app: dict[str, Sequence[int]],
    concept_section: dict[str, str],
    cfg: ScoringConfig,
) -> list[ConceptTransfer]:
    """Card-level paraphrase test, per CONCEPT.

    A concept links a recall card to its reworded application variants (the
    LinkedCardNIDs mechanism lives in collect.py: a shared concept tag). For each
    linked concept this compares recall (memory: mean retrievability) against
    accuracy on its application variants and surfaces the biggest "fluency
    illusion" gaps first -- concepts recalled well but not yet applied (Bjork,
    Dunlosky & Kornell 2013; Kornell & Bjork 2008). Finer-grained than the
    section-level transfer_gap, so one weak concept is not hidden inside a healthy
    section average.

    Reported only for a concept with BOTH a memory signal and at least
    `min_outcomes_transfer_card` application outcomes, so it never guesses. Sorted
    by gap descending (worst fluency illusion first)."""
    out: list[ConceptTransfer] = []
    for cid, recall in concept_recall.items():
        outs = list(concept_app.get(cid, []))
        if len(outs) < cfg.min_outcomes_transfer_card:
            continue
        application = sum(1 for o in outs if o) / len(outs)
        r = clamp(recall, 0.0, 1.0)
        gap = r - application
        out.append(
            ConceptTransfer(
                concept_id=cid,
                section=concept_section.get(cid, ""),
                recall=round(r, 3),
                application=round(application, 3),
                gap=round(gap, 3),
                n_app=len(outs),
                fluency_risk=gap >= cfg.fluency_gap_threshold,
            )
        )
    # worst fluency illusion first, then a stable tiebreak by concept id
    out.sort(key=lambda t: (-t.gap, t.concept_id))
    return out


# --------------------------------------------------------------------------- #
# calibration  (are the predicted probabilities honest? predicted vs observed)
# --------------------------------------------------------------------------- #
@dataclass
class CalibrationBin:
    """One reliability bin: how often items we predicted ~`pred_mean` came true."""

    lo: float  # bin's predicted-probability lower edge
    hi: float  # bin's predicted-probability upper edge
    n: int
    pred_mean: float  # mean predicted probability of items in this bin
    obs_rate: float  # observed fraction correct in this bin


@dataclass
class Calibration:
    abstained: bool
    how_sure: str
    reasons: list[str] = field(default_factory=list)
    n: int = 0
    brier: Optional[float] = None
    mean_predicted: Optional[float] = None
    mean_observed: Optional[float] = None
    well_calibrated: Optional[bool] = None
    bins: list[CalibrationBin] = field(default_factory=list)


def calibration(
    pairs: Sequence[tuple[float, int]], cfg: ScoringConfig, n_bins: int = 5
) -> Calibration:
    """Reliability of the model's probability predictions.

    `pairs`: (predicted P(correct) in [0,1], actual outcome 0/1) for each scored
    application item. Buckets predictions into `n_bins` equal-width bins over
    [0,1] and reports, per bin, the mean prediction vs the observed fraction
    correct. A well-calibrated model tracks the diagonal (predicted ~ observed).
    Reports the Brier score (mean squared error of the probabilities) and the
    overall predicted-vs-observed gap. Abstains until enough scored items exist,
    so it never draws a curve from noise.
    """
    scored = [(clamp(float(p), 0.0, 1.0), 1 if o else 0) for p, o in pairs]
    n = len(scored)
    if n < cfg.min_outcomes_calibration:
        return Calibration(
            abstained=True,
            how_sure=INSUFFICIENT,
            reasons=[
                f"only {n} scored predictions "
                f"(need >= {cfg.min_outcomes_calibration})"
            ],
            n=n,
        )

    bins: list[CalibrationBin] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        # last bin is closed on the right so predicted==1.0 lands somewhere
        members = [
            (p, o)
            for p, o in scored
            if (p >= lo and p < hi) or (i == n_bins - 1 and p == 1.0)
        ]
        if not members:
            continue
        bn = len(members)
        bins.append(
            CalibrationBin(
                lo=round(lo, 3),
                hi=round(hi, 3),
                n=bn,
                pred_mean=round(sum(p for p, _ in members) / bn, 3),
                obs_rate=round(sum(o for _, o in members) / bn, 3),
            )
        )

    b = brier(scored)
    mean_pred = sum(p for p, _ in scored) / n
    mean_obs = sum(o for _, o in scored) / n
    gap = abs(mean_pred - mean_obs)
    well = gap <= cfg.calibration_well_within
    # confidence in the calibration read itself scales with how many items we have
    how_sure = HIGH if n >= 60 else MEDIUM if n >= 2 * cfg.min_outcomes_calibration else LOW
    reasons = [
        f"predicted {mean_pred:.0%} correct, observed {mean_obs:.0%} over {n} items",
        f"Brier score {b:.3f} (0 is perfect)",
        "within tolerance" if well else "predictions run ahead of results",
    ]
    return Calibration(
        abstained=False,
        how_sure=how_sure,
        reasons=reasons,
        n=n,
        brier=round(b, 4),
        mean_predicted=round(mean_pred, 3),
        mean_observed=round(mean_obs, 3),
        well_calibrated=well,
        bins=bins,
    )


# --------------------------------------------------------------------------- #
# study pace  (days until the exam + a transparent daily target)
# --------------------------------------------------------------------------- #
@dataclass
class StudyPace:
    has_exam_date: bool
    exam_date: Optional[str] = None
    days_left: Optional[int] = None
    passed: bool = False
    reviews_due: int = 0
    flashcards_per_day: int = 0
    new_remaining: int = 0
    new_per_day: int = 0
    reasoning_target: int = 0
    reasoning_done: int = 0
    reasoning_remaining: int = 0
    reasoning_per_day: int = 0
    message: str = ""


def study_pace(
    exam_date: Optional[str],
    today: str,
    reviews_due: int,
    new_remaining: int,
    reasoning_done: int,
    cfg: ScoringConfig,
    concepts_to_practice: int = 0,
    cards_studied: int = 0,
) -> StudyPace:
    """Days until the exam and a transparent daily target to get there.

    The plan is a stated heuristic, not a promise: keep up the reviews FSRS makes
    due, introduce the remaining new cards evenly, and reach
    `pace_reasoning_target` scored practice items by exam day. Dates are ISO
    ``YYYY-MM-DD``. Abstains when no date is set; flags a date in the past.
    """
    target = cfg.pace_reasoning_target
    remaining = max(0, target - reasoning_done)
    base = dict(
        reviews_due=reviews_due,
        new_remaining=new_remaining,
        reasoning_target=target,
        reasoning_done=reasoning_done,
        reasoning_remaining=remaining,
    )
    if not exam_date:
        return StudyPace(
            has_exam_date=False,
            message="Set your exam date to get a daily study target.",
            **base,
        )
    try:
        days_left = (date.fromisoformat(exam_date) - date.fromisoformat(today)).days
    except ValueError:
        return StudyPace(
            has_exam_date=False, message="Could not read the exam date.", **base
        )
    if days_left < 0:
        return StudyPace(
            has_exam_date=True,
            exam_date=exam_date,
            days_left=days_left,
            passed=True,
            message="Your exam date has passed. Set a new one to get a plan.",
            **base,
        )
    div = max(1, days_left)  # exam today/tomorrow -> a finite, aggressive number
    # Daily reasoning goal derives from real exam breadth: the AAMC concepts you
    # still need to get exam-ready, times a per-concept budget, spread over the
    # days left. Shrinks as you master topics; never below a few a day with time.
    reasoning_prep = concepts_to_practice * cfg.pace_reasoning_per_concept
    reasoning_per_day = max(cfg.pace_reasoning_floor, math.ceil(reasoning_prep / div))
    # Flashcards: today's FSRS-due count is the honest baseline (spaced repetition
    # sets it by memory, not the calendar). As the exam nears, ramp up so you get
    # through your remaining new cards and a full pass of your deck by exam day;
    # never below what's actually due.
    flashcards_per_day = max(reviews_due, math.ceil((new_remaining + cards_studied) / div))
    return StudyPace(
        has_exam_date=True,
        exam_date=exam_date,
        days_left=days_left,
        flashcards_per_day=flashcards_per_day,
        new_per_day=math.ceil(new_remaining / div),
        reasoning_per_day=reasoning_per_day,
        **base,
    )


# --------------------------------------------------------------------------- #
# confidence calibration  (metacognition: how sure vs how right, per item)
# --------------------------------------------------------------------------- #
CONFIDENCE_LEVELS: tuple[str, ...] = ("guess", "unsure", "sure")


@dataclass
class ConfidenceLevel:
    level: str
    n: int
    correct: int
    rate: float  # accuracy at this confidence level


@dataclass
class ConfidenceCalibration:
    abstained: bool
    n: int
    levels: list[ConfidenceLevel] = field(default_factory=list)
    insight: str = ""


def confidence_calibration(
    items: Sequence[tuple[str, int]], cfg: ScoringConfig
) -> ConfidenceCalibration:
    """Compare how sure the student felt against how often they were right.

    `items`: (confidence in {guess, unsure, sure}, outcome 0/1) per scored
    question. Surfaces over/under-confidence, the metacognition almost no MCAT
    tool measures. Abstains until enough labeled items exist.
    """
    labeled = [(c, 1 if o else 0) for c, o in items if c in CONFIDENCE_LEVELS]
    n = len(labeled)
    if n < cfg.min_confidence_items:
        return ConfidenceCalibration(abstained=True, n=n)
    by: dict[str, list[int]] = {lvl: [] for lvl in CONFIDENCE_LEVELS}
    for c, o in labeled:
        by[c].append(o)
    levels = [
        ConfidenceLevel(lvl, len(outs), sum(outs), round(sum(outs) / len(outs), 3))
        for lvl in CONFIDENCE_LEVELS
        if (outs := by[lvl])
    ]
    sure, guess = by["sure"], by["guess"]
    insight = "Your confidence lines up with your results."
    if len(sure) >= 3 and sum(sure) / len(sure) < cfg.overconfident_sure_max:
        insight = (
            f"When you felt sure you were right {sum(sure) / len(sure):.0%}. "
            "Slow down on the ones you are sure about."
        )
    elif len(guess) >= 3 and sum(guess) / len(guess) > cfg.underconfident_guess_min:
        insight = (
            f"You got {sum(guess) / len(guess):.0%} of your guesses right. "
            "Trust your reasoning more, and move faster."
        )
    return ConfidenceCalibration(abstained=False, n=n, levels=levels, insight=insight)


# --------------------------------------------------------------------------- #
# mistake taxonomy  (how you lose points, not just where)
# --------------------------------------------------------------------------- #
MISS_REASONS: tuple[str, ...] = ("content", "misread", "trap", "time", "math")
MISS_LABELS: dict[str, str] = {
    "content": "Content gap",
    "misread": "Misread the question",
    "trap": "Fell for a trap answer",
    "time": "Ran out of time",
    "math": "Arithmetic slip",
}


@dataclass
class MistakeTaxonomy:
    abstained: bool
    n_wrong: int
    by_reason: dict[str, int] = field(default_factory=dict)
    top_reason: Optional[str] = None
    top_section: Optional[str] = None  # section where the top reason bites most


def mistake_taxonomy(
    wrong_items: Sequence[tuple[str, str]], cfg: ScoringConfig
) -> MistakeTaxonomy:
    """Aggregate why misses happen. `wrong_items`: (section, reason) for each
    missed question, reason in MISS_REASONS. Turns the score into a diagnosis:
    which failure mode costs the most points, and where. Abstains until enough."""
    labeled = [(s, r) for s, r in wrong_items if r in MISS_REASONS]
    n = len(labeled)
    if n < cfg.min_mistakes:
        return MistakeTaxonomy(abstained=True, n_wrong=n)
    by_reason: dict[str, int] = {}
    for _s, r in labeled:
        by_reason[r] = by_reason.get(r, 0) + 1
    top_reason = max(by_reason, key=by_reason.get)
    sec_counts: dict[str, int] = {}
    for s, r in labeled:
        if r == top_reason:
            sec_counts[s] = sec_counts.get(s, 0) + 1
    top_section = max(sec_counts, key=sec_counts.get) if sec_counts else None
    return MistakeTaxonomy(
        abstained=False,
        n_wrong=n,
        by_reason=by_reason,
        top_reason=top_reason,
        top_section=top_section,
    )


# --------------------------------------------------------------------------- #
# pacing coach  (your time per question vs the real MCAT section budget)
# --------------------------------------------------------------------------- #
# Public AAMC section format: (questions, minutes).
SECTION_TIMING: dict[str, tuple[int, int]] = {
    "chem_phys": (59, 95),
    "bio_biochem": (59, 95),
    "psych_soc": (59, 95),
    "cars": (53, 90),
}


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class SectionPace:
    section: str
    n: int
    median_sec: float  # your typical seconds per question
    target_sec: float  # the section's per-question budget
    on_pace: bool
    projected_left: int  # questions you would not reach at this pace (0 if you finish)
    spare_min: float  # minutes to spare if you finish (0 if you run out)


@dataclass
class Pacing:
    abstained: bool
    n: int
    sections: list[SectionPace] = field(default_factory=list)
    overall_on_pace: Optional[bool] = None


def pacing_coach(items: Sequence[tuple[str, float]], cfg: ScoringConfig) -> Pacing:
    """Coach pace-to-finish. `items`: (section, milliseconds) per timed question.
    Uses the median (robust to the first, passage-reading question) and projects
    against the real section time budget. Abstains until enough timed items."""
    timed = [(s, ms) for s, ms in items if ms and ms > 0]
    n = len(timed)
    if n < cfg.min_pace_total:
        return Pacing(abstained=True, n=n)
    by: dict[str, list[float]] = {}
    for s, ms in timed:
        by.setdefault(s, []).append(ms / 1000.0)
    sections: list[SectionPace] = []
    for s, vals in by.items():
        if len(vals) < cfg.min_pace_per_section or s not in SECTION_TIMING:
            continue
        med = _median(vals)
        q, mins = SECTION_TIMING[s]
        limit = mins * 60.0
        target = limit / q
        if med <= target:
            sections.append(
                SectionPace(s, len(vals), round(med, 1), round(target, 1), True, 0, round((limit - med * q) / 60.0, 1))
            )
        else:
            completed = int(limit // med)
            sections.append(
                SectionPace(s, len(vals), round(med, 1), round(target, 1), False, max(0, q - completed), 0.0)
            )
    if not sections:
        return Pacing(abstained=True, n=n)
    return Pacing(abstained=False, n=n, sections=sections, overall_on_pace=all(sp.on_pace for sp in sections))


# --------------------------------------------------------------------------- #
# score trajectory  (project readiness to exam day at your current rate)
# --------------------------------------------------------------------------- #
@dataclass
class Trajectory:
    abstained: bool
    projected: Optional[float] = None
    target: Optional[int] = None
    on_pace: Optional[bool] = None
    per_week: Optional[float] = None  # points gained per week (the slope)
    weakest_section: Optional[str] = None
    reason: str = ""


def trajectory(
    history: Sequence[dict],
    target: Optional[int],
    days_to_exam: Optional[int],
    weakest_section: Optional[str],
    cfg: ScoringConfig,
) -> Trajectory:
    """Project the readiness composite to exam day from dated snapshots.

    `history`: [{"d": "YYYY-MM-DD", "point": float}]. Fits a least-squares slope
    over the real snapshots and extrapolates to the exam date, honestly
    abstaining until there are at least a couple of days of data and a target +
    exam date are set. Never invents a trend from a single point.
    """
    if not target or days_to_exam is None:
        return Trajectory(abstained=True, target=target, reason="set a target score and an exam date")
    days = sorted({h["d"] for h in history})
    if len(days) < cfg.min_trajectory_days:
        return Trajectory(
            abstained=True, target=target, reason="your trajectory appears after a few days of study"
        )
    pts = [(date.fromisoformat(h["d"]).toordinal(), float(h["point"])) for h in history]
    m = len(pts)
    sx = sum(x for x, _ in pts)
    sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts)
    sxy = sum(x * y for x, y in pts)
    denom = m * sxx - sx * sx
    slope = (m * sxy - sx * sy) / denom if denom else 0.0
    # Anchor the projection on the most recent snapshot BY DATE, not the last
    # entry in input order, so an out-of-order history still projects from the
    # latest real point.
    base_point = max(pts, key=lambda p: p[0])[1]
    # Clamp the linear extrapolation to the readiness scale (a score can't run
    # past the three-section maximum), so a steep recent slope can't project an
    # impossible number. Valid because readiness only records full 3-section
    # composites (collect.gather), so the base always sits on the 354..396 band.
    lo = 3 * cfg.section_scale_min
    hi = 3 * cfg.section_scale_max
    projected = min(hi, max(lo, base_point + slope * days_to_exam))
    return Trajectory(
        abstained=False,
        projected=round(projected, 1),
        target=target,
        on_pace=projected >= target,
        per_week=round(slope * 7, 2),
        weakest_section=weakest_section,
        reason="",
    )
