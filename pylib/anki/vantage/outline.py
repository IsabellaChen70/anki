# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — the AAMC content outline + coverage mapping.

Pure: reads the bundled versioned outline JSON and turns a set of card tags into a
weighted coverage number that gates the readiness score (decisions D11 / D-SCORE4).
No Anki/backend imports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

_OUTLINE_PATH = Path(__file__).with_name("aamc_outline.json")
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Topic:
    """A specific AAMC topic under a content category (e.g. "Glycolysis" under 1D).

    Finer than a Concept (content category): topics drive granular coverage and
    gap detection. `category` is the parent content-category id; `section` is
    inherited from that category.
    """

    id: str
    category: str
    section: str
    name: str
    weight: float
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Concept:
    id: str
    section: str
    name: str
    weight: float
    aliases: tuple[str, ...]
    # Optional finer breakdown (AAMC topics under this content category). Empty for
    # outlines that only go to the category grain, so all category-level behaviour
    # is unchanged when topics are absent.
    topics: tuple[Topic, ...] = ()


class Outline:
    """The AAMC content outline: concepts, weights, and tag->concept matching."""

    def __init__(self, data: dict):
        self.version: str = data["version"]
        self.sections: dict[str, str] = dict(data["sections"])
        self.concepts: list[Concept] = []
        self.topics: list[Topic] = []
        for c in data["concepts"]:
            cid = c["id"]
            csection = c["section"]
            ctopics = tuple(
                Topic(
                    id=t["id"],
                    category=cid,
                    section=csection,
                    name=t["name"],
                    weight=float(t.get("weight", 1)),
                    aliases=tuple(a.lower() for a in t.get("aliases", [])),
                )
                for t in c.get("topics", [])
            )
            self.concepts.append(
                Concept(
                    id=cid,
                    section=csection,
                    name=c["name"],
                    weight=float(c.get("weight", 1)),
                    aliases=tuple(a.lower() for a in c.get("aliases", [])),
                    topics=ctopics,
                )
            )
            self.topics.extend(ctopics)
        # lookup tables (category level)
        self._by_id = {c.id.lower(): c for c in self.concepts}
        self._alias_to_id: dict[str, str] = {}
        for c in self.concepts:
            for a in c.aliases:
                self._alias_to_id.setdefault(a, c.id)
        # lookup tables (topic level) — separate from the category tables, so
        # category coverage is byte-for-byte unchanged whether or not topics exist.
        self._topic_by_id = {t.id.lower(): t for t in self.topics}
        self._topic_alias_to_id: dict[str, str] = {}
        for t in self.topics:
            for a in t.aliases:
                self._topic_alias_to_id.setdefault(a, t.id)
        self._topic_match_cache: dict[str, Optional[str]] = {}
        # per-tag memo (see match_tag): a deck has only a handful of distinct tags
        # but the coverage scan calls match_tag once per card, so caching turns an
        # O(cards) loop into O(distinct tags). Instance-scoped, so it resets with
        # each Outline.load() and never leaks across outline versions.
        self._match_cache: dict[str, Optional[str]] = {}
        # Optional deck-hierarchy -> AAMC topic map. Imported decks (e.g. MileDown)
        # carry their own topic hierarchy in tags; this maps those tags (by the
        # NORMALIZED tag string, see _tokens) to AAMC topic ids so topic coverage
        # reflects them. Consulted first in _match_topic_uncached. A missing file
        # just yields an empty map (no effect), so the outline still works alone.
        self._deck_topic_map: dict[str, str] = {}
        _dm = Path(__file__).with_name("deck_topic_map.json")
        try:
            if _dm.exists():
                self._deck_topic_map = dict(
                    json.loads(_dm.read_text(encoding="utf-8")).get("map", {})
                )
        except Exception:
            self._deck_topic_map = {}

    # ---- construction ----
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Outline":
        p = path or _OUTLINE_PATH
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # ---- weights ----
    def total_weight(self) -> float:
        return sum(c.weight for c in self.concepts)

    def section_weight(self, section: str) -> float:
        return sum(c.weight for c in self.concepts if c.section == section)

    # ---- tag -> concept matching ----
    @staticmethod
    def _tokens(tag: str) -> list[str]:
        return [t for t in _TOKEN_RE.split(tag.lower()) if t]

    def match_tag(self, tag: str) -> Optional[str]:
        """Map one raw tag to a concept id, or None. Exact id match wins over alias.

        Memoized per raw tag string: `gather` calls this once for every card, but a
        deck typically has only a handful of distinct tags, so the cache collapses
        the tag->concept work from O(cards) to O(distinct tags) with identical
        results (a measured ~45 ms @50k / ~92 ms @100k drops to a few ms)."""
        cache = self._match_cache
        if tag in cache:
            return cache[tag]
        cid = self._match_tag_uncached(tag)
        cache[tag] = cid
        return cid

    def _match_tag_uncached(self, tag: str) -> Optional[str]:
        tokens = self._tokens(tag)
        if not tokens:
            return None
        token_set = set(tokens)
        # 1) a token equal to a concept id, e.g. "1a", "10a", "mcat::4e"
        for cid_lower, concept in self._by_id.items():
            if cid_lower in token_set:
                return concept.id
        # 2) an alias matches as a whole token, or (for multi-word aliases) as a
        #    "_"-joined phrase inside the tag. Single-word aliases must match a
        #    whole token so short strings (e.g. "ph") can't hit random substrings.
        joined = "_".join(tokens)
        for alias, cid in self._alias_to_id.items():
            if alias in token_set:
                return cid
            if "_" in alias and alias in joined:
                return cid
        return None

    def covered_concepts(self, tags: Iterable[str]) -> set[str]:
        covered: set[str] = set()
        for tag in tags:
            cid = self.match_tag(tag)
            if cid is not None:
                covered.add(cid)
        return covered

    # ---- tag -> topic matching (finer than concept) ----
    def match_tag_topic(self, tag: str) -> Optional[str]:
        """Map one raw tag to a TOPIC id, or None. Same alias rules as `match_tag`,
        over the finer topic aliases; memoized per raw tag. Independent of the
        category matcher, so a tag can map to both a category and a topic."""
        cache = self._topic_match_cache
        if tag in cache:
            return cache[tag]
        tid = self._match_topic_uncached(tag)
        cache[tag] = tid
        return tid

    def _match_topic_uncached(self, tag: str) -> Optional[str]:
        tokens = self._tokens(tag)
        if not tokens:
            return None
        joined = "_".join(tokens)
        # Exact deck-hierarchy match wins (high precision): an imported deck's own
        # topic tag (e.g. MileDown::Biochemistry::Metabolism::Glycolysis) maps
        # straight to its AAMC topic id before the looser alias fallback runs.
        tid = self._deck_topic_map.get(joined)
        if tid is not None:
            return tid
        token_set = set(tokens)
        for alias, tid in self._topic_alias_to_id.items():
            if alias in token_set:
                return tid
            if "_" in alias and alias in joined:
                return tid
        return None

    def covered_topics(self, tags: Iterable[str]) -> set[str]:
        covered: set[str] = set()
        for tag in tags:
            tid = self.match_tag_topic(tag)
            if tid is not None:
                covered.add(tid)
        return covered

    def deck_topic(self, name: str) -> Optional[str]:
        """Topic id for a DECK path via the exact deck_topic_map only (no alias
        fallback). Some decks (e.g. Pankow P/S) encode the topic in the deck path
        rather than in tags; deck names are noisy, so we require an exact map hit."""
        return self._deck_topic_map.get("_".join(self._tokens(name)))

    def topic(self, tid: str) -> Optional[Topic]:
        return self._topic_by_id.get(tid.lower())

    def topic_coverage_by_category(
        self, covered_topic_ids: Iterable[str]
    ) -> dict[str, tuple[int, int]]:
        """Per category id: (covered topic count, total topic count). Only includes
        categories that actually have authored topics."""
        covered = set(covered_topic_ids)
        out: dict[str, tuple[int, int]] = {}
        for c in self.concepts:
            if not c.topics:
                continue
            n_cov = sum(1 for t in c.topics if t.id in covered)
            out[c.id] = (n_cov, len(c.topics))
        return out

    def missing_topics(self, covered_topic_ids: Iterable[str]) -> list["Topic"]:
        """Uncovered topics, heaviest first (the finer coverage gaps)."""
        covered = set(covered_topic_ids)
        missing = [t for t in self.topics if t.id not in covered]
        return sorted(missing, key=lambda t: t.weight, reverse=True)

    # ---- coverage numbers ----
    def weighted_coverage(self, covered_ids: Iterable[str]) -> float:
        covered = set(covered_ids)
        total = self.total_weight()
        if total <= 0:
            return 0.0
        got = sum(c.weight for c in self.concepts if c.id in covered)
        return got / total

    def coverage_by_section(self, covered_ids: Iterable[str]) -> dict[str, float]:
        covered = set(covered_ids)
        out: dict[str, float] = {}
        for section in self.sections:
            sw = self.section_weight(section)
            if sw <= 0:
                out[section] = 0.0
                continue
            got = sum(
                c.weight for c in self.concepts if c.section == section and c.id in covered
            )
            out[section] = got / sw
        return out

    # ---- depth-aware (topic-level) coverage, for the honest display number ----
    def _category_topic_credit(self, c: Concept, covered_t: set, covered_c: set) -> float:
        """Fractional credit for one category: its covered-topic fraction when it has
        topics, else 1.0 if the category itself is covered (no finer grain to measure)."""
        if c.topics:
            return sum(1 for t in c.topics if t.id in covered_t) / len(c.topics)
        return 1.0 if c.id in covered_c else 0.0

    def topic_weighted_coverage(
        self, covered_topic_ids: Iterable[str], covered_ids: Iterable[str] = ()
    ) -> float:
        """Weight-weighted coverage measured at the TOPIC grain: each category
        contributes its weight times the fraction of its topics that have a card.
        This is the honest 'how much of the exam do I actually have cards for' number
        (vs. category-level 'touched every area', which saturates at 100%)."""
        covered_t, covered_c = set(covered_topic_ids), set(covered_ids)
        total = self.total_weight()
        if total <= 0:
            return 0.0
        got = sum(c.weight * self._category_topic_credit(c, covered_t, covered_c) for c in self.concepts)
        return got / total

    def topic_coverage_by_section(
        self, covered_topic_ids: Iterable[str], covered_ids: Iterable[str] = ()
    ) -> dict[str, float]:
        covered_t, covered_c = set(covered_topic_ids), set(covered_ids)
        out: dict[str, float] = {}
        for section in self.sections:
            sw = self.section_weight(section)
            if sw <= 0:
                out[section] = 0.0
                continue
            got = sum(
                c.weight * self._category_topic_credit(c, covered_t, covered_c)
                for c in self.concepts
                if c.section == section
            )
            out[section] = got / sw
        return out

    def missing_concepts(self, covered_ids: Iterable[str]) -> list[Concept]:
        """Uncovered concepts, heaviest first (the coverage gaps)."""
        covered = set(covered_ids)
        missing = [c for c in self.concepts if c.id not in covered]
        return sorted(missing, key=lambda c: c.weight, reverse=True)

    def concept(self, cid: str) -> Optional[Concept]:
        return self._by_id.get(cid.lower())
