# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Regression tests for the opt-in "generate cards for a thin category" trigger.

This is the layer that connects the coverage map's thin-category signal (which
outline.py flags and collect._topic_gaps ranks) to the EXISTING vantage_tools AI
card-generation pipeline. The trigger adds nothing to the safety story: it reuses
the thin signal, and every generated card goes through the pipeline's OWN
grounding + quality gate before it can be written.

What is proven here, end to end, with no network (the LLM seam is stubbed):
  1. the suggestion appears -- render.dashboard_dict surfaces card_suggestions for
     the categories outline.py already flags as thin (never a new thinness rule);
  2. tapping runs the real pipeline scoped to THAT category, and only cards that
     PASS the real grounding + quality gate are published (with traceability);
  3. nothing bypasses the gate -- a hallucinated/negated card and a vague card are
     blocked, and only the gated cards are ever written to the collection;
  4. honest states -- with no provider configured the trigger says so, it never
     fabricates a success.

The add-on modules (render.py, cardgen_bridge.py) are pure at import time, so they
are loaded by path (as the sibling section_mix/render tests do) without pulling in
the add-on's aqt GUI imports.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

from anki.vantage.outline import Outline
from tests.shared import getEmptyCol

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _load(mod_name: str, filename: str):
    path = _REPO / "vantage_addon" / filename
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses defined under `from __future__ import
    # annotations` can resolve their own module namespace during class creation.
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


render = _load("vantage_render_cg", "render.py")
bridge = _load("vantage_cardgen_bridge", "cardgen_bridge.py")


# The stubbed model output: three cited candidates whose correct verdicts we know
# (each cites a real corpus span). Only the first should survive the gate.
_ENZYME_ANSWER = (
    "An enzyme lowers the reaction's activation energy without being consumed."
)
_NEGATION_ANSWER = (
    "An enzyme is consumed by the reaction as it lowers the activation energy."
)
_VAGUE_ANSWER = "Water."
_STUB_CARDS = [
    {
        "source_id": "src_chapter_metabolism",
        "start": 1,
        "end": 1,
        "stem": "How does an enzyme make a reaction proceed faster?",
        "answer": _ENZYME_ANSWER,  # grounded + specific -> correct_useful (published)
    },
    {
        "source_id": "src_chapter_metabolism",
        "start": 1,
        "end": 1,
        "stem": "Is an enzyme used up as it catalyzes a reaction?",
        "answer": _NEGATION_ANSWER,  # negates the source -> WRONG (blocked)
    },
    {
        "source_id": "src_chapter_metabolism",
        "start": 16,
        "end": 16,
        "stem": "At the end of the electron transport chain, what is oxygen reduced to?",
        "answer": _VAGUE_ANSWER,  # grounded but too vague -> BAD_TEACHING (blocked)
    },
]


def _stub_client(_prompt: str) -> str:
    """Stand in for the LLM seam: returns cited cards, ignores the prompt. No
    network. The pipeline's real screen + grounding + quality gate still run."""
    return json.dumps(_STUB_CARDS)


def _add_card(col, tags, front="q"):
    note = col.newNote()
    note["Front"] = front
    note.tags = list(tags)
    col.addNote(note)


# --------------------------------------------------------------------------- #
# 1. The suggestion decision (render layer), driven by outline.py's thin signal
# --------------------------------------------------------------------------- #
def test_card_suggestions_reuses_thin_gaps_and_excludes_covered():
    # Shaped exactly like collect._topic_gaps output; the last one is fully covered
    # and must never be suggested (it is not a gap).
    topic_gaps = [
        {
            "concept_id": "2B",
            "name": "Microbiology",
            "section": "bio_biochem",
            "covered": 0,
            "total": 6,
        },
        {
            "concept_id": "1A",
            "name": "Proteins",
            "section": "bio_biochem",
            "covered": 1,
            "total": 5,
        },
        {
            "concept_id": "9A",
            "name": "Social structure",
            "section": "psych_soc",
            "covered": 3,
            "total": 3,
        },
    ]
    sugg = render.card_suggestions(topic_gaps)
    ids = [s["concept_id"] for s in sugg]
    assert ids == ["2B", "1A"]  # order preserved, fully-covered 9A dropped
    assert all(s["covered"] < s["total"] for s in sugg)
    assert sugg[0]["name"] == "Microbiology" and sugg[0]["section"] == "bio_biochem"


