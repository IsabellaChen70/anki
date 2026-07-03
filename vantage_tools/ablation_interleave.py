#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage interleaving ablation (Sec 8): three arms at EQUAL study time.

FEATURE UNDER TEST
    Confusable-topic interleaving review order (the Rust change in
    rslib/src/scheduler/queue/builder/interleave.rs).

THREE ARMS (same items, equal study time = one full pass, equal reps per topic)
    1. mixed   = interleaving ON  (the feature: InterleaveMode::Mixed)
    2. blocked = interleaving grouped/OFF worst case (InterleaveMode::Blocked)
    3. off     = plain stock Anki order (InterleaveMode::Off) -- the unmodified
                 upstream ordering produced by the same shared engine with the
                 feature disabled (equivalent to plain Anki's queue order).

PRE-REGISTERED (written before looking at any result)
    ONE main metric: accuracy on NEW mixed-topic application questions at equal
    study time.
    Hypothesis: interleaving confusable topics raises that accuracy vs blocked
    (and vs off), because it raises how often confusable partners are studied
    back-to-back, which is the discrimination mechanism (Brunmair & Richter 2019,
    meta-analysis mean g ~ 0.42 for interleaving confusable categories).

    Because there is NO real learner cohort, the outcome is a SEEDED simulation
    with a documented model, and it is reported HONESTLY, including a NULL CONTROL:
      - Memory is held EQUAL across arms (one full pass -> equal reps/topic), so the
        ONLY thing that varies with queue order is DISCRIMINATION exposure
        (interleave_exposure = fraction of adjacent study transitions that are
        between two confusable partners), which we MEASURE from the real engine's
        queue order.
      - Test accuracy on a new mixed-topic question =
            MEMORY * clamp(BASE + EFFECT * (interleave_exposure - CHANCE), 0, 1)
      - EFFECT = 0.0  -> NULL CONTROL: order alone changes nothing; arms tie.
        "No difference" is a valid, honestly-reported result.
      - EFFECT = 0.42 -> the literature discrimination effect. This arm's numbers
        are MODEL-DEPENDENT (they assume the published effect size); a real cohort
        is required to confirm the size (Step 4). We do not claim it as measured.

    Part A (MECHANISM, fully real, no assumptions): same-topic adjacency of the
    real queue per arm, across seeds, with a range. This is what the engine
    actually does; the outcome model in Part B only reweights it.

REPRODUCIBLE
    Fixed content; seeds SEEDS; no randomness beyond the seeded shuffle. Re-run:
        out/pyenv/bin/python vantage_tools/ablation_interleave.py
    Writes vantage_tools/ablation_results.json.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import tempfile

from anki.collection import Collection

# Two confusable topic pairs (interleaving helps most for confusable categories).
TOPICS = ["bio_glycolysis", "bio_gluconeogenesis", "psy_classical", "psy_operant"]
CONFUSABLE = [
    ("bio_glycolysis", "bio_gluconeogenesis"),
    ("psy_classical", "psy_operant"),
]
PER_TOPIC = 8
SEEDS = [7, 13, 21, 42, 101]

# Pre-registered outcome-model constants (see docstring).
MEMORY = 0.85
BASE = 0.60
CHANCE = 0.25
EFFECTS = {"null_control": 0.0, "literature_g0.42": 0.42}

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "ablation_results.json")

_PARTNER = {}
for _a, _b in CONFUSABLE:
    _PARTNER[_a] = _b
    _PARTNER[_b] = _a


def same_topic_adjacency(topics: list[str]) -> float:
    if len(topics) < 2:
        return 0.0
    same = sum(1 for a, b in zip(topics, topics[1:]) if a == b)
    return same / (len(topics) - 1)


def interleave_exposure(topics: list[str]) -> float:
    """Fraction of adjacent transitions that are between two confusable partners.
    Measured from the real queue order; drives the discrimination term."""
    trans = list(zip(topics, topics[1:]))
    if not trans:
        return 0.0
    inter = sum(1 for a, b in trans if _PARTNER.get(a) == b)
    return inter / len(trans)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def build_due_collection(path: str, seed: int) -> Collection:
    col = Collection(path)
    basic = col.models.by_name("Basic")
    did = col.decks.id("Ablation")
    col.decks.select(did)
    pairs = [(t, i) for t in TOPICS for i in range(PER_TOPIC)]
    random.Random(seed).shuffle(pairs)  # realistic, not pre-sorted by topic
    for t, i in pairs:
        note = col.new_note(basic)
        note["Front"] = f"{t} card {i}"
        note["Back"] = "x"
        note.tags = [f"mcat::sci::{t}"]
        col.add_note(note, did)
    col.db.execute("update cards set queue=2, type=2, due=?, ivl=10", col.sched.today)
    return col


def queue_topics(col: Collection) -> list[str]:
    q = col._backend.get_queued_cards(fetch_limit=1000, intraday_learning_only=False)
    out = []
    for qc in q.cards:
        tags = col.get_card(qc.card.id).note().tags
        topic = next(
            (t.split("::")[-1] for t in tags if t.startswith("mcat::")), "untagged"
        )
        out.append(topic)
    return out


CONFUSABILITY_WEIGHT = 5.0


