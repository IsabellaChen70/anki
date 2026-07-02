// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Vantage (MCAT project): topic-interleaving review order.
//!
//! After the normal review queue has been gathered, optionally reorder the
//! review cards so that consecutive cards come from different topics (a
//! note-tag namespace such as `mcat::<section>::<topic>`). This trains
//! discrimination of which concept a card tests -- the skill MCAT passages
//! demand -- without touching FSRS scheduling. It ships via the normal queue
//! path, so it reaches both the desktop and AnkiDroid builds that call
//! `get_queued_cards`.

use std::collections::HashMap;
use std::collections::HashSet;
use std::collections::VecDeque;

use anki_proto::scheduler::SetInterleaveModeRequest;
use serde::Deserialize;
use serde::Serialize;

use super::DueCard;
use super::QueueBuilder;
use crate::ops::Op;
use crate::ops::OpOutput;
use crate::prelude::*;

/// Bucket used for cards lacking a tag under the configured prefix.
const UNTAGGED: &str = "::untagged";

/// Collection-config key holding the persisted interleave settings.
const INTERLEAVE_CONFIG_KEY: &str = "vantage.interleave";

/// How to order the review queue across topics.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub(crate) enum InterleaveMode {
    /// Leave the review order untouched (plain Anki).
    #[default]
    Off,
    /// Round-robin across topic buckets (the tested feature).
    Mixed,
    /// Group all cards of a topic together (the ablation's "feature off" arm).
    Blocked,
}

impl InterleaveMode {
    /// Map the protobuf `SetInterleaveModeRequest.Mode` (i32) to our enum.
    pub(crate) fn from_proto(value: i32) -> Self {
        match value {
            1 => InterleaveMode::Mixed,
            2 => InterleaveMode::Blocked,
            _ => InterleaveMode::Off,
        }
    }
}

/// Persisted in the collection config under a dedicated key (see the config
/// helper).
///
/// `Eq` is intentionally not derived: `confusability` carries `f64` weights.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub(crate) struct InterleaveConfig {
    pub(crate) mode: InterleaveMode,
    /// Tag namespace whose first segment identifies a card's topic, e.g.
    /// "mcat".
    pub(crate) topic_tag_prefix: String,
    /// Determinism for the ablation; rotates which topic leads.
    pub(crate) seed: u64,
    /// Optional Vantage extension: per-topic-pair confusability weights. When
    /// present and `mode` is `Mixed`, the round-robin rotation is reordered so
    /// that confusable topics land next to each other more often --
    /// interleaving helps most for *confusable* categories (Brunmair &
    /// Richter 2019). When absent or empty, the ordering is bit-for-bit
    /// identical to the naive round-robin. The Python side populates this
    /// from its confusion signal; the engine only consumes it (no proto/RPC
    /// involved).
    pub(crate) confusability: Vec<ConfusablePair>,
}

/// One undirected topic pair and how confusable the two topics are: a higher
/// `weight` means the two are more worth alternating adjacently. Topics are the
/// full note tags used as bucket keys, e.g. `mcat::bio_biochem::amino_acids`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub(crate) struct ConfusablePair {
    pub(crate) topic_a: String,
    pub(crate) topic_b: String,
    pub(crate) weight: f64,
}

/// Group `items` into buckets by `key_of`, preserving first-appearance order of
/// keys and input order within each bucket. Returns the buckets alongside the
/// parallel list of their keys, so `keys[i]` is the key of `buckets[i]`.
fn group_by_key<T, K, F>(items: Vec<T>, key_of: F) -> (Vec<Vec<T>>, Vec<K>)
where
    K: std::hash::Hash + Eq + Clone,
    F: Fn(&T) -> K,
{
    let mut index: HashMap<K, usize> = HashMap::new();
    let mut buckets: Vec<Vec<T>> = Vec::new();
    let mut keys: Vec<K> = Vec::new();
    for item in items {
        let key = key_of(&item);
        let idx = if let Some(&i) = index.get(&key) {
            i
        } else {
            let i = buckets.len();
            index.insert(key.clone(), i);
            keys.push(key);
            buckets.push(Vec::new());
            i
        };
        buckets[idx].push(item);
    }
    (buckets, keys)
}