def test_card_suggestions_caps_at_the_ui_constant():
    many = [
        {
            "concept_id": f"c{i}",
            "name": f"n{i}",
            "section": "bio_biochem",
            "covered": 0,
            "total": 4,
        }
        for i in range(10)
    ]
    sugg = render.card_suggestions(many)
    assert len(sugg) == render.SUGGEST_MAX_THIN_CATEGORIES
    assert [s["concept_id"] for s in sugg] == [
        f"c{i}" for i in range(render.SUGGEST_MAX_THIN_CATEGORIES)
    ]
    # an explicit limit is honored too
    assert len(render.card_suggestions(many, limit=2)) == 2


def test_card_suggestions_ignores_malformed_entries():
    gaps = [
        None,
        {"name": "no id"},
        {
            "concept_id": "1A",
            "name": "ok",
            "section": "bio_biochem",
            "covered": 0,
            "total": 3,
        },
    ]
    sugg = render.card_suggestions(gaps)
    assert [s["concept_id"] for s in sugg] == ["1A"]


def test_dashboard_dict_surfaces_suggestion_for_a_thin_category():
    # Cover ONE topic of category 1A (induced_fit -> topic 1A.4). That makes 1A a
    # genuinely thin category (1 of 5 topics), and -- because a topic is now
    # covered -- collect turns on the topic_gaps signal that drives the suggestion.
    col = getEmptyCol()
    assert Outline.load().match_tag_topic("mcat::bio_biochem::induced_fit") == "1A.4"
    for i in range(3):
        _add_card(col, ["mcat::bio_biochem::induced_fit"], f"enz{i}")

    data = render.dashboard_dict(col)
    tg = data["topic_gaps"]
    cs = data["card_suggestions"]

    # thinness is real, computed by outline + collect (not by the trigger)
    assert tg, "expected the coverage map to flag thin categories"
    one_a = next((g for g in tg if g["concept_id"] == "1A"), None)
    assert one_a is not None and one_a["covered"] == 1 and one_a["total"] == 5

    # the suggestion is exactly the reused top-N of that thin signal
    assert cs, "expected a card-generation suggestion to appear"
    assert cs == render.card_suggestions(tg)
    assert len(cs) <= render.SUGGEST_MAX_THIN_CATEGORIES
    assert cs[0]["concept_id"] == tg[0]["concept_id"]  # thinnest-first, reused
    assert all(s["covered"] < s["total"] for s in cs)  # only genuinely-thin areas


def test_cardgen_capability_flag_is_desktop_only():
    # The desktop body SETS the capability flag; the bundled mobile page must not
    # (there is no generation pipeline on the device). The shared dashboard.js is
    # inlined into both, so it always REFERENCES the flag -- but on mobile it stays
    # undefined, so the suggestion (and its button) never render there.
    assert "window.__VANTAGE_CARDGEN__ = true;" in render.build_body({}, live=True)
    assert "window.__VANTAGE_CARDGEN__ = true;" not in render.build_mobile_page({})


# --------------------------------------------------------------------------- #
# 2 + 3. Tapping runs the real pipeline scoped to the category, gate on the path
# --------------------------------------------------------------------------- #
def test_generate_scopes_to_category_and_publishes_only_gated():
    out = bridge.generate_for_category(
        "1A",
        "Structure and function of proteins and amino acids",
        "bio_biochem",
        ["enzymes", "proteins", "amino acids"],
        client=_stub_client,
        enabled=True,
    )

    assert out.status == bridge.STATUS_GENERATED
    # scoped to THIS category: the label carries the concept id, the retrieval
    # query carries the category's own name/terms.
    assert out.topic_tag == "mcat::vantage::1a"
    assert "proteins" in out.query.lower()

    # only the gated card is published, with its source traceability intact
    assert out.published_count == 1
    pub = out.published[0]
    assert pub["answer"] == _ENZYME_ANSWER
    assert pub["source_ref"]["locator"] == "src_chapter_metabolism#s1"
    # proof the REAL gate ran on the published card
    assert pub["provenance"]["quality_verdict"] == "correct_useful"
    assert "checker_coverage" in pub["provenance"]

    # nothing bypasses the gate: the negated and vague cards were blocked, and
    # neither reaches the published set.
    assert len(out.blocked) == 2
    assert any("negation" in r for r in out.blocked)
    assert any("vague" in r for r in out.blocked)
    published_answers = {c["answer"] for c in out.published}
    assert _NEGATION_ANSWER not in published_answers
    assert _VAGUE_ANSWER not in published_answers


