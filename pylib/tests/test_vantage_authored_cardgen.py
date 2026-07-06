# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Offline, deterministic card generation for an AAMC coverage gap.

The dashboard's "Generate cards for a gap" button used to depend on a live LLM
provider: with no provider configured (the shipped default) it produced NOTHING.
This adds the offline, deterministic engine the feature actually ships with -- a
set of authored, corpus-mapped card items (vantage_tools/ai/card_items.json) that
are run through the SAME shared gate every AI card must clear
(cardgen.GenerationPipeline.gate_candidate: SourceRef required -> grounding check
-> teaching-quality gate). Only the cards that PASS are added; anything that fails
is blocked and never written (honesty-first).

What is proven here, end to end, offline (no network, no model):
  1. tapping a gap with no provider configured now produces REAL gated cards, each
     carrying its source citation and locator (PASS case);
  2. those cards are written to the collection with the AAMC concept tag AND a
     finer topic tag, so the gap's "X of Y topics covered" actually shrinks;
  3. nothing bypasses the gate -- a candidate that negates its source (and one with
     no authored content at all) is blocked and NOTHING is written (BLOCKED case);
  4. the gate is REUSED not forked (the authored path calls gate_candidate), and
     every authored, shipped card item passes the gate (the source-map is honest);
  5. a concept with no authored source-backed content is honestly empty, never a
     fabricated success.

The vantage_tools/ai pipeline uses bare imports among its modules, so its dir is
placed on sys.path (as cardgen_bridge does at runtime). cardgen_bridge.py is pure
at import time and is loaded by path, like the sibling trigger/render tests.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

from anki.vantage import collect
from anki.vantage.outline import Outline
from tests.shared import getEmptyCol

_REPO = pathlib.Path(__file__).resolve().parents[2]
_AI = _REPO / "vantage_tools" / "ai"

if str(_AI) not in sys.path:
    sys.path.insert(0, str(_AI))

import authored_cards  # noqa: E402  (imported after sys.path setup)
import cardgen  # noqa: E402
from sources import load_corpus  # noqa: E402


def _load(mod_name: str, filename: str):
    path = _REPO / "vantage_addon" / filename
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


bridge = _load("vantage_cardgen_bridge_authored", "cardgen_bridge.py")


# A candidate that NEGATES its cited span: src_catalysis s2 says a catalyst does
# NOT shift the equilibrium; this claims it does -> the grounding checker rejects
# it. Used to prove the gate blocks and nothing is written.
_NEGATION_ITEM = {
    "id": "bad_negation",
    "concept_id": "1D",
    "section": "chem_phys",
    "topic_id": "1D.1",
    "tag": "bioenergetics",
    "stem": "As a catalyst, what does carbonic anhydrase do to the reaction's equilibrium?",
    "answer": "A catalyst shifts the position of the equilibrium toward the products.",
    "source_ref": {"source_id": "src_catalysis", "start": 2, "end": 2},
}


def _2b_terms():
    return ["prokaryotes", "bacteria", "viruses", "microbiology"]


def _covered_topic_count(col, concept_id: str) -> int:
    """Distinct AAMC topics of `concept_id` that the collection's card tags cover,
    measured with the SAME outline matcher collect uses. (topic_gaps is a top-N
    ranked list, so a nearly-covered area drops off it; this counts directly.)"""
    outline = Outline.load()
    covered = set()
    for (tags,) in col.db.execute("select tags from notes"):
        for tok in (tags or "").split():
            tid = outline.match_tag_topic(tok)
            if tid is not None:
                covered.add(tid)
    n_cov, _total = outline.topic_coverage_by_category(covered).get(concept_id, (0, 0))
    return n_cov


# --------------------------------------------------------------------------- #
# 1 (PASS). Tapping a gap with no provider configured produces REAL gated cards
# --------------------------------------------------------------------------- #
def test_offline_generation_produces_gated_cards_for_a_gap(monkeypatch):
    monkeypatch.delenv(bridge.API_KEY_ENV, raising=False)
    out = bridge.generate_for_category(
        "2B",
        "Structure, growth, physiology, genetics of prokaryotes and viruses",
        "bio_biochem",
        _2b_terms(),
    )
    assert out.status == bridge.STATUS_GENERATED
    assert out.detail.get("engine") == "offline_authored"
    assert out.published_count >= 3, "expected real authored cards for a 0-of-6 gap"

    for pub in out.published:
        # traceability rides with every published card
        assert pub["source_ref"]["locator"], pub
        assert pub["provenance"].get("citation"), pub
        assert pub["provenance"].get("model") == authored_cards.MODEL_NAME
        # proof the REAL gate ran on it
        assert pub["provenance"].get("quality_verdict") == "correct_useful"
        assert "checker_coverage" in pub["provenance"]
        # a finer topic tag rides with it so coverage can move at the topic grain
        assert pub["provenance"].get("coverage_alias")