/// Reorder `items` by the topic returned from `key_of` (the naive path).
///
/// Grouping preserves first-appearance order, and each bucket preserves its
/// input order. `Mixed` round-robins across buckets (no two consecutive items
/// share a topic until a bucket empties); `Blocked` concatenates buckets;
/// `Off`, an empty/singleton input, or a single resulting bucket are all the
/// identity. Deterministic for a given `seed`.
fn interleave_by_key<T, K, F>(items: Vec<T>, mode: InterleaveMode, seed: u64, key_of: F) -> Vec<T>
where
    K: std::hash::Hash + Eq + Clone,
    F: Fn(&T) -> K,
{
    if matches!(mode, InterleaveMode::Off) || items.len() < 2 {
        return items;
    }

    let (buckets, _keys) = group_by_key(items, key_of);

    // Nothing to interleave with only one topic -> identity.
    if buckets.len() <= 1 {
        return buckets.into_iter().flatten().collect();
    }

    match mode {
        InterleaveMode::Blocked => buckets.into_iter().flatten().collect(),
        InterleaveMode::Mixed => round_robin(buckets, seed),
        InterleaveMode::Off => unreachable!("handled above"),
    }
}

/// Confusability-weighted variant of [`interleave_by_key`]. Identical to the
/// naive path in every mode except `Mixed`, where the round-robin *rotation
/// order* across buckets is reordered so highly-confusable topic pairs (per
/// `pairs`) sit next to each other more often. Because it only reorders the
/// rotation (not the round-robin itself), every topic is still visited once per
/// pass -- no topic is starved and non-confusable topics are simply not forced
/// apart. With an empty `pairs` slice -- or when no pair names two topics that
/// are both present -- the resulting weight matrix is all zero, the rotation
/// collapses to `start, start+1, ...`, and the output is bit-for-bit identical
/// to the naive [`interleave_by_key`]. Deterministic for a given `seed`.
fn interleave_by_key_weighted<T, K, F>(
    items: Vec<T>,
    mode: InterleaveMode,
    seed: u64,
    pairs: &[ConfusablePair],
    key_of: F,
) -> Vec<T>
where
    K: std::hash::Hash + Eq + Clone + AsRef<str>,
    F: Fn(&T) -> K,
{
    if matches!(mode, InterleaveMode::Off) || items.len() < 2 {
        return items;
    }

    let (buckets, keys) = group_by_key(items, key_of);

    // Nothing to interleave with only one topic -> identity.
    if buckets.len() <= 1 {
        return buckets.into_iter().flatten().collect();
    }

    match mode {
        InterleaveMode::Blocked => buckets.into_iter().flatten().collect(),
        InterleaveMode::Mixed => {
            let labels: Vec<&str> = keys.iter().map(|k| k.as_ref()).collect();
            let weights = confusability_matrix(&labels, pairs);
            let order = confusability_order(&weights, seed, buckets.len());
            round_robin_in_order(buckets, order)
        }
        InterleaveMode::Off => unreachable!("handled above"),
    }
}

/// Build a symmetric bucket-by-bucket confusability matrix from the configured
/// topic-pair weights, where `labels[i]` is bucket `i`'s topic. Pairs naming a
/// topic not present among the buckets, self-pairs, and non-positive or
/// non-finite weights are ignored; a duplicated pair keeps its largest weight.
fn confusability_matrix(labels: &[&str], pairs: &[ConfusablePair]) -> Vec<Vec<f64>> {
    let n = labels.len();
    let mut position: HashMap<&str, usize> = HashMap::with_capacity(n);
    for (i, label) in labels.iter().enumerate() {
        position.entry(*label).or_insert(i);
    }
    let mut weights = vec![vec![0.0_f64; n]; n];
    for pair in pairs {
        if pair.weight.is_finite() && pair.weight > 0.0 {
            if let (Some(&i), Some(&j)) = (
                position.get(pair.topic_a.as_str()),
                position.get(pair.topic_b.as_str()),
            ) {
                if i != j {
                    let w = weights[i][j].max(pair.weight);
                    weights[i][j] = w;
                    weights[j][i] = w;
                }
            }
        }
    }
    weights
}

