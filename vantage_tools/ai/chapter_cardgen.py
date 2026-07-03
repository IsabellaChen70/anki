#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Deterministic, seeded 50-card generator over ONE chapter source (Challenge 7f).

THE LLM IS OFF. This is not a model; it is a fixed, offline stand-in that emits a
known, reproducible batch of 50 candidate cards from a single named source
(`src_chapter_metabolism`) so the SAFETY GATE (grounding + the three-way quality
checker) can be evaluated end to end with no network and no vendor.

Why a hand-built generator with KNOWN labels: to measure whether the gate catches
bad cards, we need cards whose correct verdict we already know. So every card
carries its intended verdict in `provenance["intended"]`, and the batch is a
realistic mix of the mistakes a real generator makes:

    ~34 correct_useful   a real question + a specific, source-grounded answer.
     ~8 wrong            answer negated or number-swapped so GROUNDING rejects it.
     ~8 correct_but_bad_teaching
                         answers that STILL PASS grounding (they are lexically
                         supported by the cited sentence) but are vague, circular
                         (restate the stem), or duplicates of an earlier card.

The "wrong" and "bad_teaching" cards are tuned so the checker/gate actually
assign the intended verdict (verified by eval_cardcheck.py, which reports any
card the gate labels differently -- honestly, not hidden).

Determinism + seeding: the card specs are fixed; a `seed` drives a shuffle of the
emission order for a realistic interleaving. The shuffle keeps every duplicate
card immediately AFTER its anchor (the card it duplicates), because the duplicate
signal is defined against already-ACCEPTED answers -- the anchor must be published
first. Re-running with the same seed yields byte-identical cards.

Reuses cardgen.Candidate + sources.SourceRef/Corpus (same types the rest of the
pipeline publishes and traces).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from cardgen import Candidate
from quality import BAD_TEACHING, CORRECT_USEFUL, WRONG
from sources import Corpus, SourceRef, load_corpus

CHAPTER_SOURCE = "src_chapter_metabolism"
MODEL_NAME = "chapter-cardgen-v1 (deterministic, LLM OFF)"
DEFAULT_SEED = 7


@dataclass(frozen=True)
class CardSpec:
    card_id: str
    start: int  # chapter sentence index (inclusive)
    end: int  # chapter sentence index (inclusive)
    stem: str
    answer: str  # also used as the claim the grounding checker verifies
    intended: str  # CORRECT_USEFUL | WRONG | BAD_TEACHING
    mode: str  # grounded | negation | numeric | vague | circular | duplicate
    dup_of: str | None = None  # for duplicate cards: the anchor card_id