def measure_arms(seed: int) -> dict:
    path = os.path.join(tempfile.mkdtemp(), "ablation.anki2")
    col = build_due_collection(path, seed)
    # Seed the confusability matrix (full note tags) so the WEIGHTED Mixed
    # interleaver alternates confusable partners. Off/Blocked ignore weights, so
    # this only changes the Mixed arm (rslib interleave.rs). set_interleave_mode
    # preserves this map when it flips the mode.
    col.set_config(
        "vantage.interleave",
        {
            "topic_tag_prefix": "mcat",
            "seed": seed,
            "confusability": [
                {
                    "topic_a": f"mcat::sci::{a}",
                    "topic_b": f"mcat::sci::{b}",
                    "weight": CONFUSABILITY_WEIGHT,
                }
                for a, b in CONFUSABLE
            ],
        },
    )
    arms = {}
    for name, mode in [("off", 0), ("mixed", 1), ("blocked", 2)]:
        col.sched.set_interleave_mode(mode=mode, topic_tag_prefix="mcat", seed=seed)
        order = queue_topics(col)
        arms[name] = {
            "same_topic_adjacency": same_topic_adjacency(order),
            "interleave_exposure": interleave_exposure(order),
        }
    col.close()
    return arms


def agg(values: list[float]) -> dict:
    return {
        "mean": round(statistics.mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def main() -> int:
    per_seed = {s: measure_arms(s) for s in SEEDS}
    arm_names = ["off", "mixed", "blocked"]

    # ---- Part A: mechanism (real) ----
    adjacency = {
        a: agg([per_seed[s][a]["same_topic_adjacency"] for s in SEEDS])
        for a in arm_names
    }
    exposure = {
        a: agg([per_seed[s][a]["interleave_exposure"] for s in SEEDS]) for a in arm_names
    }

    print("=" * 70)
    print("PART A - MECHANISM (real engine, %d seeds): same-topic adjacency" % len(SEEDS))
    print("=" * 70)
    print(f"content: {len(TOPICS)} confusable topics x {PER_TOPIC} cards, seeds={SEEDS}\n")
    print(f"  {'arm':<9}{'same-topic adj (mean [min,max])':<34}{'interleave exposure'}")
    for a in arm_names:
        adj, exp = adjacency[a], exposure[a]
        print(
            f"  {a:<9}{adj['mean']:.3f} [{adj['min']:.3f},{adj['max']:.3f}]"
            f"{'':<12}{exp['mean']:.3f} [{exp['min']:.3f},{exp['max']:.3f}]"
        )
    mech_ok = adjacency["mixed"]["mean"] < adjacency["off"]["mean"] < adjacency["blocked"]["mean"]
    print(
        f"\n  hypothesis mixed << off < blocked: "
        f"{'CONFIRMED' if mech_ok else 'NOT confirmed'} "
        f"(mixed={adjacency['mixed']['mean']:.3f} < off={adjacency['off']['mean']:.3f} "
        f"< blocked={adjacency['blocked']['mean']:.3f})"
    )

    # ---- Part B: outcome (simulated, equal study time, pre-registered) ----
    print("\n" + "=" * 70)
    print("PART B - OUTCOME: accuracy on NEW mixed-topic questions at EQUAL time")
    print("=" * 70)
    print(
        "  memory is EQUAL across arms (one full pass); only discrimination exposure\n"
        "  varies with order. EFFECT=0 is the null control; EFFECT=0.42 is the\n"
        "  literature effect (model-dependent, needs a real cohort to confirm).\n"
    )
    outcomes = {}
    for eff_name, eff in EFFECTS.items():
        outcomes[eff_name] = {}
        print(f"  --- EFFECT = {eff} ({eff_name}) ---")
        print(f"    {'arm':<9}{'test accuracy (mean [min,max])'}")
        per_arm_acc = {}
        for a in arm_names:
            accs = []
            for s in SEEDS:
                exp = per_seed[s][a]["interleave_exposure"]
                accs.append(MEMORY * clamp(BASE + eff * (exp - CHANCE)))
            per_arm_acc[a] = accs
            g = agg(accs)
            outcomes[eff_name][a] = g
            print(f"    {a:<9}{g['mean']:.3f} [{g['min']:.3f},{g['max']:.3f}]")
        spread = max(v["mean"] for v in outcomes[eff_name].values()) - min(
            v["mean"] for v in outcomes[eff_name].values()
        )
        if eff == 0.0:
            print(
                f"    -> spread across arms = {spread:.3f}: NULL as pre-registered "
                "(order alone changes nothing without a discrimination effect).\n"
            )
        else:
            better = outcomes[eff_name]["mixed"]["mean"] - outcomes[eff_name]["blocked"]["mean"]
            print(
                f"    -> mixed - blocked = {better:+.3f} (model-dependent on the "
                f"assumed g={eff}; not a measured cohort result).\n"
            )

    out = {
        "seeds": SEEDS,
        "content": {"topics": TOPICS, "confusable": CONFUSABLE, "per_topic": PER_TOPIC},
        "part_a_mechanism": {
            "same_topic_adjacency": adjacency,
            "interleave_exposure": exposure,
            "hypothesis_mixed_lt_off_lt_blocked": mech_ok,
        },
        "part_b_outcome_model": {
            "constants": {"memory": MEMORY, "base": BASE, "chance": CHANCE},
            "effects": EFFECTS,
            "test_accuracy": outcomes,
            "null_control_spread": round(
                max(v["mean"] for v in outcomes["null_control"].values())
                - min(v["mean"] for v in outcomes["null_control"].values()),
                4,
            ),
        },
        "honesty": (
            "Part A is the real engine measurement. Part B is a seeded simulation "
            "with memory held equal across arms; only the pre-registered "
            "discrimination effect size varies. EFFECT=0 (null control) shows arms "
            "tie. The literature arm is model-dependent and needs a real cohort "
            "(Step 4) to confirm the effect size; it is not claimed as measured."
        ),
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(RESULTS_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
