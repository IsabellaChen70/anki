# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Per-section topic interleaving for the in-dashboard reviewer (desktop).

The global "Start mixed review" studies the whole due queue through Anki's own
scheduler, where the Rust interleaver
(`rslib/src/scheduler/queue/builder/interleave.rs`) mixes topics. The per-section
"Mix topics" button instead studies ONE section, but still wants its topics
interleaved. That section queue is hand-built by the add-on (a plain list, it
never touches the scheduler), so the engine never sees it. This module reorders
that list the same way.

It is a deliberate, small mirror of the engine's naive `round_robin` (the same
relationship `mobile_scoring.js` has to `scoring.py`): bucket by the full note
tag under a prefix, then drain one card from each non-empty bucket per pass. It
is intentionally seed-free (a focused section session needs no rotation) and
carries NO `aqt`/`anki` imports so it can be unit-tested without a collection.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Tuple

# Bucket for cards with no tag under the prefix. Matches the Rust `UNTAGGED`.
UNTAGGED = "::untagged"

# Marker the web layer prepends to a section key to request the per-section
# topic-mixed mode: the dashboard button emits `study:mix:<section>`, which
# reaches the reviewer as `mix:<section>` (e.g. `mix:bio_biochem`).
MIX_PREFIX = "mix:"


def parse_section_key(raw: str | None) -> tuple[str | None, bool]:
    """Split a reviewer section key into ``(bare_section, topic_mix)``.

    This is the ONE place the ``mix:`` marker is understood, so nothing
    downstream (the tag SQL, the "keep going" broader pool, or any label) ever
    sees the raw marker. Examples::

        "mix:bio_biochem" -> ("bio_biochem", True)
        "bio_biochem"     -> ("bio_biochem", False)
        "interleave"      -> ("interleave", False)
        None / ""         -> (None, False)

    A bare ``"mix:"`` with nothing behind it is meaningless, so it collapses to
    ``(None, False)`` (the whole-queue review) rather than a mix of nothing.
    """
    if not raw:
        return (None, False)
    if raw.startswith(MIX_PREFIX):
        section = raw[len(MIX_PREFIX) :]
        if not section:
            return (None, False)
        return (section, True)
    return (raw, False)


def section_label(section: str | None, labels: Mapping[str, str]) -> str:
    """Friendly, student-facing label for a reviewer section key.

    ``labels`` is the section->label map (the add-on's ``SECTION_LABELS``).
    Returns "" for the whole-queue / mixed review (``section`` None or
    ``"interleave"``). Defensive on purpose: it re-parses through
    :func:`parse_section_key` first, so even if a raw ``"mix:..."`` marker ever
    reached this far it still resolves to the bare section's friendly label
    (e.g. "Bio/Biochem") and never surfaces the raw key.
    """
    bare, _ = parse_section_key(section)
    if not bare or bare == "interleave":
        return ""
    return labels.get(bare, bare)


def topic_key_for_tags(tags: str, prefix: str) -> str:
    """The interleave bucket key for a note's tag string.

    The topic is the FULL note tag under ``prefix`` (e.g.
    ``mcat::bio_biochem::amino_acids``), not just the section, so distinct
    sub-topics interleave against each other. A note carrying several matching
    tags is a first-wins tie-break in SORTED order, so the bucket is
    deterministic rather than an accident of tag storage order. Cards with no
    matching tag fall in the shared ``::untagged`` bucket. Mirrors the Rust
    ``topic_key_for_tags`` policy exactly.
    """
    matching = sorted(t for t in tags.split() if t.startswith(prefix))
    return matching[0] if matching else UNTAGGED


def interleave_cids_by_topic(rows: Iterable[Tuple[int, str]], prefix: str) -> list[int]:
    """Round-robin a section's cards across their topics.

    ``rows`` is an iterable of ``(card_id, tags)`` in the desired input order
    (e.g. due order). Cards are grouped by :func:`topic_key_for_tags`; buckets
    keep first-appearance order and their input order within, and one card is
    drained from each non-empty bucket per pass. So no two consecutive cards
    share a topic WHILE at least two buckets still have cards; once only one
    bucket is left its remainder is unavoidably consecutive (interleaving cannot
    separate a topic from itself). Deterministic. Returns the reordered ids.
    """
    buckets: dict[str, list[int]] = {}
    order: list[str] = []
    for cid, tags in rows:
        key = topic_key_for_tags(tags or "", prefix)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(cid)

    out: list[int] = []
    while True:
        progressed = False
        for key in order:
            bucket = buckets[key]
            if bucket:
                out.append(bucket.pop(0))
                progressed = True
        if not progressed:
            break
    return out
