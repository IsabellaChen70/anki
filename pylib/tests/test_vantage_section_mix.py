# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Unit tests for the desktop per-section topic mixer (vantage_addon/section_mix.py).

The per-section "Mix topics" button reorders ONE section's due cards so
consecutive cards come from different topics, mirroring the Rust round-robin in
`rslib/src/scheduler/queue/builder/interleave.rs`. `section_mix.py` is a pure
module (no aqt/anki imports), loaded by path here so the test needs no Anki
collection and does not trip the add-on's GUI imports.
"""

from __future__ import annotations

import importlib.util
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO / "vantage_addon" / "section_mix.py"


def _load():
    spec = importlib.util.spec_from_file_location("vantage_section_mix", _MODULE_PATH)
    assert spec and spec.loader, _MODULE_PATH
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


section_mix = _load()


def _topics(cids, rows):
    tag_of = dict(rows)
    return [section_mix.topic_key_for_tags(tag_of[c], "mcat::") for c in cids]


def test_topic_key_is_full_tag_sorted_first():
    key = section_mix.topic_key_for_tags
    # the topic is the FULL tag, not the section
    assert (
        key("leech mcat::bio_biochem::amino_acids", "mcat::")
        == "mcat::bio_biochem::amino_acids"
    )
    # distinct sub-topics of one section stay distinct (they must interleave)
    assert key("mcat::bio::krebs", "mcat::") != key("mcat::bio::glycolysis", "mcat::")
    # several matching tags -> deterministic first-in-SORTED-order
    assert key("mcat::chem::acids mcat::bio::krebs", "mcat::") == "mcat::bio::krebs"
    assert key("mcat::bio::krebs mcat::chem::acids", "mcat::") == "mcat::bio::krebs"
    # untagged, and a near-miss that must NOT match the prefix
    assert key("leech marked", "mcat::") == section_mix.UNTAGGED
    assert key("mcative::foo", "mcat::") == section_mix.UNTAGGED


def test_balanced_topics_strictly_alternate():
    # 3 topics x 2 cards, in a clumped (blocked) input order.
    rows = [
        (1, "mcat::bio::a"),
        (2, "mcat::bio::a"),
        (3, "mcat::bio::b"),
        (4, "mcat::bio::b"),
        (5, "mcat::bio::c"),
        (6, "mcat::bio::c"),
    ]
    out = section_mix.interleave_cids_by_topic(rows, "mcat::")
    assert len(out) == 6
    assert set(out) == {1, 2, 3, 4, 5, 6}  # nothing dropped or duplicated
    seq = _topics(out, rows)
    for a, b in zip(seq, seq[1:]):
        assert a != b, f"two of a topic in a row: {seq}"


def test_uneven_buckets_repeat_only_at_tail():
    # a x4, b x1: alternate once, then a's remainder is unavoidably consecutive --
    # the honest limit of the guarantee (matches the Rust engine's test).
    rows = [
        (1, "mcat::x::a"),
        (2, "mcat::x::a"),
        (3, "mcat::x::a"),
        (4, "mcat::x::a"),
        (5, "mcat::x::b"),
    ]
    out = section_mix.interleave_cids_by_topic(rows, "mcat::")
    assert out == [1, 5, 2, 3, 4]
    assert _topics(out, rows) == [
        "mcat::x::a",
        "mcat::x::b",
        "mcat::x::a",
        "mcat::x::a",
        "mcat::x::a",
    ]


def test_within_topic_order_is_preserved():
    rows = [
        (10, "mcat::x::a"),
        (20, "mcat::x::b"),
        (11, "mcat::x::a"),
        (21, "mcat::x::b"),
    ]
    out = section_mix.interleave_cids_by_topic(rows, "mcat::")
    assert out.index(10) < out.index(11)
    assert out.index(20) < out.index(21)


def test_single_topic_is_identity():
    rows = [(1, "mcat::x::a"), (2, "mcat::x::a"), (3, "mcat::x::a")]
    assert section_mix.interleave_cids_by_topic(rows, "mcat::") == [1, 2, 3]


def test_untagged_cards_form_their_own_bucket():
    # cards with no mcat:: tag share the UNTAGGED bucket and interleave as one
    # more topic -- never silently dropped.
    rows = [
        (1, "mcat::x::a"),
        (2, "leech"),
        (3, "mcat::x::a"),
        (4, "marked"),
    ]
    out = section_mix.interleave_cids_by_topic(rows, "mcat::")
    assert set(out) == {1, 2, 3, 4}
    seq = _topics(out, rows)
    for a, b in zip(seq, seq[1:]):
        assert a != b, seq  # balanced 2/2 -> strict alternation


def test_deterministic():
    rows = [(i, f"mcat::x::{chr(97 + i % 3)}") for i in range(9)]
    first = section_mix.interleave_cids_by_topic(rows, "mcat::")
    second = section_mix.interleave_cids_by_topic(rows, "mcat::")
    assert first == second


# --------------------------------------------------------------------------- #
# Reviewer section key: the "mix:<section>" marker must be understood in exactly
# one place so nothing downstream (tag SQL, "keep going" pool, or any label) ever
# sees the raw marker. These guard the reported bug where a per-section mix review
# showed "You finished today's reviews for mix:bio_biochem" and offered no
# continue (the raw key leaked into the label and matched zero cards).
# --------------------------------------------------------------------------- #

# Mirror of SECTION_LABELS in vantage_addon/__init__.py, kept here so the pure
# label helper is testable without importing the aqt-bound add-on.
_LABELS = {
    "chem_phys": "Chem/Phys",
    "bio_biochem": "Bio/Biochem",
    "psych_soc": "Psych/Soc",
    "cars": "CARS",
}


def test_parse_section_key_splits_marker_from_section():
    parse = section_mix.parse_section_key
    # the per-section mix marker is stripped, and the flag is raised
    assert parse("mix:bio_biochem") == ("bio_biochem", True)
    # a plain section is itself, no mix
    assert parse("bio_biochem") == ("bio_biochem", False)
    # the whole-queue keys pass through untouched, no mix
    assert parse("interleave") == ("interleave", False)
    assert parse(None) == (None, False)
    # degenerate keys collapse to the whole-queue review, never a mix of nothing
    assert parse("") == (None, False)
    assert parse("mix:") == (None, False)


def test_section_label_is_friendly_and_never_raw_mix():
    label = section_mix.section_label
    # a mix key resolves to the friendly label, not the raw "mix:..." key
    assert label("mix:bio_biochem", _LABELS) == "Bio/Biochem"
    assert label("bio_biochem", _LABELS) == "Bio/Biochem"
    # a mix key must never yield a label outside SECTION_LABELS (the reported bug)
    for key in ("bio_biochem", "mix:bio_biochem", "mix:chem_phys", "mix:psych_soc"):
        out = label(key, _LABELS)
        assert out in _LABELS.values()
        assert not out.startswith("mix:")
    # the whole-queue / mixed review has no single-section label
    assert label(None, _LABELS) == ""
    assert label("interleave", _LABELS) == ""
    # an unknown bare section falls back to itself, still never a raw marker
    assert label("unknown_sec", _LABELS) == "unknown_sec"