/// Deterministic rotation order for the round-robin: a permutation of bucket
/// indices, built greedily from the seed-chosen start bucket by repeatedly
/// hopping to the most-confusable not-yet-placed bucket. Candidates are scanned
/// in cyclic order from the start and kept with a strict maximum, so equal
/// weights -- and the all-zero-weight case -- fall back to the naive rotation
/// `start, start+1, ...` without ever comparing floats for equality.
fn confusability_order(weights: &[Vec<f64>], seed: u64, n: usize) -> Vec<usize> {
    let start = (seed % n as u64) as usize;
    let mut visited = vec![false; n];
    let mut order = Vec::with_capacity(n);
    let mut current = start;
    visited[current] = true;
    order.push(current);
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
    order
}

/// Deterministic round-robin across buckets; `seed` rotates the starting
/// bucket.
fn round_robin<T>(buckets: Vec<Vec<T>>, seed: u64) -> Vec<T> {
    let n = buckets.len();
    let start = (seed % n as u64) as usize;
    let total: usize = buckets.iter().map(Vec::len).sum();
    let mut deques: Vec<VecDeque<T>> = buckets.into_iter().map(VecDeque::from).collect();
    let mut out = Vec::with_capacity(total);
    loop {
        let mut progressed = false;
        for offset in 0..n {
            let idx = (start + offset) % n;
            if let Some(item) = deques[idx].pop_front() {
                out.push(item);
                progressed = true;
            }
        }
        if !progressed {
            break;
        }
    }
    out
}

/// Round-robin across buckets in the given rotation `order` (a permutation of
/// bucket indices): one item is drained from each listed bucket per pass until
/// all are empty. With `order == [start, start+1, ...]` this is byte-identical
/// to [`round_robin`] with that same `start`.
fn round_robin_in_order<T>(buckets: Vec<Vec<T>>, order: Vec<usize>) -> Vec<T> {
    let total: usize = buckets.iter().map(Vec::len).sum();
    let mut deques: Vec<VecDeque<T>> = buckets.into_iter().map(VecDeque::from).collect();
    let mut out = Vec::with_capacity(total);
    loop {
        let mut progressed = false;
        for &idx in &order {
            if let Some(item) = deques[idx].pop_front() {
                out.push(item);
                progressed = true;
            }
        }
        if !progressed {
            break;
        }
    }
    out
}

impl QueueBuilder {
    /// Reorder `self.review` in place according to `cfg`, grouping by each
    /// card's note tag under `cfg.topic_tag_prefix`. No-op when disabled,
    /// when there are fewer than two reviews, or when every card maps to
    /// the same topic.
    pub(super) fn interleave_reviews_by_topic(
        &mut self,
        col: &Collection,
        cfg: &InterleaveConfig,
    ) -> Result<()> {
        if matches!(cfg.mode, InterleaveMode::Off) || self.review.len() < 2 {
            return Ok(());
        }

        // Dedupe: a note with >1 review-due card lists its id more than once, and
        // get_note_tags_by_id_list inserts each into a UNIQUE temp table, so a
        // duplicate would fail the whole queue build.
        let note_ids: Vec<NoteId> = self
            .review
            .iter()
            .map(|c| c.note_id)
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();
        let prefix = format!("{}::", cfg.topic_tag_prefix);
        let mut topic_by_nid: HashMap<NoteId, String> = HashMap::new();
        for note_tags in col.storage.get_note_tags_by_id_list(&note_ids)? {
            let topic = note_tags
                .tags
                .split_whitespace()
                .find(|tag| tag.starts_with(&prefix))
                .map(str::to_string)
                .unwrap_or_else(|| UNTAGGED.to_string());
            topic_by_nid.insert(note_tags.id, topic);
        }

        let reviews = std::mem::take(&mut self.review);
        let key_of = |card: &DueCard| {
            topic_by_nid
                .get(&card.note_id)
                .map(String::as_str)
                .unwrap_or(UNTAGGED)
        };
        // No confusability signal -> the exact naive round-robin (unchanged
        // default). Otherwise bias the rotation toward confusable pairs; with no
        // effective weight the weighted path still reduces to the naive order.
        self.review = if cfg.confusability.is_empty() {
            interleave_by_key(reviews, cfg.mode, cfg.seed, key_of)
        } else {
            interleave_by_key_weighted(reviews, cfg.mode, cfg.seed, &cfg.confusability, key_of)
        };
        Ok(())
    }
}

