#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Three-way card quality gate (Challenge 7f / spec-ai-cardgen.md sec 5).

The grounding checker (checker.py) answers only ONE question: does the card's
claim trace to its cited source span? That is faithfulness, not teaching value.
A card can be perfectly grounded and still be useless -- too vague to teach, a
tautology that just restates its own question, or a duplicate of a card the
student already has. This module adds the second gate, turning the two-way
(supported / rejected) faithfulness check into the three-way verdict the spec
asks for:

    wrong                    the grounding checker REJECTED the card (low
                             coverage, a negation conflict, or a numeric
                             conflict). The claim is not supported by its source.
    correct_but_bad_teaching grounding PASSED, but the card is low quality:
                               (a) vague     -- the answer has fewer than
                                   MIN_ANSWER_CONTENT_TOKENS content tokens
                                   (after stopword removal), or
                               (b) circular  -- the answer's content tokens are a
                                   subset of the question's, so it merely restates
                                   the stem, or
                               (c) duplicate -- the answer's word-trigram Jaccard
                                   is >= DUP_THRESHOLD against a card already
                                   accepted in this batch.
    correct_useful           grounding passed AND none of the above: a specific,
                             non-circular, non-duplicate answer worth publishing.

Only correct_useful cards are published; wrong and correct_but_bad_teaching are
blocked (spec sec 5, criterion 6: nothing reaches a student until it passes).

PRE-REGISTERED THRESHOLDS (fixed in code BEFORE any generator output was scored,
per D-AI3; changing them after seeing results would be p-hacking):

    GROUNDING_CUTOFF            = 0.5   (imported from checker.COVERAGE_CUTOFF;
                                        the faithfulness cutoff this gate reuses)
    MIN_ANSWER_CONTENT_TOKENS   = 3     (below this an answer is "vague")
    DUP_THRESHOLD               = 0.85  (word-trigram Jaccard at/above which an
                                        answer is a "duplicate")

METHOD NOTES (stated honestly)
    - Content tokens reuse checker.py's tokenizer exactly (retrieval.Tokenizer
      with light stemming + stopword removal), so "content token" means the same
      thing here as in the grounding coverage score.
    - The duplicate signal is a lexical near-dup detector (word-trigram Jaccard),
      the same family the leakage scan uses. It catches verbatim and near-verbatim
      repeats, not paraphrased duplicates; a semantic dedup model would slot in
      behind the same interface.
    - "circular" is deliberately strict (pure subset). It flags the classic
      give-away card whose answer is contained in its own stem; it does not judge
      pedagogy beyond that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from checker import COVERAGE_CUTOFF, CheckResult
from retrieval import Tokenizer

# --- pre-registered before viewing any generator output (D-AI3) ---------------
GROUNDING_CUTOFF = COVERAGE_CUTOFF  # 0.5, reused from the grounding checker
MIN_ANSWER_CONTENT_TOKENS = 3
DUP_THRESHOLD = 0.85

CORRECT_USEFUL = "correct_useful"
WRONG = "wrong"
BAD_TEACHING = "correct_but_bad_teaching"


@dataclass
class QualityResult:
    verdict: str  # CORRECT_USEFUL | WRONG | BAD_TEACHING
    reason: str  # "ok" | "grounding:..." | "vague" | "circular" | "duplicate"
    grounding_passed: bool
    answer_content_tokens: int
    max_dup_jaccard: float
    detail: dict = field(default_factory=dict)

    @property
    def published(self) -> bool:
        return self.verdict == CORRECT_USEFUL


