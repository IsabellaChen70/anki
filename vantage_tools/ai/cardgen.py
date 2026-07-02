#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Card generation pipeline: retrieve -> generate -> screen -> ground-check -> gate.

AI IS OFF BY DEFAULT. The default pipeline's generator is an `LLMCardGenerator`
whose `enabled` flag is False; calling it raises `GeneratorDisabledError`. The
default `run()` therefore returns zero cards with status "ai_off" and never
touches the network. This mirrors the app contract: pull the plug and the apps
still review and still score (spec-ai-cardgen.md sec 4; PRD 8.7). NOTHING in this
module sets `ai_used=true`; the live scoring path (pylib/anki/vantage) is not
imported here and is unaffected.

Two generators, both behind the same interface (provider-agnostic, D-AI1):
  - LLMCardGenerator          the pluggable real seam. Disabled by default. A
                              concrete provider is injected as `client`; only
                              then, and only when explicitly enabled, does it run.
                              This is the ONLY place a network call could happen.
  - DeterministicTemplateGenerator  an offline, no-LLM stand-in used by the eval
                              and canary so the whole pipeline is testable with
                              no API. It only ever asserts what a cited chunk
                              already says (grounded by construction).

Every candidate is screened for injected content (defense in depth on top of the
corpus-level quarantine) and then must pass the grounding checker before it is
"published". Failing candidates are blocked with a logged reason.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

from checker import CheckResult, GroundingChecker
from retrieval import Retriever, build_retrievers
from sources import (
    Chunk,
    Corpus,
    SourceRef,
    build_chunks,
    detect_injection,
    load_corpus,
    sanitize_text,
)


class GeneratorDisabledError(RuntimeError):
    """Raised when a disabled generator is asked to produce cards."""


@dataclass
class Candidate:
    kind: str  # "recall" | "application"
    stem: str
    answer: str
    claim: str  # the factual statement the card teaches (what the checker verifies)
    source_ref: SourceRef
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "stem": self.stem,
            "answer": self.answer,
            "claim": self.claim,
            "source_ref": {
                "source_id": self.source_ref.source_id,
                "start": self.source_ref.start,
                "end": self.source_ref.end,
                "locator": self.source_ref.locator(),
            },
            "provenance": self.provenance,
        }


class CardGenerator:
    """Base interface. `enabled` gates all production."""

    name = "base"
    enabled = False

    def propose(
        self, topic_tag: str, chunks: list[Chunk], corpus: Corpus
    ) -> list[Candidate]:
        raise NotImplementedError


class LLMCardGenerator(CardGenerator):
    """Pluggable, provider-agnostic LLM seam. OFF by default.

    `client` is any callable(prompt:str) -> str. It is only invoked when the
    generator is explicitly enabled AND a client is supplied. With no client and
    disabled (the default), any attempt to generate raises.
    """

    name = "llm"

    def __init__(
        self,
        client: Callable[[str], str] | None = None,
        enabled: bool = False,
        model: str = "unset",
    ) -> None:
        self.client = client
        self.enabled = bool(enabled)
        self.model = model

    def propose(
        self, topic_tag: str, chunks: list[Chunk], corpus: Corpus
    ) -> list[Candidate]:
        if not self.enabled:
            raise GeneratorDisabledError(
                "LLM generation is OFF by default. Enable explicitly and inject a "
                "provider client to use it; the app never needs this to score."
            )
        if self.client is None:
            raise GeneratorDisabledError(
                "LLM generator enabled but no provider client injected."
            )
        # A real implementation would build a delimited, data-only prompt from the
        # retrieved chunks, call self.client, and parse a cited card back out. It
        # is intentionally not wired to a vendor here so AI-off stays the default.
        raise NotImplementedError(
            "Wire a concrete provider here; kept unimplemented so no vendor is hard-coded."
        )


class DeterministicTemplateGenerator(CardGenerator):
    """Offline, no-LLM generator. Grounded by construction (asserts only what the
    cited chunk says), so it exercises the full pipeline with no API."""

    name = "offline-template-v1"

    def __init__(self, enabled: bool = False, max_cards: int = 3) -> None:
        self.enabled = bool(enabled)
        self.max_cards = max_cards

    def propose(
        self, topic_tag: str, chunks: list[Chunk], corpus: Corpus
    ) -> list[Candidate]:
        if not self.enabled:
            raise GeneratorDisabledError(
                "Offline generator is disabled; enable it explicitly."
            )
        cands: list[Candidate] = []
        for chunk in chunks[: self.max_cards]:
            claim = chunk.text  # only assert what the source says
            prompt_hash = hashlib.sha256(
                f"{topic_tag}|{chunk.chunk_id}|{claim}".encode()
            ).hexdigest()[:12]
            cands.append(
                Candidate(
                    kind="recall",
                    stem=f"For {topic_tag}: state the key fact from the cited source.",
                    answer=claim,
                    claim=claim,
                    source_ref=chunk.ref(),
                    provenance={
                        "model": self.name,
                        "prompt_hash": prompt_hash,
                        "citation": corpus.citation_for(chunk.source_id),
                        "locator": chunk.ref().locator(),
                    },
                )
            )
        return cands