# --------------------------------------------------------------------------- #
# 2 (WRITE). Gated cards are written with a citation + tags; coverage moves; dedup
# --------------------------------------------------------------------------- #
def test_generated_cards_written_with_citation_and_move_topic_coverage(monkeypatch):
    monkeypatch.delenv(bridge.API_KEY_ENV, raising=False)
    col = getEmptyCol()

    # before: category 2B has no cards, so none of its topics are covered
    assert _covered_topic_count(col, "2B") == 0

    out = bridge.generate_for_category(
        "2B",
        "Structure, growth, physiology, genetics of prokaryotes and viruses",
        "bio_biochem",
        _2b_terms(),
    )
    made = bridge.write_generated_cards(col, "2B", "bio_biochem", out.published)
    assert made >= 3

    # each written note carries a visible source line and the AAMC + topic tags
    rows = col.db.all(
        "select flds, tags from notes where tags like ?",
        f"%{bridge.AI_GENERATED_TAG}%",
    )
    assert len(rows) == made
    for flds, tags in rows:
        assert "Source:" in flds  # the citation rides on the card back
        assert "mcat::bio_biochem::2B" in tags  # concept coverage tag
        assert bridge.AI_GENERATED_TAG in tags

    # the gap actually shrinks: 2B now has covered topics where it had none
    assert _covered_topic_count(col, "2B") >= 3
    # and the whole-collection topic coverage is no longer zero
    assert collect.gather(col).topic_coverage_by_section["bio_biochem"] > 0.0

    # re-tapping the same gap does not duplicate cards already added
    assert bridge.write_generated_cards(col, "2B", "bio_biochem", out.published) == 0


# --------------------------------------------------------------------------- #
# 3 (BLOCKED). A candidate that fails the gate is not published and not written
# --------------------------------------------------------------------------- #
def test_failing_candidate_is_blocked_and_nothing_is_written():
    col = getEmptyCol()
    corpus = load_corpus()
    pipe = cardgen.GenerationPipeline.default(corpus)

    published, blocked = authored_cards.cards_for_concept(
        "1D", corpus, pipe, items=[_NEGATION_ITEM]
    )
    assert published == []
    assert len(blocked) == 1
    _cand, reason = blocked[0]
    assert reason.startswith("wrong:grounding")  # the real checker rejected it

    # nothing to write -> nothing lands in the collection
    made = bridge.write_generated_cards(
        col, "1D", "chem_phys", [c.to_dict() for c in published]
    )
    assert made == 0
    assert (
        col.db.scalar(
            "select count() from notes where tags like ?",
            f"%{bridge.AI_GENERATED_TAG}%",
        )
        == 0
    )


# --------------------------------------------------------------------------- #
# 4. The shipped, authored source-map is honest: every item passes the gate
# --------------------------------------------------------------------------- #
def test_all_authored_cards_pass_the_gate():
    corpus = load_corpus()
    pipe = cardgen.GenerationPipeline.default(corpus)
    items = authored_cards.load_items()
    assert items, "no authored card items found"

    for item in items:
        cand = authored_cards.card_candidate(item, corpus)
        outcome = pipe.gate_candidate(cand, accepted_answers=[])
        assert outcome.published, f"authored item did not pass the gate: {item['id']} ({outcome.reason})"
        # every card resolves to a real, non-empty corpus span
        assert corpus.resolve(cand.source_ref).strip()
        # the item's coverage alias is a real, matcher-recognized outline alias
        from anki.vantage.outline import Outline

        tag = f"mcat::{item['section']}::{item['tag']}"
        assert Outline.load().match_tag_topic(tag) == item["topic_id"], item["id"]


# --------------------------------------------------------------------------- #
# 5. The gate is reused (not forked): the authored path calls gate_candidate
# --------------------------------------------------------------------------- #
def test_authored_path_uses_shared_gate_not_forked():
    assert hasattr(cardgen.GenerationPipeline, "gate_candidate")
    corpus = load_corpus()
    pipe = cardgen.GenerationPipeline.default(corpus)
    items = authored_cards.load_items()
    first = next(i for i in items if i["concept_id"] == "2B")
    cand = authored_cards.card_candidate(first, corpus)
    # gating through the authored helper == gating the candidate directly
    published, _blocked = authored_cards.cards_for_concept(
        first["concept_id"], corpus, pipe, items=[first]
    )
    outcome = pipe.gate_candidate(
        authored_cards.card_candidate(first, corpus), accepted_answers=[]
    )
    assert bool(published) == outcome.published is True


# --------------------------------------------------------------------------- #
# 6. A concept with no authored source-backed content is honestly empty
# --------------------------------------------------------------------------- #
def test_concept_without_authored_content_is_honestly_empty(monkeypatch):
    monkeypatch.delenv(bridge.API_KEY_ENV, raising=False)
    out = bridge.generate_for_category(
        # 4A (physics) has no authored card items -- only 12 concepts do, and 4A is
        # not one of them -- so this exercises the real "honestly empty" behavior.
        "4A",
        "Translational motion, forces, work, energy, equilibrium",
        "chem_phys",
        ["kinematics", "forces"],
    )
    assert out.status == bridge.STATUS_GENERATED
    assert out.published == []  # nothing to add, stated honestly (never fabricated)


# --------------------------------------------------------------------------- #
# 7. Contamination guard: card_items.json is read ONLY by authored_cards, never
#    by an eval/measurement module. This is the invariant that keeps the authored
#    cards (which reuse gold-set corpus spans BY DESIGN) from ever contaminating an
#    eval score. The standalone stdlib proof is
#    vantage_tools/ai/eval_carditems_separation.py (runs without the venv).
# --------------------------------------------------------------------------- #
def test_card_items_read_only_by_authored_cards():
    import eval_carditems_separation as sep  # noqa: E402 (vantage_tools/ai on sys.path)

    scanned, offenders = sep.import_scan()
    assert any(s["present"] for s in scanned), "no eval modules found to scan"
    assert offenders == {}, (
        "an eval/measurement module reads card_items.json (would let the authored "
        f"cards contaminate an eval score): {offenders}"
    )