# --- 34 correct_useful: real Q + specific grounded answer --------------------
_USEFUL: list[CardSpec] = [
    CardSpec(
        "u_catabolism",
        0,
        0,
        "In metabolism, which set of reactions releases energy by breaking molecules down?",
        "Catabolism releases energy by breaking molecules down.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_anabolism",
        0,
        0,
        "Which half of metabolism spends energy to build molecules up?",
        "Anabolism spends energy to build molecules up.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_enzyme_role",
        1,
        1,
        "How does an enzyme make a reaction proceed faster?",
        "An enzyme lowers the reaction's activation energy without being consumed.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_active_site",
        2,
        2,
        "What is the part of an enzyme that binds substrate and carries out the chemistry?",
        "The active site of the enzyme.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_induced_fit",
        3,
        3,
        "In the induced-fit model, what does substrate binding do to the active site?",
        "It reshapes the active site so it grips the substrate more snugly.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_optimum",
        4,
        4,
        "What two conditions have an optimum at which an enzyme runs fastest?",
        "Temperature and pH each have an optimum where the catalytic rate peaks.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_denature",
        5,
        5,
        "What does excessive heat do to an enzyme?",
        "Excessive heat denatures the enzyme by unfolding its three-dimensional shape.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_temp37",
        5,
        5,
        "Near what temperature do most human enzymes work fastest?",
        "Near 37 degrees Celsius, close to human body warmth.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_coenzyme",
        6,
        6,
        "What is a coenzyme?",
        "A cofactor that is a small organic molecule derived from a vitamin.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_feedback",
        7,
        7,
        "How does feedback inhibition regulate a metabolic pathway?",
        "The pathway's final product binds and switches off an enzyme acting early in it.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_allosteric",
        8,
        8,
        "How does an allosteric regulator change an enzyme's activity?",
        "It binds a site separate from the active site and raises or lowers activity.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_glyc_location",
        9,
        9,
        "Where does glycolysis happen and what does it make from glucose?",
        "In the cytoplasm, where glucose is cleaved into pyruvate molecules.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_glyc_yield",
        10,
        10,  # anchor for a duplicate
        "What does glycolysis produce per glucose, and does it need oxygen?",
        "Glycolysis nets two ATP and two NADH per glucose and can proceed in the absence of oxygen.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_investment",
        11,
        11,
        "What does the energy investment phase of glycolysis accomplish?",
        "It spends ATP to phosphorylate glucose before any energy is harvested.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_acetyl",
        12,
        12,
        "Aerobically, what is pyruvate converted into before the citric acid cycle?",
        "Pyruvate is oxidized and joined to coenzyme A to form acetyl-CoA.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_acetyl_co2",
        12,
        12,
        "What gas is released as pyruvate is turned into acetyl-CoA?",
        "Carbon dioxide is released as pyruvate becomes acetyl-CoA.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_krebs_loc",
        13,
        13,
        "Where does the citric acid cycle run, and what does it finish?",
        "In the mitochondrial matrix, finishing the oxidizing of carbon to carbon dioxide.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_krebs_alias",
        13,
        13,
        "What is another name for the citric acid cycle?",
        "It is also known as the Krebs cycle, running in the mitochondrial matrix.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_krebs_products",
        14,
        14,
        "What does each single turn of the citric acid cycle generate?",
        "Three NADH, plus FADH2 and GTP.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_etc_loc",
        15,
        15,
        "Where is the electron transport chain located?",
        "In the inner mitochondrial membrane.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_oxygen_water",
        16,
        16,
        "What is the ETC's final electron acceptor, and what forms from it?",
        "Oxygen accepts the electrons and is reduced to water.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_proton_gradient",
        17,
        17,
        "What does the flow of electrons set up across the inner membrane?",
        "It drives protons into the intermembrane space, forming an electrochemical gradient.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_atp_synthase",
        18,
        18,
        "How does ATP synthase generate ATP?",
        "By letting protons flow back into the matrix and using that flow to attach phosphate to ADP.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_atp_count",
        19,
        19,
        "How much ATP does fully oxidizing one glucose aerobically give?",
        "Roughly 30 to 32 ATP in a typical human cell.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_oxphos",
        20,
        20,
        "Which process supplies most of a cell's ATP?",
        "Oxidative phosphorylation supplies the large majority of the cell's ATP.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_anaerobic_etc",
        21,
        21,
        "What happens to the electron transport chain and its NADH when oxygen runs out?",
        "The chain halts and leaves the earlier NADH stuck in its reduced form.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_fermentation",
        22,
        22,
        "How do muscle cells regenerate NAD+ when they lack oxygen?",
        "By running lactic acid fermentation that converts pyruvate into lactate.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_ferment_noatp",
        23,
        23,
        "How much extra ATP does fermentation itself add beyond glycolysis?",
        "Fermentation delivers no ATP beyond the small amount glycolysis already produced.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_gluconeo",
        24,
        24,
        "What is gluconeogenesis?",
        "Gluconeogenesis makes new glucose from noncarbohydrate sources and is not merely glycolysis in reverse.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_insulin",
        25,
        25,
        "How does insulin lower blood glucose?",
        "Insulin prompts cells to take up glucose and store it as glycogen.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_glucagon",
        26,
        26,
        "How does glucagon raise blood glucose?",
        "Glucagon triggers the breakdown of glycogen in the liver.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_beta_ox",
        27,
        27,
        "What does beta-oxidation do with fatty acids?",
        "It chops fatty acids into acetyl-CoA units that feed the citric acid cycle.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_vmax",
        28,
        28,
        "What happens to an enzyme's rate as substrate rises toward a limit?",
        "The rate rises until the active sites are saturated, then levels off at the maximum velocity.",
        CORRECT_USEFUL,
        "grounded",
    ),
    CardSpec(
        "u_km",
        29,
        29,  # anchor for a duplicate
        "What does the Michaelis constant tell you about an enzyme?",
        "It is the substrate concentration at half the maximum velocity, and a smaller value means tighter binding.",
        CORRECT_USEFUL,
        "grounded",
    ),
]

