#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Named sources, SourceRefs, sanitization, and prompt-injection detection.

This is the sourcing + injection-defense foundation for the Vantage AI card
generation layer (spec-ai-cardgen.md). It has NO network dependency and NO LLM:
it loads a small corpus of clearly-marked SYNTHETIC, explicitly-cited source
passages and exposes them as chunks that later stages retrieve, cite, and check.

Honesty-first (per the Vantage rules): every generated or retrofit item must
trace to a NAMED source. A `SourceRef` is that trace: (source_id, sentence span)
resolving to exact text plus the source's citation/license.

Injection defense (spec-ai-cardgen.md sec 6): retrieved text is untrusted DATA.
`sanitize_text` strips hidden/zero-width text and comments; `detect_injection`
flags imperative "ignore your instructions"-style payloads. A chunk that trips
the detector is quarantined and never reaches retrieval or generation.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(HERE, "corpus.json")

# Zero-width / invisible characters an attacker can hide instructions inside.
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_ZERO_WIDTH_RE = re.compile(f"[{_ZERO_WIDTH}]")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Imperative-injection signatures. Matched AFTER de-obfuscation (zero-width
# stripped) so "IGNORE<zwsp> ALL PREVIOUS INSTRUCTIONS" is still caught.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (
        "ignore_instructions",
        r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions",
    ),
    (
        "disregard_rules",
        r"disregard\s+(?:the\s+)?(?:source|previous|prior|above|system|rules?)",
    ),
    ("system_role_injection", r"(?m)^\s*system\s*:"),
    ("developer_mode", r"developer\s+mode"),
    ("reveal_prompt", r"reveal\s+(?:your\s+)?(?:hidden\s+)?(?:system\s+)?prompt"),
    ("override_task", r"no\s+matter\s+what\s+the\s+question"),
    ("new_persona", r"you\s+are\s+now\b"),
]


@dataclass(frozen=True)
class SourceRef:
    """A traceable pointer into the corpus: a source + an inclusive sentence span."""

    source_id: str
    start: int
    end: int

    def locator(self) -> str:
        if self.start == self.end:
            return f"{self.source_id}#s{self.start}"
        return f"{self.source_id}#s{self.start}-s{self.end}"

    @classmethod
    def from_dict(cls, d: dict) -> "SourceRef":
        return cls(source_id=d["source_id"], start=int(d["start"]), end=int(d["end"]))


@dataclass(frozen=True)
class Chunk:
    """One sanitized sentence of a source, addressable by SourceRef."""

    source_id: str
    sent_idx: int
    text: str

    @property
    def chunk_id(self) -> str:
        return f"{self.source_id}#s{self.sent_idx}"

    def ref(self) -> SourceRef:
        return SourceRef(self.source_id, self.sent_idx, self.sent_idx)


@dataclass
class SourceDoc:
    source_id: str
    title: str
    author: str
    license: str
    synthetic: bool
    citation: str
    sentences: list[str]
    canary: bool = False


@dataclass
class Quarantine:
    """A chunk removed before indexing because it tripped injection detection."""

    chunk_id: str
    source_id: str
    sent_idx: int
    reasons: list[str]
    original: str
    sanitized: str


@dataclass
class Corpus:
    docs: dict[str, SourceDoc] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def get(self, source_id: str) -> SourceDoc:
        return self.docs[source_id]

    def resolve(self, ref: SourceRef, sanitized: bool = True) -> str:
        """Return the exact text a SourceRef points to (space-joined sentences)."""
        doc = self.docs[ref.source_id]
        parts = doc.sentences[ref.start : ref.end + 1]
        if sanitized:
            parts = [sanitize_text(p).clean for p in parts]
        return " ".join(parts).strip()

    def citation_for(self, source_id: str) -> str:
        return self.docs[source_id].citation


@dataclass
class Sanitized:
    clean: str
    stripped_zero_width: int
    stripped_comments: int


def sanitize_text(text: str) -> Sanitized:
    """Strip hidden/zero-width chars, HTML comments, and control chars.

    Runs BEFORE injection detection so obfuscated payloads are de-cloaked first.
    """
    zw = len(_ZERO_WIDTH_RE.findall(text))
    comments = len(_HTML_COMMENT_RE.findall(text))
    clean = _HTML_COMMENT_RE.sub(" ", text)
    clean = _ZERO_WIDTH_RE.sub("", clean)
    clean = _CONTROL_RE.sub(" ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return Sanitized(clean=clean, stripped_zero_width=zw, stripped_comments=comments)


def detect_injection(text: str) -> list[str]:
    """Return the names of any injection signatures found in (sanitized) text."""
    lowered = text.lower()
    hits = []
    for name, pat in _INJECTION_PATTERNS:
        if re.search(pat, lowered):
            hits.append(name)
    return hits


def load_corpus(path: str = CORPUS_PATH) -> Corpus:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    docs: dict[str, SourceDoc] = {}
    for s in raw["sources"]:
        docs[s["source_id"]] = SourceDoc(
            source_id=s["source_id"],
            title=s["title"],
            author=s["author"],
            license=s["license"],
            synthetic=bool(s.get("synthetic", False)),
            citation=s["citation"],
            sentences=list(s["sentences"]),
            canary=bool(s.get("canary", False)),
        )
    return Corpus(docs=docs, meta=raw.get("meta", {}))


def build_chunks(corpus: Corpus) -> tuple[list[Chunk], list[Quarantine]]:
    """Sanitize every sentence, quarantine any that trip injection detection.

    Returns (clean_chunks, quarantined). Clean chunks are what the retriever
    indexes and what generation may cite; quarantined chunks are logged and
    never used. This is the enforcement point for "retrieved text is data".
    """
    clean: list[Chunk] = []
    quarantined: list[Quarantine] = []
    for source_id, doc in corpus.docs.items():
        for idx, sentence in enumerate(doc.sentences):
            san = sanitize_text(sentence)
            reasons = detect_injection(san.clean)
            if reasons:
                quarantined.append(
                    Quarantine(
                        chunk_id=f"{source_id}#s{idx}",
                        source_id=source_id,
                        sent_idx=idx,
                        reasons=reasons,
                        original=sentence,
                        sanitized=san.clean,
                    )
                )
                continue
            clean.append(Chunk(source_id=source_id, sent_idx=idx, text=san.clean))
    return clean, quarantined


if __name__ == "__main__":
    corpus = load_corpus()
    chunks, quarantined = build_chunks(corpus)
    print(
        f"sources: {len(corpus.docs)}   clean chunks: {len(chunks)}   quarantined: {len(quarantined)}"
    )
    for q in quarantined:
        print(f"  QUARANTINED {q.chunk_id}: {q.reasons}")
