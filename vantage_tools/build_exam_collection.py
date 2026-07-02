#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project): build a REAL, reviewed exam collection.

Creates a tagged MCAT exam deck, turns FSRS on, turns topic-interleaving on, and
then drives a genuine review history through Anki's own scheduler (``answer_card``)
so the memory score is computed from real FSRS memory states and a real revlog,
never from hand-set stability/difficulty values.

The only thing simulated is the *timing* of each review: each answer's timestamp
(``answered_at``) is set to a point in the recent past, so a few weeks of spaced
practice can be reproduced in seconds. The engine still computes every memory
state, interval, and retrievability itself, exactly as it would for a student who
had studied on those days. See the backend at
``rslib/src/scheduler/answering/mod.rs`` (``card.last_review_time = answered_at``)
and the FSRS elapsed-days calculation right below it.

Usage:
    out/pyenv/bin/python vantage_tools/build_exam_collection.py OUT.anki2
    out/pyenv/bin/python -m anki.vantage.report OUT.anki2
"""

from __future__ import annotations

import os
import random
import sys
import time

from anki import scheduler_pb2
from anki.collection import Collection, ExportAnkiPackageOptions
from anki.vantage.outline import Outline

CardAnswer = scheduler_pb2.CardAnswer
MIXED = scheduler_pb2.SetInterleaveModeRequest.MIXED

RATINGS = ("again", "hard", "good", "easy")
RATING_ENUM = {
    "again": CardAnswer.AGAIN,
    "hard": CardAnswer.HARD,
    "good": CardAnswer.GOOD,
    "easy": CardAnswer.EASY,
}

# A study profile per topic strength. `earlier` are the days-ago of every review
# except the last; `last_ago` is the range for the most recent review (the bigger
# this gap relative to the built-up stability, the more memory has decayed, so the
# lower the retrievability). `weights` are the rating mix after the first pass.
PROFILES = {
    "strong": {"earlier": [26, 17, 9, 4], "last_ago": (2, 8),
               "weights": {"again": 0.03, "hard": 0.12, "good": 0.70, "easy": 0.15}},
    "medium": {"earlier": [21, 12, 6], "last_ago": (5, 15),
               "weights": {"again": 0.10, "hard": 0.28, "good": 0.55, "easy": 0.07}},
    "weak": {"earlier": [24, 13], "last_ago": (12, 24),
             "weights": {"again": 0.42, "hard": 0.30, "good": 0.27, "easy": 0.01}},
}

# concept_id -> (strength, [(front, back), ...]). Tags are written as
# mcat::<section>::<concept_id> so the AAMC outline maps them by concept id.
DECK: dict[str, tuple[str, list[tuple[str, str]]]] = {
    # ---- Chemical & Physical Foundations ----
    "4A": ("strong", [
        ("Formula for kinetic energy?", "KE = 1/2 m v^2"),
        ("Work-energy theorem?", "Net work equals the change in kinetic energy (W = dKE)"),
        ("Condition for translational equilibrium?", "Net force is zero (sum of F = 0)"),
        ("Gravitational potential energy near Earth's surface?", "PE = m g h"),
        ("Power in terms of work and time?", "P = W / t (watts = joules per second)"),
    ]),
    "4E": ("medium", [
        ("What is an isotope?", "Atoms of the same element with different numbers of neutrons"),
        ("What does the principal quantum number n indicate?", "The electron shell / energy level and size"),
        ("Atomic radius trend across a period (left to right)?", "Decreases (increasing effective nuclear charge)"),
        ("Particle emitted in beta-minus decay?", "An electron; a neutron converts to a proton"),
        ("Definition of half-life?", "Time for half of a radioactive sample to decay"),
    ]),
    "5A": ("medium", [
        ("Ion-product constant of water Kw at 25 C?", "1.0 x 10^-14"),
        ("Henderson-Hasselbalch equation?", "pH = pKa + log([A-]/[HA])"),
        ("A buffer resists pH change when it contains?", "A weak acid and its conjugate base"),
        ("pH of a neutral solution at 25 C?", "7"),
        ("Why is water an excellent solvent?", "Its polarity and hydrogen bonding"),
    ]),
    "5B": ("medium", [
        ("Strongest intermolecular force among neutral molecules?", "Hydrogen bonding"),
        ("Difference between sigma and pi bonds?", "Sigma = head-on overlap; pi = side-on overlap"),
        ("Shape of a molecule with 4 bonding pairs and no lone pairs?", "Tetrahedral (109.5 degrees)"),
        ("What is electronegativity?", "An atom's tendency to attract bonding electrons"),
        ("London dispersion forces arise from?", "Temporary / induced dipoles (present in all molecules)"),
    ]),
    "5C": ("medium", [
        ("Principle behind chromatographic separation?", "Differential affinity for the stationary vs mobile phase"),
        ("What does IR spectroscopy detect?", "Functional groups via bond vibrations"),
        ("In distillation, compounds separate by?", "Differences in boiling point"),
        ("What does a mass spectrum m/z peak indicate?", "Mass-to-charge ratio of fragments"),
    ]),
    "5D": ("strong", [
        ("Functional group of a carboxylic acid?", "-COOH"),
        ("What are enantiomers?", "Non-superimposable mirror-image stereoisomers"),
        ("In an SN2 reaction the nucleophile attacks?", "The electrophilic carbon (backside, causing inversion)"),
        ("Aldehyde vs ketone carbonyl position?", "Aldehyde = terminal (CHO); ketone = C=O between carbons"),
        ("What is a racemic mixture?", "Equal parts of two enantiomers (optically inactive)"),
    ]),
    "5E": ("medium", [
        ("Gibbs free energy equation?", "dG = dH - T dS"),
        ("Sign of dG for a spontaneous process?", "Negative"),
        ("Effect of a catalyst on activation energy?", "Lowers it (speeds forward and reverse equally)"),
        ("First law of thermodynamics?", "Energy is conserved; dU = q - w"),
        ("Sign of dH for an endothermic reaction?", "Positive (absorbs heat)"),
    ]),
    # ---- Biological & Biochemical Foundations ----
    "1A": ("strong", [
        ("Bond linking amino acids in a protein?", "Peptide (amide) bond"),
        ("What determines a protein's primary structure?", "The sequence of amino acids"),
        ("What does an enzyme do to a reaction?", "Lowers its activation energy (biological catalyst)"),
        ("What is protein denaturation?", "Loss of structure/function without breaking peptide bonds"),
        ("A competitive inhibitor changes which kinetic value?", "Raises apparent Km; Vmax unchanged"),
    ]),
    "1B": ("medium", [
        ("Central dogma of molecular biology?", "DNA to RNA to protein"),
        ("Enzyme that synthesizes mRNA from DNA?", "RNA polymerase"),
        ("Where does translation occur?", "Ribosomes"),
        ("A codon codes for?", "One amino acid (3 nucleotides)"),
        ("Role of tRNA?", "Brings amino acids to the ribosome; anticodon pairs with codon"),
    ]),
    "1D": ("strong", [
        ("Net ATP yield from glycolysis per glucose?", "2 ATP (plus 2 NADH)"),
        ("Where does the Krebs cycle occur?", "Mitochondrial matrix"),
        ("Final electron acceptor in the electron transport chain?", "Oxygen"),
        ("Where does glycolysis occur?", "The cytoplasm"),
        ("Main energy currency of the cell?", "ATP"),
    ]),
    "2A": ("strong", [
        ("Main structural component of the cell membrane?", "Phospholipid bilayer"),
        ("Organelle called the powerhouse of the cell?", "Mitochondrion"),
        ("Function of the rough ER?", "Protein synthesis (ribosome-studded)"),
        ("Passive diffusion moves solutes?", "Down their concentration gradient (no ATP)"),
        ("What does the sodium-potassium pump do?", "Pumps 3 Na+ out and 2 K+ in (active transport)"),
    ]),
    "2C": ("medium", [
        ("In which phase is DNA replicated?", "S phase of interphase"),
        ("Result of mitosis?", "Two genetically identical diploid daughter cells"),
        ("Meiosis produces?", "Four genetically unique haploid gametes"),
        ("What characterizes stem cells?", "Self-renewal and potency to differentiate"),
    ]),
    "3A": ("medium", [
        ("Resting membrane potential of a neuron?", "About -70 mV"),
        ("Neurotransmitter at the neuromuscular junction?", "Acetylcholine"),
        ("Gland that regulates other endocrine glands?", "Anterior pituitary (master gland)"),
        ("Ion influx that depolarizes a neuron?", "Sodium (Na+)"),
        ("Endocrine vs nervous signaling speed?", "Endocrine is slower/longer; nervous is fast/brief"),
    ]),
    "3B": ("medium", [
        ("Functional unit of the kidney?", "The nephron"),
        ("Where does gas exchange occur in the lungs?", "The alveoli"),
        ("Vessel carrying oxygenated blood from lungs to heart?", "Pulmonary vein"),
        ("Hormone that lowers blood glucose?", "Insulin"),
        ("Heart chamber that pumps blood to the body?", "Left ventricle"),
    ]),
    # ---- Psychological, Social & Biological Foundations ----
    "6B": ("weak", [
        ("Short-term vs long-term memory capacity?", "STM limited (~7 items); LTM essentially unlimited"),
        ("What is the primacy effect?", "Better recall of items at the beginning of a list"),
        ("Encoding of meaning is called?", "Semantic encoding"),
        ("What is proactive interference?", "Old information disrupts recall of new information"),
        ("Brain structure that consolidates new memories?", "The hippocampus"),
    ]),
    "7A": ("weak", [
        ("In classical conditioning the neutral stimulus becomes the?", "Conditioned stimulus (CS)"),
        ("What does negative reinforcement do to behavior?", "Increases it (by removing an aversive stimulus)"),
        ("Who studied observational learning (Bobo doll)?", "Albert Bandura"),
        ("Reinforcement vs punishment?", "Reinforcement increases behavior; punishment decreases it"),
        ("A fixed-ratio schedule reinforces after?", "A set number of responses"),
    ]),
    "8B": ("weak", [
        ("What is the fundamental attribution error?", "Overattributing others' behavior to disposition over situation"),
        ("What is a stereotype?", "A generalized belief about a group"),
        ("Prejudice vs discrimination?", "Prejudice is an attitude; discrimination is a behavior"),
        ("What is the self-serving bias?", "Crediting successes to self and failures to the situation"),
    ]),
    "9A": ("weak", [
        ("What is socioeconomic status (SES)?", "Social standing based on income, education, occupation"),
        ("Durkheim's term for social cohesion?", "Social solidarity (mechanical/organic)"),
        ("What is a social institution?", "An established system meeting a societal need (family, education)"),
        ("Folkway vs more?", "A folkway is a mild norm; a more is a morally significant norm"),
    ]),
}


def _simulate_reviews(col, card, strength, rng, now, seq):
    """Drive a genuine FSRS review history for one card via the real scheduler."""
    prof = PROFILES[strength]
    weights = [prof["weights"][r] for r in RATINGS]
    schedule = list(prof["earlier"]) + [rng.randint(*prof["last_ago"])]
    for i, days_ago in enumerate(schedule):
        card.load()
        states = col._backend.get_scheduling_states(card.id)
        # First pass: a student marks it Good once learned; afterwards, mix.
        rating = "good" if i == 0 else rng.choices(RATINGS, weights=weights, k=1)[0]
        seq[0] += 1
        answered_ms = (now - days_ago * 86400) * 1000 + seq[0]
        answer = CardAnswer(
            card_id=card.id,
            current_state=states.current,
            new_state=getattr(states, rating),
            rating=RATING_ENUM[rating],
            answered_at_millis=answered_ms,
            milliseconds_taken=rng.randint(2000, 9000),
        )
        col._backend.answer_card_raw(answer.SerializeToString())


def build(out_path: str, seed: int = 20260701) -> None:
    if os.path.exists(out_path):
        os.remove(out_path)
    col = Collection(out_path)
    col.set_config("fsrs", True)
    outline = Outline.load()
    basic = col.models.by_name("Basic")
    deck_id = col.decks.id("MCAT Exam")
    rng = random.Random(seed)
    now = int(time.time())
    seq = [0]

    n_cards = 0
    for cid, (strength, cards) in DECK.items():
        concept = outline.concept(cid)
        if concept is None:
            raise SystemExit(f"unknown concept id in DECK: {cid}")
        for front, back in cards:
            note = col.new_note(basic)
            note["Front"] = front
            note["Back"] = back
            note.tags = [f"mcat::{concept.section}::{cid}"]
            col.add_note(note, deck_id)
            _simulate_reviews(col, note.cards()[0], strength, rng, now, seq)
            n_cards += 1

    # Turn the Rust topic-interleaving feature on for this deck too.
    col.sched.set_interleave_mode(mode=MIXED, topic_tag_prefix="mcat", seed=7)

    # Also emit a fresh, shareable, pre-tagged deck (no scheduling) for import.
    apkg = os.path.splitext(out_path)[0] + "_deck.apkg"
    col.export_anki_package(
        out_path=apkg,
        options=ExportAnkiPackageOptions(
            with_scheduling=False, with_deck_configs=False, with_media=False, legacy=False
        ),
        limit=None,
    )
    col.close()

    print(f"built {out_path}: {n_cards} cards, {seq[0]} genuine reviews, FSRS on, interleaving MIXED")
    print(f"exported shareable deck: {apkg}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    build(sys.argv[1])
