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
    rng = random.Random(cfg.seed)
    band = bootstrap_mean_ci([clamp(r, 0.0, 1.0) for r in r_values], cfg, rng)
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


def _beta_draw(k: int, n: int, rng: random.Random) -> float:
    """Draw from Beta(k+1, n-k+1) — the posterior mean-accuracy with a uniform prior."""
    a = k + 1.0
    b = n - k + 1.0
    x = rng.gammavariate(a, 1.0)
    y = rng.gammavariate(b, 1.0)
    return x / (x + y)


def readiness(
    section_outcomes: dict[str, Sequence[int]],
    coverage: float,
    coverage_by_section: dict[str, float],
    n_reviews: int,
    cfg: ScoringConfig,
) -> ScoreResult:
    """Project the three science sections + a labeled partial composite, with a range.

    Abstains (give-up rule) unless reviews and coverage clear the gate. Ability per
    section = observed application-item accuracy (interim performance model); range via
    Monte-Carlo over per-section Beta posteriors (D-SCORE2). Never a 4-section 472..528
    total — CARS is not modeled (D2/D-SCORE3).
    """
    abstain, reasons = give_up(n_reviews, coverage, cfg)
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
    usable_sections: list[str] = []
    for s in SECTIONS:
        outs = list(section_outcomes.get(s, []))
        n = len(outs)
        if n == 0:
            continue
        k = sum(1 for o in outs if o)
        section_kn[s] = (k, n)
        per_section_point[s] = map_ability_to_scale(k / n, cfg)
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
            scaled = map_ability_to_scale(_beta_draw(k, n, rng), cfg)
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