impl Collection {
    /// Current interleave settings (defaults to Off when unset).
    pub(crate) fn get_interleave_config(&self) -> InterleaveConfig {
        self.get_config_optional(INTERLEAVE_CONFIG_KEY)
            .unwrap_or_default()
    }

    /// Persist the interleave mode and trigger a study-queue rebuild.
    pub(crate) fn set_interleave_mode(
        &mut self,
        input: SetInterleaveModeRequest,
    ) -> Result<OpOutput<()>> {
        // The proto toggle only carries mode/prefix/seed; preserve any
        // confusability map the Python side has written so switching modes never
        // discards it.
        let confusability = self.get_interleave_config().confusability;
        let cfg = InterleaveConfig {
            mode: InterleaveMode::from_proto(input.mode),
            topic_tag_prefix: input.topic_tag_prefix,
            seed: input.seed,
            confusability,
        };
        self.transact(Op::SetInterleaveMode, |col| {
            col.set_config(INTERLEAVE_CONFIG_KEY, &cfg)?;
            Ok(())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keys(items: &[(&'static str, u32)]) -> Vec<&'static str> {
        items.iter().map(|x| x.0).collect()
    }

    #[test]
    fn mixed_separates_topics() {
        let items = vec![("A", 0), ("A", 1), ("A", 2), ("B", 3), ("B", 4), ("B", 5)];
        let out = interleave_by_key(items, InterleaveMode::Mixed, 0, |x| x.0);
        // Balanced 3/3 -> strictly alternating, never two of a topic in a row.
        for window in out.windows(2) {
            assert_ne!(window[0].0, window[1].0);
        }
        assert_eq!(out.len(), 6);
    }

    #[test]
    fn blocked_groups_topics() {
        let items = vec![("A", 0), ("B", 1), ("A", 2), ("B", 3)];
        let out = interleave_by_key(items, InterleaveMode::Blocked, 0, |x| x.0);
        assert_eq!(keys(&out), vec!["A", "A", "B", "B"]);
    }

    #[test]
    fn deterministic_with_seed() {
        let make = || {
            vec![
                ("A", 0),
                ("B", 1),
                ("C", 2),
                ("A", 3),
                ("B", 4),
                ("C", 5),
                ("A", 6),
            ]
        };
        let first = interleave_by_key(make(), InterleaveMode::Mixed, 7, |x| x.0);
        let second = interleave_by_key(make(), InterleaveMode::Mixed, 7, |x| x.0);
        assert_eq!(first, second);
    }

    #[test]
    fn single_topic_or_untagged_is_noop() {
        let one_topic = vec![("A", 0), ("A", 1), ("A", 2)];
        assert_eq!(
            interleave_by_key(one_topic.clone(), InterleaveMode::Mixed, 3, |x| x.0),
            one_topic
        );
        assert_eq!(
            interleave_by_key(one_topic.clone(), InterleaveMode::Blocked, 3, |x| x.0),
            one_topic
        );
        let empty: Vec<(&str, u32)> = vec![];
        assert_eq!(
            interleave_by_key(empty.clone(), InterleaveMode::Mixed, 0, |x| x.0),
            empty
        );
    }

    #[test]
    fn build_queues_handles_note_with_multiple_review_cards() {
        // Regression: a note with >1 review-due card lists its id twice in
        // self.review; the tag lookup must dedupe or build_queues fails with a
        // UNIQUE constraint error on the search_nids temp table.
        let mut col = Collection::new();
        // Keep both review siblings (don't bury) so the note id repeats.
        col.update_default_deck_config(|config| {
            config.bury_reviews = false;
        });
        CardAdder::new()
            .siblings(2)
            .due_dates(["0", "0"])
            .add(&mut col);
        col.set_interleave_mode(SetInterleaveModeRequest {
            mode: 1, // MIXED
            topic_tag_prefix: "mcat".to_string(),
            seed: 0,
        })
        .unwrap();
        let queue = col.build_queues(DeckId(1)).unwrap();
        assert_eq!(queue.iter().count(), 2);
    }

    /// How many adjacent positions pair topics `a` and `b` (in either order).
    fn adjacency_count(items: &[(&str, u32)], a: &str, b: &str) -> usize {
        items
            .windows(2)
            .filter(|w| (w[0].0 == a && w[1].0 == b) || (w[0].0 == b && w[1].0 == a))
            .count()
    }

    fn pair(a: &str, b: &str, weight: f64) -> ConfusablePair {
        ConfusablePair {
            topic_a: a.to_string(),
            topic_b: b.to_string(),
            weight,
        }
    }

    /// Three balanced buckets with A<->C flagged confusable: the weighted order
    /// must alternate A and C more often than the naive round-robin does, and
    /// the confusable pair must be the most-alternated pair -- all without
    /// starving the non-confusable B.
    #[test]
    fn confusability_biases_confusable_adjacency() {
        let make = || {
            let mut items = Vec::new();
            for i in 0..4u32 {
                items.push(("A", i));
                items.push(("B", i));
                items.push(("C", i));
            }
            items
        };
        let pairs = vec![pair("A", "C", 5.0)];

        let naive = interleave_by_key(make(), InterleaveMode::Mixed, 0, |x| x.0);
        let weighted =
            interleave_by_key_weighted(make(), InterleaveMode::Mixed, 0, &pairs, |x| x.0);

        // The confusable pair is alternated strictly more often than under naive.
        assert!(
            adjacency_count(&weighted, "A", "C") > adjacency_count(&naive, "A", "C"),
            "weighted A/C adjacency {} should exceed naive {}",
            adjacency_count(&weighted, "A", "C"),
            adjacency_count(&naive, "A", "C"),
        );
        // Under the weighted order the confusable pair is the most-alternated one.
        assert!(adjacency_count(&weighted, "A", "C") >= adjacency_count(&weighted, "A", "B"));
        assert!(adjacency_count(&weighted, "A", "C") >= adjacency_count(&weighted, "B", "C"));
        // Nothing dropped or duplicated; B is still fully interleaved (not blocked).
        assert_eq!(weighted.len(), 12);
        assert_eq!(weighted.iter().filter(|x| x.0 == "B").count(), 4);
    }

    /// The whole point of the fallback: an absent/empty or ineffective map must
    /// reproduce today's naive round-robin byte for byte, for every seed and in
    /// every mode.
    #[test]
    fn empty_confusability_matches_naive() {
        let make = || {
            vec![
                ("A", 0),
                ("B", 1),
                ("C", 2),
                ("A", 3),
                ("B", 4),
                ("C", 5),
                ("A", 6),
                ("B", 7),
                ("A", 8),
            ]
        };
        // A map naming only absent topics resolves to zero effective weight.
        let irrelevant = vec![pair("X", "Y", 9.0)];
        for seed in [0u64, 1, 2, 7, 42, 1000] {
            let naive = interleave_by_key(make(), InterleaveMode::Mixed, seed, |x| x.0);
            let empty =
                interleave_by_key_weighted(make(), InterleaveMode::Mixed, seed, &[], |x| x.0);
            assert_eq!(empty, naive, "empty map must equal naive (seed {seed})");
            let unmatched =
                interleave_by_key_weighted(make(), InterleaveMode::Mixed, seed, &irrelevant, |x| {
                    x.0
                });
            assert_eq!(
                unmatched, naive,
                "unmatched map must equal naive (seed {seed})"
            );
        }
        // Blocked ignores weights entirely, matching the naive path.
        let pairs = vec![pair("A", "B", 3.0)];
        assert_eq!(
            interleave_by_key_weighted(make(), InterleaveMode::Blocked, 0, &pairs, |x| x.0),
            interleave_by_key(make(), InterleaveMode::Blocked, 0, |x| x.0),
        );
    }

    /// Same seed + same weights -> identical order; changing the seed rotates
    /// the start bucket and yields a different order.
    #[test]
    fn weighted_deterministic_with_seed() {
        let make = || {
            let mut items = Vec::new();
            for i in 0..3u32 {
                items.push(("A", i));
                items.push(("B", i));
                items.push(("C", i));
                items.push(("D", i));
            }
            items
        };
        let pairs = vec![pair("A", "C", 4.0), pair("B", "D", 2.0)];

        let first = interleave_by_key_weighted(make(), InterleaveMode::Mixed, 3, &pairs, |x| x.0);
        let second = interleave_by_key_weighted(make(), InterleaveMode::Mixed, 3, &pairs, |x| x.0);
        assert_eq!(first, second);

        let other = interleave_by_key_weighted(make(), InterleaveMode::Mixed, 1, &pairs, |x| x.0);
        assert_ne!(first, other);
    }
}
