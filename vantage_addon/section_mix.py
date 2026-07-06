# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Per-section topic ordering for the in-dashboard reviewer (desktop).

The global "Start mixed review" studies the whole due queue through Anki's own
scheduler, where the Rust interleaver
(`rslib/src/scheduler/queue/builder/interleave.rs`) mixes topics. A per-section
"Flashcards" session instead studies ONE section, on a queue the add-on
hand-builds (a plain list that never touches the scheduler), so the engine never
sees it. This module orders that list.

Whether a section studies Mixed (topics interleaved, to train discrimination) or
Blocked (grouped by topic, for focused acquisition) is decided automatically from
the section's card maturity (see `scoring.section_should_mix`); there is no manual
toggle. `interleave_cids_by_topic` builds the Mixed order and
`block_cids_by_topic` the Blocked order.

Both are deliberate, small mirrors of the engine's naive `round_robin` / `Blocked`
bucketing (the same relationship `mobile_scoring.js` has to `scoring.py`): bucket
by the full note tag under a prefix, then either drain one card from each
non-empty bucket per pass (Mixed) or concatenate the buckets (Blocked).
Intentionally seed-free (a focused section session needs no rotation) and carrying
NO `aqt`/`anki` imports, so it is unit-testable without a collection.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Tuple

# Bucket for cards with no tag under the prefix. Matches the Rust `UNTAGGED`.
UNTAGGED = "::untagged"


def section_label(section: str | None, labels: Mapping[str, str]) -> str:
    """Friendly, student-facing label for a reviewer section key.

    ``labels`` is the section->label map (the add-on's ``SECTION_LABELS``).
    Returns "" for the whole-queue / interleaved review (``section`` None or
    ``"interleave"``); otherwise the friendly label, falling back to the bare
    section key when it is not in the map. Section keys no longer carry any
    marker (the Mixed/Blocked choice is automatic), so this is a plain lookup.
    """
    if not section or section == "interleave":
        return ""
    return labels.get(section, section)


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


def block_cids_by_topic(rows: Iterable[Tuple[int, str]], prefix: str) -> list[int]:
    """Group a section's cards by topic (the Blocked order).

    Same bucketing as :func:`interleave_cids_by_topic` (by the full note tag under
    ``prefix``, first-appearance order of topics preserved, input order within each
    bucket), but the buckets are CONCATENATED rather than round-robined: all of one
    topic, then all of the next. Mirrors the Rust engine's ``Blocked`` mode. This
    is the "focused acquisition" order a section studies until enough of its cards
    have matured. Deterministic. Returns the reordered ids.
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
    for key in order:
        out.extend(buckets[key])
    return out