# --- 8 wrong: grounding must REJECT (4 negation, 4 number-swap) ----------------
_WRONG: list[CardSpec] = [
    CardSpec(
        "w_neg_enzyme",
        1,
        1,
        "Is an enzyme used up as it catalyzes a reaction?",
        "An enzyme is consumed by the reaction as it lowers the activation energy.",
        WRONG,
        "negation",
    ),
    CardSpec(
        "w_neg_oxygen",
        16,
        16,
        "Does oxygen act as the final electron acceptor in the ETC?",
        "Oxygen is not the final electron acceptor of the electron transport chain.",
        WRONG,
        "negation",
    ),
    CardSpec(
        "w_neg_atpsynthase",
        18,
        18,
        "Does ATP synthase make ATP as protons flow into the matrix?",
        "ATP synthase does not produce ATP when protons flow into the matrix.",
        WRONG,
        "negation",
    ),
    CardSpec(
        "w_neg_gluconeo",
        24,
        24,
        "Is gluconeogenesis just glycolysis run in reverse?",
        "Gluconeogenesis is simply glycolysis running in reverse.",
        WRONG,
        "negation",
    ),
    CardSpec(
        "w_num_temp",
        5,
        5,
        "Near what temperature do most human enzymes work fastest?",
        "Most human enzymes work fastest near 47 degrees Celsius.",
        WRONG,
        "numeric",
    ),
    CardSpec(
        "w_num_investment",
        11,
        11,
        "How many ATP does the investment phase of glycolysis spend?",
        "The investment phase of glycolysis spends four ATP to phosphorylate glucose.",
        WRONG,
        "numeric",
    ),
    CardSpec(
        "w_num_krebs",
        14,
        14,
        "How many NADH does one turn of the citric acid cycle produce?",
        "One turn of the citric acid cycle produces five NADH.",
        WRONG,
        "numeric",
    ),
    CardSpec(
        "w_num_yield",
        19,
        19,
        "How many ATP does complete aerobic oxidation of one glucose yield?",
        "Fully oxidizing one glucose by aerobic respiration yields only about 4 ATP in a human cell.",
        WRONG,
        "numeric",
    ),
]

# --- 8 correct_but_bad_teaching: PASS grounding but low quality ----------------
_BAD: list[CardSpec] = [
    # vague: fewer than MIN_ANSWER_CONTENT_TOKENS content tokens
    CardSpec(
        "b_vague_cytoplasm",
        9,
        9,
        "Where in the cell does glycolysis take place?",
        "In the cytoplasm.",
        BAD_TEACHING,
        "vague",
    ),
    CardSpec(
        "b_vague_water",
        16,
        16,
        "At the end of the electron transport chain, what is oxygen reduced to?",
        "Water.",
        BAD_TEACHING,
        "vague",
    ),
    CardSpec(
        "b_vague_glycogen",
        25,
        25,
        "Insulin drives cells to store glucose as what?",
        "As glycogen.",
        BAD_TEACHING,
        "vague",
    ),
    # circular: answer's content tokens are a subset of the question's
    CardSpec(
        "b_circ_etc",
        15,
        15,
        "In which membrane is the electron transport chain embedded?",
        "The electron transport chain is embedded.",
        BAD_TEACHING,
        "circular",
    ),
    CardSpec(
        "b_circ_glyc",
        9,
        9,
        "Is glucose cleaved into pyruvate molecules by glycolysis?",
        "Glucose is cleaved into pyruvate molecules by glycolysis.",
        BAD_TEACHING,
        "circular",
    ),
    CardSpec(
        "b_circ_krebs",
        13,
        13,
        "Does the citric acid cycle run in the mitochondrial matrix?",
        "The citric acid cycle runs in the mitochondrial matrix.",
        BAD_TEACHING,
        "circular",
    ),
    # duplicate: near-verbatim repeat of an already-accepted answer
    CardSpec(
        "b_dup_yield",
        10,
        10,
        "How much ATP and NADH does glycolysis yield for each glucose?",
        "Glycolysis nets two ATP and two NADH per glucose and can proceed in the absence of oxygen.",
        BAD_TEACHING,
        "duplicate",
        dup_of="u_glyc_yield",
    ),
    CardSpec(
        "b_dup_km",
        29,
        29,
        "What is the Michaelis constant?",
        "It is the substrate concentration at half the maximum velocity, and a smaller value means tighter binding.",
        BAD_TEACHING,
        "duplicate",
        dup_of="u_km",
    ),
]


