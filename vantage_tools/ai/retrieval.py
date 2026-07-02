#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Retrieval over the named-source corpus: a BM25 baseline and the Vantage retriever.

Two retrievers are compared on the gold set (see eval_cardgen.py):

    baseline_bm25   classic BM25 (lowercase alphanumeric tokenization).
    vantage_rag     the SAME BM25 index + BM25 query with domain synonym
                    expansion (synonyms.json), where expansion terms carry a
                    fractional weight because they are lower-confidence than the
                    student's own words.

Because both use the identical tokenizer and index, the ONLY difference is the
expansion, so any recall change is attributable to it. Down-weighting expansion
is what makes it safe: for an in-vocabulary question the direct matches dominate
and expansion changes nothing; for an out-of-vocabulary question ("What is
Vmax?", which the source only ever calls "maximum velocity") the base score is
near zero, so even down-weighted expansion lifts the correct span. The result is
stable for expansion weights ~0.15-0.35 (in-vocabulary recall unchanged, OOV
recovered); 0.25 is used.

No embeddings and no network: a pure-stdlib lexical retriever, which is what keeps
the whole pipeline runnable offline (spec-ai-cardgen.md sec 4). A trained dense
retriever would slot in behind the same Retriever interface.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass

from sources import Chunk

HERE = os.path.dirname(os.path.abspath(__file__))
SYNONYMS_PATH = os.path.join(HERE, "synonyms.json")

BM25_K1 = 1.5
BM25_B = 0.75
# Expansion terms are auxiliary evidence, not the student's own words, so they get
# a fixed fractional weight. Chosen a priori (not tuned to the gold set); results
# are stable across 0.15-0.35 (see module docstring / EVALUATION.md).
EXPANSION_WEIGHT = 0.25

_WORD_RE = re.compile(r"[a-z0-9]+(?:[+'-][a-z0-9]+)*")

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "hundred": "100",
    "half": "0.5",
}

_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "as",
    "from",
    "into",
    "than",
    "then",
    "which",
    "what",
    "when",
    "where",
    "why",
    "how",
    "does",
    "do",
    "did",
    "can",
    "could",
    "will",
    "would",
    "should",
    "not",
    "no",
    "yes",
    "if",
    "so",
    "up",
    "out",
    "about",
    "more",
    "most",
    "some",
    "any",
    "each",
    "own",
    "same",
    "just",
    "only",
    "very",
    "one",
    "two",
    "you",
    "your",
    "they",
    "their",
}


def _light_stem(tok: str) -> str:
    """Small, deterministic suffix stripper (not Porter). Also folds number words
    to digits so "ten to one" and "10 to 1" match."""
    if tok in _NUMBER_WORDS:
        return _NUMBER_WORDS[tok]
    if len(tok) <= 3:
        return tok
    for suf in ("ies",):
        if tok.endswith(suf) and len(tok) > len(suf) + 1:
            return tok[: -len(suf)] + "y"
    for suf in ("ing", "edly", "ed", "es", "ly", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)]
    return tok


class Tokenizer:
    def __init__(self, stem: bool = False, remove_stopwords: bool = False) -> None:
        self.stem = stem
        self.remove_stopwords = remove_stopwords

    def tokens(self, text: str) -> list[str]:
        out = []
        for tok in _WORD_RE.findall(text.lower()):
            if self.remove_stopwords and tok in _STOPWORDS:
                continue
            out.append(_light_stem(tok) if self.stem else tok)
        return out


@dataclass
class SynonymExpander:
    groups: list[list[str]]

    @classmethod
    def load(cls, path: str = SYNONYMS_PATH) -> "SynonymExpander":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls(groups=[list(g) for g in raw["groups"]])

    def expansion_tokens(self, query: str, tokenizer: Tokenizer) -> list[str]:
        """Tokens to ADD: for every alias group with a phrase present in the
        query, contribute the tokens of the group's other phrases."""
        q = " " + re.sub(r"[^a-z0-9]+", " ", query.lower()).strip() + " "
        extra: list[str] = []
        for group in self.groups:
            present = [p for p in group if f" {p} " in q]
            if not present:
                continue
            for phrase in group:
                if phrase in present:
                    continue
                extra.extend(tokenizer.tokens(phrase))
        return extra


