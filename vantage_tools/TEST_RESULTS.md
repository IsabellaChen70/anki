# Vantage test results (MCAT project)

Updated 2026-07-02. Everything below is reproducible from a clean checkout of this
fork after `./ninja pylib` (see `VANTAGE.md`). The Rust engine change and the honest
scoring layer are covered by unit tests; the re-runnable eval + safety harness is
covered by the one-command runners in the [justfile](../justfile) (`just eval-all`,
`just bench`, `just crash-test`, `just parity`).

## Downloads and evidence map

- **Run it without building:** desktop [`.dmg` + add-on](https://github.com/IsabellaChen70/anki/releases/latest) and Android [`.apk`](https://github.com/IsabellaChen70/Anki-Android/releases/latest).
- **Speed benchmark (50k deck), full detail:** [PERF_RESULTS.md](PERF_RESULTS.md).
- **Eval + ablation methodology:** [EVALUATION.md](EVALUATION.md).
- **Rust engine change write-up:** [../RUST_CHANGE_NOTE.md](../RUST_CHANGE_NOTE.md).
- **AI safety layer:** [../AI_NOTE.md](../AI_NOTE.md).

![Vantage dashboard: three scores with ranges, exam coverage, and the honest give-up state](../docs/img/dashboard.png)

## Reproduce

```bash
# Rust: the topic-interleaving engine change (15 unit tests)
cargo test -p anki interleave

# Python: interleaving end-to-end, the honest scoring layer, and the bank validator (142 tests)
PYTHONPATH=pylib:out/pylib ./out/pyenv/bin/python -m pytest \
  pylib/tests/test_interleave.py \
  pylib/tests/test_vantage_scoring.py \
  pylib/tests/test_vantage_collect.py \
  pylib/tests/test_vantage_reasoning_bank.py -q

# Everything re-runnable in one shot (unit tests + all seeded evals + safety):
just eval-all
```

## Rust engine change: `cargo test -p anki interleave`

```
running 15 tests
test scheduler::queue::builder::interleave::tests::off_mode_is_identity ... ok
test scheduler::queue::builder::interleave::tests::single_topic_or_untagged_is_noop ... ok
test scheduler::queue::builder::interleave::tests::deterministic_with_seed ... ok
test scheduler::queue::builder::interleave::tests::mixed_separates_topics ... ok
test scheduler::queue::builder::interleave::tests::untagged_cards_form_their_own_bucket ... ok
test scheduler::queue::builder::interleave::tests::blocked_groups_topics ... ok
test scheduler::queue::builder::interleave::tests::uneven_buckets_repeat_only_at_tail ... ok
test scheduler::queue::builder::interleave::tests::confusability_biases_confusable_adjacency ... ok
test scheduler::queue::builder::interleave::tests::weighted_deterministic_with_seed ... ok
test scheduler::queue::builder::interleave::tests::empty_confusability_matches_naive ... ok
test scheduler::queue::builder::interleave::tests::build_queues_handles_note_with_multiple_review_cards ... ok
test scheduler::queue::builder::interleave::tests::empty_priorities_match_naive ... ok
test scheduler::queue::builder::interleave::tests::priority_leads_the_rotation ... ok
test scheduler::queue::builder::interleave::tests::topic_key_for_tags_policy ... ok
test scheduler::queue::builder::interleave::tests::filtered_reschedule_deck_interleaves_reviews ... ok

test result: ok. 15 passed; 0 failed; 0 ignored
```

Coverage: MIXED never places two same-topic cards in a row **while ≥2 topic buckets
remain** (and the honest tail case when they don't — `uneven_buckets_repeat_only_at_tail`);
BLOCKED groups by topic; a single/untagged topic is a no-op; untagged cards bucket
together; `Off` is the exact identity; order is deterministic for a fixed seed; the
confusability upgrade biases confusable pairs without starving others and is byte-identical
to naive when unset; and a note with multiple review cards is handled during queue build.
Four newer tests cover the topic-priority upgrade and its parity: a prioritized topic leads the
rotation without starving others (`priority_leads_the_rotation`), empty or unmatched priorities stay
byte-identical to naive (`empty_priorities_match_naive`), each card's topic key is the full
topic-level tag resolved deterministically (`topic_key_for_tags_policy`), and a rescheduling filtered
deck's reviews interleave through the same shared build path (`filtered_reschedule_deck_interleaves_reviews`).

## Honest scoring + interleaving from Python: `pytest` (142 passed)

```
pylib/tests/test_interleave.py ........................................ 2 passed
pylib/tests/test_vantage_scoring.py .................................. 94 passed
pylib/tests/test_vantage_collect.py ................................... 42 passed
pylib/tests/test_vantage_reasoning_bank.py ...... 4 passed
================================ 142 passed ================================
```

These cover: the outline + weighted coverage; the three scores (memory / performance /
readiness) with ranges; the give-up rule (≥200 reviews AND ≥50% coverage); calibration
(Brier, Wilson, IRT/EAP); reasoning outcomes as real sync-safe cards + revlog; per-device
metacognition merge (no clobber / no double-count); confusability pairing; and the
interleaving RPC end-to-end (no two consecutive same-topic cards, undo + integrity clean).

## Reasoning question bank

The application/reasoning practice bank ships **519 questions across 88 passages**: every AAMC science content category (Chem/Phys 10, Bio/Biochem 9, Psych/Soc 12) plus 16 original CARS passages. Every item is original; each science item is tagged to its AAMC concept (`vantage::concept::<id>`, which powers the per-concept transfer gap) and, where tagged, to one of the four AAMC Scientific Inquiry and Reasoning Skills (`skill`, the second diagnostic axis; 423/519 items carry one so far), and cites an OpenStax (CC BY-NC-SA 4.0) chapter by name as a verification anchor (the question text is original; no OpenStax text is copied). The banks live in `vantage_addon/web/reasoning_bank.{cars,chem_phys,bio_biochem,psych_soc}.json`, are injected identically on desktop and mobile by `render.py`, and are validated by `pylib/tests/test_vantage_reasoning_bank.py` (well-formed items, in-range answers, no orphan concepts).

## Re-runnable evals + safety harness (committed artifacts)

Each writes a seeded result file; run individually or via `just eval-all`.

| Area | Command (`just …` or script) | Artifact | Latest result |
| --- | --- | --- | --- |
| Memory calibration | `just eval-memory` | `memory_calibration.json` | beats base rate +11.8% Brier; ECE 0.027 (CALIBRATED) |
| Performance calibration | `just eval-performance` | `performance_results.json` | beats base rate on held-out items |
| Paraphrase transfer gap | `just eval-paraphrase` | `paraphrase_results.json` | transfer gap surfaced; 1 FN reported |
| Interleaving ablation | `just ablation` | `ablation_results.json` | Part A MEASURED: mechanism CONFIRMED (mixed 0.000 < off ~0.16 < blocked 0.903; `off` = stock-order variance). Part B PROJECTED: null ties; bounded mixed-blocked +0.09..+0.26 (g 0.20/0.42/0.60), model-dependent |
| Leakage scan | `just leakage` | `leakage_report.json` | clean (worst 0.50 < 0.80 cutoff) |
| AI retrieval + grounding | `just eval-ai` | `eval_results.json` | beats BM25 (R@3 80→86); grounding 0 false accepts |
| AI 3-way card gate (tuned) | `just eval-ai` | `cardcheck_results.json` | 34/8/8, 0 wrong published, 50/50 |
| AI card gate (independent held-out) | `just eval-ai` | `cardcheck_holdout_results.json` | 22/22 wrong blocked, 14/14 useful published, SAFE |
| AI grounding on REAL text (Wikipedia CC BY-SA 4.0) | `just eval-ai` | `realtext_grounding_results.json` | 18/18 wrong blocked, 14/14 useful published, 0 wrong published, SAFE |
| AI experiment-design item gate (SIRS research) | `just eval-ai` | `experiment_design_results.json` | 9/9 grounded + correct-useful, 0 uncited published |
| AI wired-LLM seam screening | `just eval-ai` | `llm_seam_results.json` | hallucination + injection + fabrication all blocked; AI-off holds |
| Injection canary | `just eval-ai` | (stdout) | CAUGHT |
| Offline degrade | `just offline-test` | `offline_results.json` | AI off + scores locally; graceful on network loss |
| Score-mapping anchors + sensitivity | `just score-map` | `score_mapping_results.json` | monotonic; ±1 scale-pt sensitivity; pilot harness ready |
| Desktop↔phone scoring parity | `just parity` | `scoring_parity_results.json` | 27 values match to 2.8e-16 |
| Speed benchmark (50k) | `just bench` | `PERF_RESULTS.md` | all §11 p50/p95 budgets PASS |
| Desktop crash (20× kill) | `just crash-test` | `crash_results.json` | 20/20, zero corruption |
| Android crash (20× force-stop) | (device script) | `android_crash_results.json` | 20/20, zero corruption |
| Two-way sync reconcile (10+10) | (self-hosted server) | `sync_reconcile_results.json` | 351→371, 0 duplicates; later-review wins |

## Summary

| Suite | Command | Result |
| --- | --- | --- |
| Rust engine change (interleaving) | `cargo test -p anki interleave` | **15 passed** |
| Interleaving E2E + honest scoring (Python) | `pytest` (4 files) | **142 passed** |
| Reasoning question bank (519 items, no orphan concepts) | `pytest test_vantage_reasoning_bank.py` | **validated** |
| **Unit-test total** | | **157 passed, 0 failed** |
| Re-runnable evals + safety | `just eval-all` | all pass (see table above) |
