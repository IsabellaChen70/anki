// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Vantage (MCAT project): topic-interleaving review order.
//!
//! After the normal review queue has been gathered, optionally reorder the
//! review cards so that consecutive cards come from different topics (a note-tag
//! namespace such as `mcat::<section>::<topic>`). This trains discrimination of
//! which concept a card tests -- the skill MCAT passages demand -- without
//! touching FSRS scheduling. It ships via the normal queue path, so it reaches
//! both the desktop and AnkiDroid builds that call `get_queued_cards`.

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

/// Persisted in the collection config under a dedicated key (see the config helper).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(default)]
pub(crate) struct InterleaveConfig {
    pub(crate) mode: InterleaveMode,
    /// Tag namespace whose first segment identifies a card's topic, e.g. "mcat".
    pub(crate) topic_tag_prefix: String,
    /// Determinism for the ablation; rotates which topic leads.
    pub(crate) seed: u64,
}

/// Reorder `items` by the topic returned from `key_of`.
///
/// Grouping preserves first-appearance order, and each bucket preserves its
/// input order. `Mixed` round-robins across buckets (no two consecutive items
/// share a topic until a bucket empties); `Blocked` concatenates buckets;
/// `Off`, an empty/singleton input, or a single resulting bucket are all the
/// identity. Deterministic for a given `seed`.
fn interleave_by_key<T, K, F>(items: Vec<T>, mode: InterleaveMode, seed: u64, key_of: F) -> Vec<T>
where
    K: std::hash::Hash + Eq,
    F: Fn(&T) -> K,
{
    if matches!(mode, InterleaveMode::Off) || items.len() < 2 {
        return items;
    }

    // Group into buckets, preserving first-appearance order of topics and input
    // order within each topic.
    let mut index: HashMap<K, usize> = HashMap::new();
    let mut buckets: Vec<Vec<T>> = Vec::new();
    for item in items {
        let key = key_of(&item);
        let idx = if let Some(&i) = index.get(&key) {
            i
        } else {
            let i = buckets.len();
            index.insert(key, i);
            buckets.push(Vec::new());
            i
        };
        buckets[idx].push(item);
    }

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

/// Deterministic round-robin across buckets; `seed` rotates the starting bucket.
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

impl QueueBuilder {
    /// Reorder `self.review` in place according to `cfg`, grouping by each card's
    /// note tag under `cfg.topic_tag_prefix`. No-op when disabled, when there are
    /// fewer than two reviews, or when every card maps to the same topic.
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
        self.review = interleave_by_key(reviews, cfg.mode, cfg.seed, |card: &DueCard| {
            topic_by_nid
                .get(&card.note_id)
                .map(String::as_str)
                .unwrap_or(UNTAGGED)
        });
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
        let cfg = InterleaveConfig {
            mode: InterleaveMode::from_proto(input.mode),
            topic_tag_prefix: input.topic_tag_prefix,
            seed: input.seed,
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
        let items = vec![
            ("A", 0),
            ("A", 1),
            ("A", 2),
            ("B", 3),
            ("B", 4),
            ("B", 5),
        ];
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
        CardAdder::new().siblings(2).due_dates(["0", "0"]).add(&mut col);
        col.set_interleave_mode(SetInterleaveModeRequest {
            mode: 1, // MIXED
            topic_tag_prefix: "mcat".to_string(),
            seed: 0,
        })
        .unwrap();
        let queue = col.build_queues(DeckId(1)).unwrap();
        assert_eq!(queue.iter().count(), 2);
    }
}
