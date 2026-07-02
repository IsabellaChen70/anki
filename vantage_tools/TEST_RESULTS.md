# Vantage test results (MCAT project)

Captured 2026-07-01. Everything below is reproducible from a clean checkout of
this fork after `./ninja pylib` (see `VANTAGE.md`). Two suites cover the Rust
engine change and the honest scoring layer.

## Reproduce

```bash
# Rust: the topic-interleaving engine change (5 unit tests)
export CARGO_TARGET_DIR=./target
cargo test -p anki interleave

# Python: interleaving end-to-end + the honest scoring layer (22 tests)
./out/pyenv/bin/python -m pytest \
  pylib/tests/test_interleave.py \
  pylib/tests/test_vantage_scoring.py \
  pylib/tests/test_vantage_collect.py -v
```

## Rust engine change: `cargo test -p anki interleave`

```
running 5 tests
test scheduler::queue::builder::interleave::tests::blocked_groups_topics ... ok
test scheduler::queue::builder::interleave::tests::single_topic_or_untagged_is_noop ... ok
test scheduler::queue::builder::interleave::tests::deterministic_with_seed ... ok
test scheduler::queue::builder::interleave::tests::mixed_separates_topics ... ok
test scheduler::queue::builder::interleave::tests::build_queues_handles_note_with_multiple_review_cards ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 395 filtered out
```

These cover: MIXED never places two same-topic cards in a row; BLOCKED groups by
topic; a single/untagged topic is a no-op; the order is deterministic for a fixed
seed; and a note with multiple review cards is handled during queue build.

## Honest scoring + interleaving from Python: `pytest` (22 passed)

```
pylib/tests/test_interleave.py::test_set_interleave_mode_mixes_topics PASSED
pylib/tests/test_vantage_scoring.py::test_outline_loads_all_three_sections PASSED
pylib/tests/test_vantage_scoring.py::test_match_tag_exact_id_and_alias PASSED
pylib/tests/test_vantage_scoring.py::test_weighted_coverage_bounds_and_sections PASSED
pylib/tests/test_vantage_scoring.py::test_memory_abstains_below_min_cards PASSED
pylib/tests/test_vantage_scoring.py::test_memory_point_is_mean_and_range_brackets_it PASSED
pylib/tests/test_vantage_scoring.py::test_memory_is_deterministic PASSED
pylib/tests/test_vantage_scoring.py::test_memory_high_confidence_only_when_tight_and_plentiful PASSED
pylib/tests/test_vantage_scoring.py::test_performance_abstains_below_min_outcomes PASSED
pylib/tests/test_vantage_scoring.py::test_performance_point_and_interval PASSED
pylib/tests/test_vantage_scoring.py::test_give_up_both_conditions_fail PASSED
pylib/tests/test_vantage_scoring.py::test_give_up_reviews_ok_but_coverage_low PASSED
pylib/tests/test_vantage_scoring.py::test_give_up_passes_when_both_met PASSED
pylib/tests/test_vantage_scoring.py::test_readiness_abstains_below_the_line_shows_no_number PASSED
pylib/tests/test_vantage_scoring.py::test_readiness_projects_partial_composite_when_gate_passes PASSED
pylib/tests/test_vantage_scoring.py::test_readiness_is_deterministic PASSED
pylib/tests/test_vantage_scoring.py::test_readiness_not_high_confidence_when_coverage_thin PASSED
pylib/tests/test_vantage_scoring.py::test_map_ability_anchors_and_clamps PASSED
pylib/tests/test_vantage_scoring.py::test_brier_known_values PASSED
pylib/tests/test_vantage_scoring.py::test_wilson_interval_brackets_proportion PASSED
pylib/tests/test_vantage_collect.py::test_memory_uses_real_fsrs_and_coverage_from_tags PASSED
pylib/tests/test_vantage_collect.py::test_readiness_abstains_below_the_line_then_lifts_above_it PASSED

============================== 22 passed in 0.37s ==============================
```

## Summary

| Suite | Command | Result |
| --- | --- | --- |
| Rust engine change (interleaving) | `cargo test -p anki interleave` | 5 passed |
| Interleaving E2E from Python | `pytest test_interleave.py` | 1 passed |
| Scoring core (memory/performance/readiness, give-up, ranges) | `pytest test_vantage_scoring.py` | 19 passed |
| Scoring on a real collection (real FSRS, coverage, give-up) | `pytest test_vantage_collect.py` | 2 passed |
| **Total** | | **27 passed, 0 failed** |
