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

## Upgrade: confusability-weighted `Mixed` order

The original `Mixed` mode was a blind round-robin: it rotated topics in fixed
first-appearance order, treating every pair of topics as equally worth
separating. The learning science says otherwise. Interleaving trains
_discrimination_, and its benefit is largest for **confusable** categories; for
dissimilar material the effect shrinks toward null (Brunmair & Richter, 2019,
_Psychological Bulletin_, "Similarity matters: A meta-analysis of interleaved
learning and its moderators"). A smarter interleaver should therefore spend its
adjacencies on the topics a student actually confuses, not on blind rotation.

**What changed (additive).** `Mixed` now reads an _optional_ per-topic-pair
confusability map straight from the same `vantage.interleave` config the toggle
already uses:

```jsonc
"vantage.interleave": {
  "mode": "Mixed",
  "topic_tag_prefix": "mcat",
  "seed": 0,
  // NEW, optional. Topics are the full note tags used as bucket keys.
  "confusability": [
    { "topic_a": "mcat::bio_biochem::amino_acids",
      "topic_b": "mcat::bio_biochem::nucleotides",
      "weight": 5.0 }
  ]
}
```

When `confusability` is **absent or empty**, ordering is **bit-for-bit identical**
to the old naive round-robin (all five original tests still pass unchanged). When
present, the round-robin _rotation order_ is reordered so confusable topics sit
adjacent more often. It never touches the proto, adds no RPC, mutates no cards or
FSRS state, and stays undoable — the engine only **consumes** the map; the Python
side that populates it lands separately.

**Algorithm.** Rather than greedily ping-ponging between two confusable topics
(which would starve the rest), we keep the round-robin — one card per topic per
pass, so no topic is starved and non-confusable topics are simply not forced
apart — but choose the _rotation order_ greedily so the confusable edge lands
inside a pass instead of on the wrap. From the seed-chosen start bucket we hop to
the most-confusable not-yet-placed bucket (nearest-neighbour over the weight
matrix). Candidates are scanned in cyclic order from the start and kept with a
**strict** maximum, so equal weights — and the all-zero-weight case — fall back
to `start, start+1, …`, i.e. exactly the naive rotation, _without ever comparing
floats for equality_. Core loop:

```rust
for _ in 1..n {
    let mut best: Option<usize> = None;
    let mut best_weight = f64::NEG_INFINITY;
    for offset in 0..n {
        let cand = (start + offset) % n;
        if visited[cand] {
            continue;
        }
        let weight = weights[current][cand];
        if weight > best_weight {
            best_weight = weight;
            best = Some(cand);
        }
    }
    let next = best.expect("an unvisited bucket must remain");
    visited[next] = true;
    order.push(next);
    current = next;
}
```

The permutation then drives a plain round-robin (`round_robin_in_order`); with
the identity rotation it is byte-identical to the existing `round_robin`, which is
what guarantees the exact fallback. Deterministic for a given `seed` (the seed
still rotates the start bucket). The proto toggle also now **preserves** any
existing `confusability` map instead of clobbering it, so switching modes never
discards the signal.

_Worked example (3 balanced topics A, B, C with A<->C confusable, seed 0)._ Naive
rotation `A,B,C` yields `A B C A B C …`, so the confusable pair A–C is adjacent
only on the wrap — the _least_ frequent pairing. Weighted rotation `A,C,B` yields
`A C B A C B …`, making A–C the _most_ frequent adjacency while B stays fully
interleaved. That flip is exactly what `confusability_biases_confusable_adjacency`
(Rust) and `test_confusability_config_biases_adjacency` (Python) assert.

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

| File                                              | Change                                                                                                                                                                                                                                                                    | Merge risk              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `proto/anki/scheduler.proto`                      | add `rpc SetInterleaveMode` + `SetInterleaveModeRequest`                                                                                                                                                                                                                  | low (append)            |
| `rslib/src/scheduler/queue/builder/interleave.rs` | new module: algorithm, config, builder hook, 5 unit tests. **Upgrade:** optional `confusability` config field + `ConfusablePair`, weighted rotation (`interleave_by_key_weighted`, `confusability_matrix`, `confusability_order`, `round_robin_in_order`), + 3 unit tests | none (new file)         |
| `rslib/src/scheduler/queue/builder/mod.rs`        | one `interleave_reviews_by_topic()` call after gather, + `mod interleave;`                                                                                                                                                                                                | low (one line + decl)   |
| `rslib/src/ops.rs`                                | `Op::SetInterleaveMode` variant, `describe` arm, study-queue-rebuild whitelist                                                                                                                                                                                            | low (enum + match adds) |
| `rslib/src/scheduler/service/mod.rs`              | `set_interleave_mode` service handler                                                                                                                                                                                                                                     | low (one trait method)  |
| `pylib/anki/scheduler/v3.py`                      | `set_interleave_mode` Python wrapper                                                                                                                                                                                                                                      | low (one method)        |
| `pylib/tests/test_interleave.py`                  | new Python integration test. **Upgrade:** + `test_confusability_config_biases_adjacency`                                                                                                                                                                                  | none (new file)         |

**Overall merge difficulty: LOW.** The change is additive: a new module, a new proto
message, a new `Op` variant, a single hook line in `build_queues`, one service method, and a
Python wrapper. No existing queue logic is rewritten. A future upstream merge would only
conflict if upstream restructures the queue builder or the `Op` enum in those exact regions.

**Upgrade scope.** The confusability-weighted upgrade is contained entirely to
`interleave.rs` and `test_interleave.py` (the two rows marked **Upgrade** above). It adds
**no** proto message or RPC, and touches neither `mod.rs`, `ops.rs`, `service/mod.rs`, nor
`v3.py`: the new field rides inside the existing `vantage.interleave` config blob, so it
already syncs to the phone and reaches AnkiDroid through the same shared core with zero new
surface. The naive default is unchanged and every prior test still passes.

## Tests

- **11 Rust unit tests** (`interleave.rs`). The original 5: mixed separates
  topics; blocked groups topics; deterministic for a given seed; single-topic/untagged is a
  no-op; regression for a note with more than one review-due card (id de-duplication). Plus 3
  for the confusability upgrade:
  - `confusability_biases_confusable_adjacency` — with a weight on A<->C, the weighted order
    alternates A/C strictly more often than the naive round-robin, makes A/C the
    most-alternated pair, and does **not** starve the non-confusable B.
  - `empty_confusability_matches_naive` — empty map (and a map naming only absent topics)
    equals the naive round-robin **byte for byte** across many seeds, and Blocked is
    unaffected by weights.
  - `weighted_deterministic_with_seed` — same seed + weights ⇒ identical order; a different
    seed rotates the start bucket to a different order.

  Plus 3 edge-case tests (this change) that pin the honest limits of the guarantee:
  - `off_mode_is_identity` — `Off` returns a multi-topic input untouched, any seed.
  - `uneven_buckets_repeat_only_at_tail` — A×4/B×1 ⇒ `[A,B,A,A,A]`: once one bucket is
    exhausted the remainder is unavoidably consecutive (the "no two in a row" guarantee holds
    only while ≥2 buckets are non-empty), and nothing is dropped.
  - `untagged_cards_form_their_own_bucket` — cards without a topic map to the shared
    `::untagged` key: interleaved as their own topic under Mixed, grouped under Blocked.

  Scope: only the mature review pool is interleaved; intraday/interday learning cards keep
  their time-ordered sequence (documented in the module header, an intentional scope choice —
  extending to interday-learning `DueCard`s would mirror `interleave_reviews_by_topic`).
- **2 Python tests** (`test_interleave.py`):
  - `test_set_interleave_mode_mixes_topics` (unchanged) — calls `set_interleave_mode` through
    the backend, checks no two consecutive cards share a topic, asserts the study-queue
    rebuild flag, runs `col.undo()`, asserts `pragma integrity_check == "ok"`.
  - `test_confusability_config_biases_adjacency` (new) — writes the `confusability` map to
    `vantage.interleave` config directly (the shape the Python plumbing will persist),
    rebuilds the queue, and asserts the confusable pair is the most-alternated one and the
    collection stays integrity-clean. Proves the engine consumes the map end-to-end with **no
    proto/RPC change**.

Verified locally: `cargo test -p anki interleave` → 11 passed; `pytest pylib/tests/test_interleave.py`
→ 2 passed; the file is `cargo +nightly fmt`-clean and `cargo clippy -p anki` reports no warnings.

## Shipped to the phone

Because it lives in `rslib`, the change is compiled into AnkiDroid's backend (`rsdroid`) from
this fork and verified on-device: the review order interleaves across topics.