def all_specs() -> list[CardSpec]:
    return [*_USEFUL, *_WRONG, *_BAD]


def _grouped_units(specs: list[CardSpec]) -> list[list[CardSpec]]:
    """Group each duplicate immediately after its anchor so a seeded shuffle can
    reorder units without ever placing a duplicate before the card it copies."""
    dependents: dict[str, list[CardSpec]] = {}
    for s in specs:
        if s.dup_of:
            dependents.setdefault(s.dup_of, []).append(s)
    anchors_seen = {s.dup_of for s in specs if s.dup_of}
    known_ids = {s.card_id for s in specs}
    missing = anchors_seen - known_ids
    if missing:
        raise ValueError(f"duplicate anchors not found: {sorted(missing)}")
    units: list[list[CardSpec]] = []
    for s in specs:
        if s.dup_of:
            continue
        unit = [s, *dependents.get(s.card_id, [])]
        units.append(unit)
    return units


def _spec_to_candidate(spec: CardSpec, corpus: Corpus, seed: int) -> Candidate:
    ref = SourceRef(CHAPTER_SOURCE, spec.start, spec.end)
    prompt_hash = hashlib.sha256(
        f"{seed}|{spec.card_id}|{spec.answer}".encode()
    ).hexdigest()[:12]
    return Candidate(
        kind="recall",
        stem=spec.stem,
        answer=spec.answer,
        claim=spec.answer,  # the claim the grounding checker verifies
        source_ref=ref,
        provenance={
            "model": MODEL_NAME,
            "card_id": spec.card_id,
            "intended": spec.intended,  # KNOWN correct verdict (self-validation)
            "error_mode": spec.mode,
            "prompt_hash": prompt_hash,
            "citation": corpus.citation_for(CHAPTER_SOURCE),
            "locator": ref.locator(),
            "seed": seed,
        },
    )


def generate(seed: int = DEFAULT_SEED, corpus: Corpus | None = None) -> list[Candidate]:
    """Return the 50 candidate cards, seeded and deterministic.

    Anchors always precede their duplicates; otherwise the unit order is a
    seeded shuffle for a realistic interleaving of good and bad cards.
    """
    corpus = corpus or load_corpus()
    units = _grouped_units(all_specs())
    rng = random.Random(seed)
    rng.shuffle(units)
    ordered = [spec for unit in units for spec in unit]
    return [_spec_to_candidate(spec, corpus, seed) for spec in ordered]


def intended_counts() -> dict[str, int]:
    counts: dict[str, int] = {CORRECT_USEFUL: 0, WRONG: 0, BAD_TEACHING: 0}
    for s in all_specs():
        counts[s.intended] += 1
    return counts


if __name__ == "__main__":
    cards = generate()
    print(f"generator: {MODEL_NAME}")
    print(f"source: {CHAPTER_SOURCE}   seed: {DEFAULT_SEED}   cards: {len(cards)}")
    print(f"intended label counts: {intended_counts()}\n")
    print("first 8 cards in (seeded) emission order:")
    for c in cards[:8]:
        p = c.provenance
        print(
            f"  [{p['locator']:<28}] intended={p['intended']:<24} "
            f"mode={p['error_mode']:<9} {c.answer[:52]}"
        )
