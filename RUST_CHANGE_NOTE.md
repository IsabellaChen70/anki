# Rust change: topic-interleaving review order

Commit `207318a19` on `vantage/interleaving` (25.09.2 port for AnkiDroid: `290f3771a`).

## What it does

A new review-queue ordering in Anki's Rust core (`rslib`). When enabled, it reorders
the due review cards so consecutive cards come from different topics (round-robin across
topic buckets), where a card's topic is the note tag under a configured prefix, e.g.
`mcat::<section>::<topic>`. Three modes:

- `Off` : stock Anki order.
- `Mixed` : interleave across topics (the tested learning-science feature).
- `Blocked` : group all of one topic, then the next (the ablation's "feature off" arm).

It is exposed to Python via a new protobuf RPC `SetInterleaveMode`, persisted in
collection config under `vantage.interleave` (so it syncs to the phone), and applied
during queue build. FSRS intervals are untouched: this only decides which due card is
shown next.

## Why this belongs in Rust, not Python

- The review queue is built in the Rust core (`rslib/src/scheduler/queue/builder`). The
  order a learner sees is decided there. Doing this in Python would either duplicate/override
  the queue after the fact (fragile) or not change the real review queue at all.
- The engine is shared across frontends over the protobuf boundary, so an `rslib` change
  ships to **desktop and AnkiDroid from one implementation**. The brief requires the change
  to work on the phone; a Python-only change never reaches AnkiDroid, which does not run
  `pylib`.
- Undo and integrity go through Anki's `transact`/`Op` system (`Op::SetInterleaveMode`), which
  lives in Rust; that is what makes the change undoable and keeps the collection from
  corrupting.
- Determinism for the ablation (a `seed`) and the config that syncs both belong at the core.

## Files touched (all additive, low merge risk)

| File | Change | Merge risk |
| --- | --- | --- |
| `proto/anki/scheduler.proto` | add `rpc SetInterleaveMode` + `SetInterleaveModeRequest` | low (append) |
| `rslib/src/scheduler/queue/builder/interleave.rs` | new module: algorithm, config, builder hook, 5 unit tests | none (new file) |
| `rslib/src/scheduler/queue/builder/mod.rs` | one `interleave_reviews_by_topic()` call after gather, + `mod interleave;` | low (one line + decl) |
| `rslib/src/ops.rs` | `Op::SetInterleaveMode` variant, `describe` arm, study-queue-rebuild whitelist | low (enum + match adds) |
| `rslib/src/scheduler/service/mod.rs` | `set_interleave_mode` service handler | low (one trait method) |
| `pylib/anki/scheduler/v3.py` | `set_interleave_mode` Python wrapper | low (one method) |
| `pylib/tests/test_interleave.py` | new Python integration test | none (new file) |

**Overall merge difficulty: LOW.** The change is additive: a new module, a new proto
message, a new `Op` variant, a single hook line in `build_queues`, one service method, and a
Python wrapper. No existing queue logic is rewritten. A future upstream merge would only
conflict if upstream restructures the queue builder or the `Op` enum in those exact regions.

## Tests

- **5 Rust unit tests** (`interleave.rs`): mixed separates topics; blocked groups topics;
  deterministic for a given seed; single-topic/untagged is a no-op; regression for a note
  with more than one review-due card (id de-duplication).
- **1 Python test** (`test_interleave.py`): calls `set_interleave_mode` through the backend,
  checks no two consecutive cards share a topic, asserts the study-queue rebuild flag, runs
  `col.undo()`, and asserts `pragma integrity_check == "ok"`.

## Shipped to the phone

Because it lives in `rslib`, the change is compiled into AnkiDroid's backend (`rsdroid`) from
this fork and verified on-device: the review order interleaves across topics.
