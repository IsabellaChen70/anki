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
class Concept:
    id: str
    section: str
    name: str
    weight: float
    aliases: tuple[str, ...]


class Outline:
    """The AAMC content outline: concepts, weights, and tag->concept matching."""

    def __init__(self, data: dict):
        self.version: str = data["version"]
        self.sections: dict[str, str] = dict(data["sections"])
        self.concepts: list[Concept] = [
            Concept(
                id=c["id"],
                section=c["section"],
                name=c["name"],
                weight=float(c.get("weight", 1)),
                aliases=tuple(a.lower() for a in c.get("aliases", [])),
            )
            for c in data["concepts"]
        ]
        # lookup tables
        self._by_id = {c.id.lower(): c for c in self.concepts}
        self._alias_to_id: dict[str, str] = {}
        for c in self.concepts:
            for a in c.aliases:
                self._alias_to_id.setdefault(a, c.id)

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
        """Map one raw tag to a concept id, or None. Exact id match wins over alias."""
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

    def missing_concepts(self, covered_ids: Iterable[str]) -> list[Concept]:
        """Uncovered concepts, heaviest first (the coverage gaps)."""
        covered = set(covered_ids)
        missing = [c for c in self.concepts if c.id not in covered]
        return sorted(missing, key=lambda c: c.weight, reverse=True)

    def concept(self, cid: str) -> Optional[Concept]:
        return self._by_id.get(cid.lower())
