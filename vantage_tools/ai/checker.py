#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Grounding checker: does a card's claim trace to its cited source span?

Every generated (or retrofit) card carries a claim and a SourceRef. Before a
card may be published, this checker resolves the SourceRef to its exact span text
and decides whether the span SUPPORTS the claim. Unsupported cards are blocked
(spec-ai-cardgen.md sec 5, criterion 6).

METHOD (deterministic, no model, no network)
    Three signals, all computed from normalized tokens (light stemming, stopword
    removal, and domain synonym expansion via synonyms.json):
      1. coverage  - fraction of the claim's content tokens whose meaning is
                     present in the span (directly or via a synonym). Below the
                     PRE-REGISTERED cutoff -> "low_coverage" (unsupported).
      2. negation_conflict - the claim and the span disagree in polarity (one
                     negates what the other asserts) while otherwise overlapping.
      3. numeric_conflict  - the claim and span both state numbers for the same
                     thing and they differ.

LIMITS (stated honestly; this is NOT a trained entailment model)
    - It is lexical, so a correct claim phrased with vocabulary outside the
      synonym map can be FALSE-REJECTED (see rf_chemphys_q1_mathnotation, whose
      math notation shares few word tokens with the prose source).
    - It can be FOOLED by high word overlap that is not real logical support; the
      negation/numeric signals catch the common contradiction cases but not all.
    - It is a gate that reduces risk, not a proof of truth. A real deployment
      would add a trained NLI/entailment model behind the same interface.

The cutoff is fixed in code BEFORE looking at results (D-AI3): a grounded claim
should have at least half of its content words traceable to the cited span.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from retrieval import SynonymExpander, Tokenizer
from sources import Corpus, SourceRef

# Pre-registered before viewing any results (spec-ai-cardgen.md D-AI3).
COVERAGE_CUTOFF = 0.5

_NEGATION_RE = re.compile(
    r"\b(not|no|never|cannot|can't|without|neither|nor|"
    r"don't|doesn't|didn't|isn't|aren't|wasn't|weren't)\b"
)
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
_DIGIT_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class CheckResult:
    verdict: str  # "supported" | "rejected"
    coverage: float
    reasons: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    claim_negation: bool = False
    span_negation: bool = False
    claim_numbers: list[str] = field(default_factory=list)
    span_numbers: list[str] = field(default_factory=list)
    span_text: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "supported"


class GroundingChecker:
    def __init__(
        self,
        expander: SynonymExpander | None = None,
        cutoff: float = COVERAGE_CUTOFF,
    ) -> None:
        self.expander = expander or SynonymExpander.load()
        self.cutoff = cutoff
        self.tok = Tokenizer(stem=True, remove_stopwords=True)
        self._sib = self._build_sibling_map()

    def _build_sibling_map(self) -> dict[str, set[str]]:
        """token -> all tokens of every alias group that token appears in."""
        sib: dict[str, set[str]] = {}
        for group in self.expander.groups:
            group_tokens: set[str] = set()
            for phrase in group:
                group_tokens.update(self.tok.tokens(phrase))
            for tk in group_tokens:
                sib.setdefault(tk, set()).update(group_tokens)
        return sib

    def _numbers(self, text: str) -> set[str]:
        nums = set(_DIGIT_RE.findall(text.lower()))
        for word, digit in _NUMBER_WORDS.items():
            if re.search(rf"\b{word}\b", text.lower()):
                nums.add(digit)
        return nums

    def check_text(self, claim: str, span_text: str) -> CheckResult:
        claim_tokens = set(self.tok.tokens(claim))
        span_tokens = set(self.tok.tokens(span_text))

        matched, missing = [], []
        for t in sorted(claim_tokens):
            candidates = self._sib.get(t, {t}) | {t}
            if candidates & span_tokens:
                matched.append(t)
            else:
                missing.append(t)
        coverage = (len(matched) / len(claim_tokens)) if claim_tokens else 0.0

        claim_neg = bool(_NEGATION_RE.search(claim.lower()))
        span_neg = bool(_NEGATION_RE.search(span_text.lower()))
        claim_nums = self._numbers(claim)
        span_nums = self._numbers(span_text)

        reasons: list[str] = []
        if coverage < self.cutoff:
            reasons.append("low_coverage")
        # Only treat polarity/number disagreements as contradictions when the two
        # otherwise talk about the same thing (enough overlap), else it is noise.
        if coverage >= self.cutoff and (claim_neg != span_neg):
            reasons.append("negation_conflict")
        if (
            coverage >= self.cutoff
            and (claim_nums - span_nums)
            and (span_nums - claim_nums)
        ):
            reasons.append("numeric_conflict")

        verdict = "supported" if not reasons else "rejected"
        return CheckResult(
            verdict=verdict,
            coverage=coverage,
            reasons=reasons,
            matched=matched,
            missing=missing,
            claim_negation=claim_neg,
            span_negation=span_neg,
            claim_numbers=sorted(claim_nums),
            span_numbers=sorted(span_nums),
            span_text=span_text,
        )

    def check_ref(self, claim: str, ref: SourceRef, corpus: Corpus) -> CheckResult:
        return self.check_text(claim, corpus.resolve(ref))


if __name__ == "__main__":
    from sources import load_corpus

    corpus = load_corpus()
    checker = GroundingChecker()
    supported = checker.check_ref(
        "Adding more substrate can overcome a competitive inhibitor.",
        SourceRef("src_enzyme_inhibition", 2, 2),
        corpus,
    )
    contradicted = checker.check_ref(
        "Adding more substrate can overcome a noncompetitive inhibitor.",
        SourceRef("src_enzyme_inhibition", 5, 5),
        corpus,
    )
    for label, r in [("supported", supported), ("contradicted", contradicted)]:
        print(
            f"{label:<14} verdict={r.verdict:<10} coverage={r.coverage:.2f} reasons={r.reasons}"
        )