def test_generate_falls_back_to_offline_authored_when_no_provider(monkeypatch):
    # No injected client and no provider key -> generation is NOT off: it falls back
    # to the offline, deterministic authored engine (never a live model, never a
    # fabricated success). A category with no authored source-backed card is honestly
    # empty; a category that HAS authored, gated cards produces them out of the box.
    monkeypatch.delenv(bridge.API_KEY_ENV, raising=False)

    empty = bridge.generate_for_category(
        # 3A has no authored card items (only 12 concepts do); this exercises the
        # honestly-empty path with no provider configured.
        "3A",
        "Structure and function of the nervous and endocrine systems",
        "bio_biochem",
        ["neurons"],
    )
    assert empty.status == bridge.STATUS_GENERATED
    assert empty.detail.get("engine") == "offline_authored"
    assert empty.published == []  # nothing to add, stated honestly (never fabricated)

    real = bridge.generate_for_category(
        "2B",  # a 0-of-6 gap that HAS authored, source-backed cards
        "Structure, growth, physiology, genetics of prokaryotes and viruses",
        "bio_biochem",
        ["prokaryotes", "viruses"],
    )
    assert real.status == bridge.STATUS_GENERATED
    assert real.detail.get("engine") == "offline_authored"
    assert real.published_count >= 3  # real gated cards, with no provider configured
    assert all(p["source_ref"]["locator"] for p in real.published)


# --------------------------------------------------------------------------- #
# 3 (write side). Only gated cards are written; they count toward coverage; dedup
# --------------------------------------------------------------------------- #
def test_only_gated_cards_are_written_and_count_toward_coverage():
    col = getEmptyCol()
    out = bridge.generate_for_category(
        "1A",
        "Structure and function of proteins and amino acids",
        "bio_biochem",
        ["enzymes", "proteins"],
        client=_stub_client,
        enabled=True,
    )
    made = bridge.write_generated_cards(col, "1A", "bio_biochem", out.published)
    assert made == 1  # exactly the one card that passed the gate

    backs = col.db.list(
        "select flds from notes where tags like ?", f"%{bridge.AI_GENERATED_TAG}%"
    )
    assert len(backs) == 1
    blob = backs[0]
    assert _ENZYME_ANSWER in blob  # the gated card, with its answer
    # the blocked (ungated) cards were never written
    assert _NEGATION_ANSWER not in blob
    assert _VAGUE_ANSWER not in blob

    # the written card carries the AAMC coverage tag AND the ai-generated marker
    tags = col.db.scalar(
        "select tags from notes where tags like ?", f"%{bridge.AI_GENERATED_TAG}%"
    )
    assert "mcat::bio_biochem::1A" in tags
    assert bridge.AI_GENERATED_TAG in tags

    # it counts toward coverage on the next read (the tag maps to concept 1A)
    from anki.vantage import collect

    dash = collect.gather(col)
    assert dash.coverage_by_section["bio_biochem"] > 0.0

    # a second tap on the same category does not duplicate already-added cards
    assert bridge.write_generated_cards(col, "1A", "bio_biochem", out.published) == 0
    # and an empty (all-blocked) result writes nothing
    assert bridge.write_generated_cards(col, "1A", "bio_biochem", []) == 0


def test_generate_reports_unavailable_when_pipeline_missing(monkeypatch):
    # If the desktop tools are not shipped, the trigger says so honestly rather
    # than crashing or pretending to generate.
    monkeypatch.setattr(bridge, "_ai_dir", lambda: None)
    out = bridge.generate_for_category(
        "1A", "Proteins", "bio_biochem", ["enzymes"], client=_stub_client, enabled=True
    )
    assert out.status == bridge.STATUS_UNAVAILABLE
    assert out.published == []