@dataclass
class GenerationResult:
    status: str  # "ai_off" | "generated"
    published: list[Candidate] = field(default_factory=list)
    blocked: list[tuple[Candidate, str]] = field(default_factory=list)
    topic_tag: str = ""


class GenerationPipeline:
    def __init__(
        self,
        corpus: Corpus,
        chunks: list[Chunk],
        retriever: Retriever,
        checker: GroundingChecker,
        generator: CardGenerator,
    ) -> None:
        self.corpus = corpus
        self.chunks = chunks
        self.retriever = retriever
        self.checker = checker
        self.generator = generator

    @classmethod
    def default(cls, corpus: Corpus | None = None) -> "GenerationPipeline":
        """The app default: AI OFF (LLM generator disabled, no client)."""
        corpus = corpus or load_corpus()
        chunks, _ = build_chunks(corpus)
        retriever = build_retrievers(chunks)["vantage_rag"]
        return cls(
            corpus,
            chunks,
            retriever,
            GroundingChecker(),
            LLMCardGenerator(enabled=False),
        )

    @classmethod
    def offline_demo(
        cls, corpus: Corpus | None = None, max_cards: int = 3
    ) -> "GenerationPipeline":
        """Fully offline pipeline for eval/canary: deterministic generator ON."""
        corpus = corpus or load_corpus()
        chunks, _ = build_chunks(corpus)
        retriever = build_retrievers(chunks)["vantage_rag"]
        gen = DeterministicTemplateGenerator(enabled=True, max_cards=max_cards)
        return cls(corpus, chunks, retriever, GroundingChecker(), gen)

    def _screen(self, cand: Candidate) -> str | None:
        """Output-side injection screen (defense in depth). Returns a reason if
        the candidate must be blocked, else None."""
        for piece in (cand.stem, cand.answer, cand.claim):
            san = sanitize_text(piece)
            if detect_injection(san.clean):
                return "injection_in_output"
            if "pwned" in san.clean.lower() or "evil.example" in san.clean.lower():
                return "payload_in_output"
        return None

    def run(
        self, topic_query: str, topic_tag: str = "", k: int = 3
    ) -> GenerationResult:
        topic_tag = topic_tag or topic_query
        if not self.generator.enabled:
            return GenerationResult(status="ai_off", topic_tag=topic_tag)

        top = [c for c, _ in self.retriever.rank(topic_query, k=k)]
        candidates = self.generator.propose(topic_tag, top, self.corpus)

        published: list[Candidate] = []
        blocked: list[tuple[Candidate, str]] = []
        for cand in candidates:
            screen_reason = self._screen(cand)
            if screen_reason:
                blocked.append((cand, screen_reason))
                continue
            result: CheckResult = self.checker.check_ref(
                cand.claim, cand.source_ref, self.corpus
            )
            if result.passed:
                cand.provenance["checker_coverage"] = round(result.coverage, 3)
                published.append(cand)
            else:
                blocked.append((cand, "grounding:" + ",".join(result.reasons)))
        return GenerationResult(
            status="generated",
            published=published,
            blocked=blocked,
            topic_tag=topic_tag,
        )


def assert_ai_off_default() -> dict:
    """Prove the default pipeline is AI-off and produces no cards without a model."""
    pipe = GenerationPipeline.default()
    facts = {
        "default_generator": pipe.generator.name,
        "default_generator_enabled": pipe.generator.enabled,
    }
    # A disabled generator must refuse to produce.
    raised = False
    try:
        pipe.generator.propose("mcat::chem::acids_bases", pipe.chunks[:1], pipe.corpus)
    except GeneratorDisabledError:
        raised = True
    facts["disabled_generator_raises"] = raised

    # The default run must yield zero cards with status ai_off.
    res = pipe.run("buffers and pH", topic_tag="mcat::chem::acids_bases")
    facts["default_run_status"] = res.status
    facts["default_run_card_count"] = len(res.published)
    facts["ai_off_ok"] = (
        pipe.generator.enabled is False
        and raised
        and res.status == "ai_off"
        and not res.published
    )
    return facts


if __name__ == "__main__":
    print("AI-off contract:", assert_ai_off_default())
    demo = GenerationPipeline.offline_demo(max_cards=2)
    res = demo.run("competitive inhibitor Km Vmax", topic_tag="mcat::biochem::enzymes")
    print(
        f"\noffline demo status={res.status}  published={len(res.published)}  blocked={len(res.blocked)}"
    )
    for c in res.published:
        print(
            f"  PUBLISHED [{c.source_ref.locator()}] cov={c.provenance.get('checker_coverage')}  {c.answer[:64]}"
        )