class QualityChecker:
    """Second gate: given a grounding result, decide teaching quality.

    Reuses checker.py's tokenizer (retrieval.Tokenizer) so "content token" is
    defined identically to the grounding coverage score.
    """

    def __init__(
        self,
        min_answer_content_tokens: int = MIN_ANSWER_CONTENT_TOKENS,
        dup_threshold: float = DUP_THRESHOLD,
    ) -> None:
        self.min_answer_content_tokens = min_answer_content_tokens
        self.dup_threshold = dup_threshold
        # Same configuration checker.GroundingChecker uses for coverage.
        self.content_tok = Tokenizer(stem=True, remove_stopwords=True)
        # Raw word tokens (no stemming / no stopword removal) for the near-dup
        # trigram signal, matching the leakage scan's word-ngram convention.
        self.word_tok = Tokenizer(stem=False, remove_stopwords=False)

    def _content(self, text: str) -> set[str]:
        return set(self.content_tok.tokens(text))

    def _word_trigrams(self, text: str) -> set[str]:
        w = self.word_tok.tokens(text)
        if len(w) < 3:
            return {" ".join(w)} if w else set()
        return {" ".join(w[i : i + 3]) for i in range(len(w) - 2)}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _max_dup(self, answer: str, accepted_answers: list[str]) -> tuple[float, str]:
        best, best_prev = 0.0, ""
        a_tri = self._word_trigrams(answer)
        for prev in accepted_answers:
            j = self._jaccard(a_tri, self._word_trigrams(prev))
            if j > best:
                best, best_prev = j, prev
        return best, best_prev

    def classify(
        self,
        stem: str,
        answer: str,
        grounding: CheckResult,
        accepted_answers: list[str],
    ) -> QualityResult:
        """Return the three-way verdict for one candidate.

        `grounding` is the CheckResult from GroundingChecker for this card's
        claim; `accepted_answers` are the answers of cards already published in
        this batch (the duplicate signal is measured only against those).
        """
        ans_tokens = self._content(answer)
        q_tokens = self._content(stem)
        n_ans = len(ans_tokens)
        max_dup, dup_match = self._max_dup(answer, accepted_answers)

        # (1) faithfulness first: an unsupported claim is WRONG, full stop.
        if not grounding.passed:
            reason = "grounding:" + (",".join(grounding.reasons) or "rejected")
            return QualityResult(
                verdict=WRONG,
                reason=reason,
                grounding_passed=False,
                answer_content_tokens=n_ans,
                max_dup_jaccard=round(max_dup, 3),
                detail={
                    "coverage": round(grounding.coverage, 3),
                    "grounding_reasons": list(grounding.reasons),
                },
            )

        # Grounding passed -> judge teaching quality.
        # (2a) vague: too few content tokens to teach anything specific.
        if n_ans < self.min_answer_content_tokens:
            return QualityResult(
                verdict=BAD_TEACHING,
                reason="vague",
                grounding_passed=True,
                answer_content_tokens=n_ans,
                max_dup_jaccard=round(max_dup, 3),
                detail={"content_tokens": sorted(ans_tokens)},
            )

        # (2b) circular: the answer only restates the stem (subset of the question).
        if ans_tokens and ans_tokens <= q_tokens:
            return QualityResult(
                verdict=BAD_TEACHING,
                reason="circular",
                grounding_passed=True,
                answer_content_tokens=n_ans,
                max_dup_jaccard=round(max_dup, 3),
                detail={
                    "answer_tokens": sorted(ans_tokens),
                    "question_tokens": sorted(q_tokens),
                },
            )

        # (2c) duplicate: near-verbatim repeat of an already-accepted answer.
        if max_dup >= self.dup_threshold:
            return QualityResult(
                verdict=BAD_TEACHING,
                reason="duplicate",
                grounding_passed=True,
                answer_content_tokens=n_ans,
                max_dup_jaccard=round(max_dup, 3),
                detail={"duplicate_of": dup_match},
            )

        # (3) grounded, specific, non-circular, non-duplicate.
        return QualityResult(
            verdict=CORRECT_USEFUL,
            reason="ok",
            grounding_passed=True,
            answer_content_tokens=n_ans,
            max_dup_jaccard=round(max_dup, 3),
            detail={"coverage": round(grounding.coverage, 3)},
        )


if __name__ == "__main__":
    from checker import GroundingChecker
    from sources import SourceRef, load_corpus

    corpus = load_corpus()
    checker = GroundingChecker()
    gate = QualityChecker()
    print(
        f"pre-registered: grounding_cutoff={GROUNDING_CUTOFF} "
        f"min_answer_content_tokens={MIN_ANSWER_CONTENT_TOKENS} "
        f"dup_threshold={DUP_THRESHOLD}\n"
    )

    demos = [
        # (label, stem, claim==answer, ref, accepted)
        (
            "useful",
            "How does an enzyme speed up a reaction?",
            "An enzyme lowers the reaction's activation energy without being consumed.",
            SourceRef("src_chapter_metabolism", 1, 1),
            [],
        ),
        (
            "vague",
            "Where does glycolysis take place in the cell?",
            "In the cytoplasm.",
            SourceRef("src_chapter_metabolism", 9, 9),
            [],
        ),
        (
            "circular",
            "In which membrane is the electron transport chain embedded?",
            "The electron transport chain is embedded.",
            SourceRef("src_chapter_metabolism", 15, 15),
            [],
        ),
    ]
    for label, stem, answer, ref, accepted in demos:
        g = checker.check_ref(answer, ref, corpus)
        r = gate.classify(stem, answer, g, accepted)
        print(
            f"  {label:<9} -> verdict={r.verdict:<24} reason={r.reason:<14} "
            f"grounded={r.grounding_passed} ans_tokens={r.answer_content_tokens}"
        )