class Bm25Index:
    """A deterministic BM25 index over corpus chunks."""

    def __init__(self, chunks: list[Chunk], tokenizer: Tokenizer) -> None:
        self.chunks = list(chunks)
        self.tokenizer = tokenizer
        self.doc_tokens = [tokenizer.tokens(c.text) for c in self.chunks]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.n = len(self.chunks)
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for toks in self.doc_tokens:
            counts: dict[str, int] = {}
            for tk in toks:
                counts[tk] = counts.get(tk, 0) + 1
            self.tf.append(counts)
            for tk in counts:
                df[tk] = df.get(tk, 0) + 1
        self.idf = {
            tk: math.log(1 + (self.n - d + 0.5) / (d + 0.5)) for tk, d in df.items()
        }

    def score(self, query_weights: dict[str, float]) -> list[float]:
        """BM25 with per-term weights (weight 1.0 = an ordinary query term)."""
        scores = [0.0] * self.n
        for i in range(self.n):
            dl = self.doc_len[i]
            denom_norm = BM25_K1 * (
                1 - BM25_B + BM25_B * (dl / self.avgdl if self.avgdl else 0)
            )
            tf_i = self.tf[i]
            s = 0.0
            for tk, wt in query_weights.items():
                f = tf_i.get(tk, 0)
                if not f:
                    continue
                s += wt * self.idf.get(tk, 0.0) * (f * (BM25_K1 + 1)) / (f + denom_norm)
            scores[i] = s
        return scores


@dataclass
class Retriever:
    """Wraps a shared index + optional synonym expansion. `name` labels reports."""

    name: str
    index: Bm25Index
    expander: SynonymExpander | None = None
    expansion_weight: float = EXPANSION_WEIGHT

    def query_weights(self, query: str) -> dict[str, float]:
        weights: dict[str, float] = {t: 1.0 for t in self.index.tokenizer.tokens(query)}
        if self.expander is not None:
            for t in self.expander.expansion_tokens(query, self.index.tokenizer):
                weights[t] = max(weights.get(t, 0.0), self.expansion_weight)
        return weights

    def rank(self, query: str, k: int | None = None) -> list[tuple[Chunk, float]]:
        scores = self.index.score(self.query_weights(query))
        order = sorted(
            range(self.index.n),
            key=lambda i: (-scores[i], self.index.chunks[i].chunk_id),
        )
        ranked = [(self.index.chunks[i], scores[i]) for i in order]
        return ranked[:k] if k else ranked


def build_retrievers(chunks: list[Chunk]) -> dict[str, Retriever]:
    """Baseline and Vantage retriever over one shared index (identical tokenizer),
    so the sole difference is synonym expansion."""
    tokenizer = Tokenizer(stem=False, remove_stopwords=False)
    index = Bm25Index(chunks, tokenizer)
    return {
        "baseline_bm25": Retriever("baseline_bm25", index),
        "vantage_rag": Retriever("vantage_rag", index, expander=SynonymExpander.load()),
    }


if __name__ == "__main__":
    from sources import build_chunks, load_corpus

    chunks, _ = build_chunks(load_corpus())
    retrievers = build_retrievers(chunks)

    def rank_of(retriever, source_id, query):
        for i, (c, _s) in enumerate(retriever.rank(query, k=10), 1):
            if c.source_id == source_id:
                return i
        return None

    # Out-of-vocabulary queries: student jargon the source never spells out.
    demos = [
        ("What is a synonymous substitution?", "src_genetic_code"),
        ("What is Vmax?", "src_enzyme_kinetics"),
    ]
    print(f"{'out-of-vocabulary query':<40}{'baseline rank':>14}{'vantage rank':>14}")
    for query, source_id in demos:
        rb = rank_of(retrievers["baseline_bm25"], source_id, query)
        rv = rank_of(retrievers["vantage_rag"], source_id, query)
        print(f"{query:<40}{str(rb):>14}{str(rv):>14}")
