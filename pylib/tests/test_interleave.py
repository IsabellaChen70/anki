# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Vantage (MCAT project): end-to-end test of the topic-interleaving review order.

Exercises the new `SetInterleaveMode` protobuf RPC from Python and checks that the
shared Rust engine reorders the review queue so consecutive cards differ in topic.
"""

from anki import scheduler_pb2
from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
from tests.shared import getEmptyCol

MIXED = scheduler_pb2.SetInterleaveModeRequest.MIXED


def _add_review_card(col, tag: str, front: str) -> None:
    note = col.newNote()
    note["Front"] = front
    note.tags = [tag]
    col.addNote(note)
    card = note.cards()[0]
    card.type = CARD_TYPE_REV
    card.queue = QUEUE_TYPE_REV
    card.due = 0
    card.ivl = 1
    card.flush()


def test_set_interleave_mode_mixes_topics() -> None:
    col = getEmptyCol()
    # Two confusable topics, three review-due cards each.
    for i in range(3):
        _add_review_card(col, "mcat::bio_biochem::amino_acids", f"bio {i}")
        _add_review_card(col, "mcat::chem_phys::acid_base", f"chem {i}")

    # Turn interleaving on via the new Rust-backed RPC; it should flag a rebuild.
    changes = col.sched.set_interleave_mode(mode=MIXED, topic_tag_prefix="mcat", seed=0)
    assert changes.study_queues

    queued = col.sched.get_queued_cards(fetch_limit=100)
    assert queued.review_count == 6

    topics = []
    for queued_card in queued.cards:
        note = col.get_note(queued_card.card.note_id)
        topics.append(next(t for t in note.tags if t.startswith("mcat::")))

    assert len(topics) == 6
    # Mixed mode with balanced buckets: never two of the same topic in a row.
    for first, second in zip(topics, topics[1:]):
        assert first != second

    # The mode change is an undoable op; undo must leave the collection healthy.
    col.undo()
    assert col.db.scalar("pragma integrity_check") == "ok"

    col.close()
