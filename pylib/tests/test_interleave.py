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


def _topics_in_queue(col) -> list[str]:
    queued = col.sched.get_queued_cards(fetch_limit=100)
    topics = []
    for queued_card in queued.cards:
        note = col.get_note(queued_card.card.note_id)
        topics.append(next(t for t in note.tags if t.startswith("mcat::")))
    return topics


def test_confusability_config_biases_adjacency() -> None:
    """The engine consumes the optional `confusability` map the Python side writes.

    Backward-compatible: the config is the same `vantage.interleave` blob, just
    with an extra `confusability` list of {topic_a, topic_b, weight}. No proto or
    RPC is involved -- the Rust queue builder reads it straight from config.
    """
    col = getEmptyCol()
    # Three balanced topics; amino_acids <-> nucleotides are the confusable pair.
    amino = "mcat::bio_biochem::amino_acids"
    nucleo = "mcat::bio_biochem::nucleotides"
    kinematics = "mcat::chem_phys::kinematics"
    for i in range(4):
        _add_review_card(col, amino, f"amino {i}")
        _add_review_card(col, kinematics, f"kin {i}")
        _add_review_card(col, nucleo, f"nucleo {i}")

    # Written directly to config (mode is serialized as its variant name). This is
    # exactly what the separate Python plumbing will persist.
    col.set_config(
        "vantage.interleave",
        {
            "mode": "Mixed",
            "topic_tag_prefix": "mcat",
            "seed": 0,
            "confusability": [
                {"topic_a": amino, "topic_b": nucleo, "weight": 5.0},
            ],
        },
    )

    # First build reads the config fresh, so the queue is confusability-ordered.
    topics = _topics_in_queue(col)
    assert len(topics) == 12

    def adjacency(a: str, b: str) -> int:
        return sum(
            1 for first, second in zip(topics, topics[1:]) if {first, second} == {a, b}
        )

    # The confusable pair is alternated at least as often as any other pair --
    # the opposite of the naive round-robin, where it would be the least frequent.
    confusable = adjacency(amino, nucleo)
    assert confusable >= adjacency(amino, kinematics)
    assert confusable >= adjacency(nucleo, kinematics)
    assert confusable > min(adjacency(amino, kinematics), adjacency(nucleo, kinematics))

    assert col.db.scalar("pragma integrity_check") == "ok"
    col.close()
