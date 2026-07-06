#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Source-traced explanations for MISSED reasoning questions, gated by the SAME
pipeline that gates generated cards (spec-ai-cardgen.md sec 5).

When a student misses a reasoning question we may offer a short explanation of the
correct answer. Honesty-first (per the Vantage rules): that explanation is treated
exactly like a generated card. It must carry a SourceRef into the named corpus, it
must pass the grounding checker (the claim traces to the cited span), and it must
pass the three-way teaching-quality gate. If it fails ANY stage it is not shown at
all -- the app never surfaces ungrounded or unverified AI content.

NO NEW GATE. This module builds a `cardgen.Candidate` for each explanation and runs
it through `cardgen.GenerationPipeline.gate_candidate`, the one shared gate the card
generator also uses. There is no forked grounding/quality logic here and no new
statistical threshold: the coverage cutoff and quality thresholds come from
checker.py / quality.py unchanged.

OFFLINE + DETERMINISTIC. Like the offline card generator, the explanation only ever
asserts what a named source already says (grounded by construction) and is shown
with its citation. This is the AI-off default path: no network, no live model. A
real LLM seam would produce the same shape of candidate and pass through the same
gate before anything reached a student.

Inputs / outputs:
  explanation_items.json  (authored)  section + exact question stem + correct choice
                                      + the grounded explanation + its SourceRef.
  explanations.gated.json (generated) ONLY the explanations that passed the gate,
                                      keyed by section then stem, each carrying its
                                      shown text, source citation, and locator. This
                                      is what the web UI injects and reads on a miss.

Run:  python3 vantage_tools/ai/explanations.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from cardgen import Candidate, GenerationPipeline
from sources import Corpus, SourceRef, load_corpus

HERE = Path(__file__).resolve().parent
ITEMS_PATH = HERE / "explanation_items.json"
# The gated output lives beside the reasoning banks so render.py injects it the
# same way (one source, identical on desktop and mobile).
OUT_PATH = HERE.parents[1] / "vantage_addon" / "web" / "explanations.gated.json"

# Provenance marker for a source-grounded, offline explanation (not a live model).
MODEL_NAME = "offline-explanation-v1"


@dataclass
class ExplanationResult:
    """The gate verdict for one candidate explanation."""

    section: str
    stem: str
    published: bool
    reason: str = ""
    text: str = ""
    source: str = ""
    locator: str = ""
    coverage: float | None = None


@dataclass
class GatedExplanations:
    """The build output: the shown (passed) explanations plus an audit of blocks."""

    gated: dict = field(default_factory=dict)  # section -> stem -> {text,source,locator}
    blocked: list = field(default_factory=list)  # [{section, stem, reason}]
    passed_count: int = 0
    blocked_count: int = 0


def _source_ref(item: dict) -> SourceRef | None:
    """The item's SourceRef, or None when it is absent/malformed. A None (or an
    unresolvable) ref makes the gate block the item ("SourceRef required")."""
    raw = item.get("source_ref")
    if not isinstance(raw, dict):
        return None
    try:
        return SourceRef.from_dict(raw)
    except (KeyError, TypeError, ValueError):
        return None


def explanation_candidate(item: dict, corpus: Corpus) -> Candidate:
    """Build a gate Candidate for one explanation. The explanation text is both the
    displayed answer and the claim the grounding checker verifies against the cited
    span (claim == answer, the card-generator convention)."""
    text = str(item.get("explanation", "")).strip()
    ref = _source_ref(item)
    provenance: dict = {"model": MODEL_NAME, "kind": "reasoning_explanation"}
    if ref is not None and ref.source_id in corpus.docs:
        provenance["citation"] = corpus.citation_for(ref.source_id)
        provenance["locator"] = ref.locator()
    return Candidate(
        kind="explanation",
        stem=str(item.get("stem", "")).strip(),
        answer=text,
        claim=text,
        source_ref=ref,
        provenance=provenance,
    )


def gate_item(
    item: dict, pipe: GenerationPipeline, corpus: Corpus
) -> ExplanationResult:
    """Run one explanation through the shared card gate and report the verdict.

    Passed -> the shown text plus its citation/locator/coverage. Blocked -> only the
    reason (nothing to show). `accepted_answers` is intentionally empty: each
    explanation is judged on its own, so the duplicate signal never fires across
    unrelated questions."""
    section = str(item.get("section", "")).strip()
    cand = explanation_candidate(item, corpus)
    outcome = pipe.gate_candidate(cand, accepted_answers=[])
    if not outcome.published:
        return ExplanationResult(
            section=section, stem=cand.stem, published=False, reason=outcome.reason
        )
    return ExplanationResult(
        section=section,
        stem=cand.stem,
        published=True,
        text=cand.answer,
        source=cand.provenance.get("citation", ""),
        locator=cand.provenance.get("locator", ""),
        coverage=(outcome.grounding.coverage if outcome.grounding else None),
    )


def build_gated(items: list[dict], corpus: Corpus | None = None) -> GatedExplanations:
    """Gate every authored explanation and collect ONLY the passers for the UI.

    Blocked explanations are recorded for auditing but never placed in `gated`, so a
    consumer that reads `gated` shows a verified explanation or shows nothing."""
    corpus = corpus or load_corpus()
    # AI-off default pipeline: we use only its shared gate (checker + quality); the
    # generator stays disabled and is never invoked here.
    pipe = GenerationPipeline.default(corpus)
    out = GatedExplanations()
    for item in items:
        res = gate_item(item, pipe, corpus)
        if res.published:
            out.gated.setdefault(res.section, {})[res.stem] = {
                "text": res.text,
                "source": res.source,
                "locator": res.locator,
            }
            out.passed_count += 1
        else:
            out.blocked.append(
                {"section": res.section, "stem": res.stem, "reason": res.reason}
            )
            out.blocked_count += 1
    return out


def load_items(path: Path = ITEMS_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    return list(items or [])


def write_gated(out_path: Path = OUT_PATH) -> GatedExplanations:
    """Author -> gate -> write the UI artifact. Returns the build result."""
    items = load_items()
    built = build_gated(items)
    payload = {
        "about": (
            "Source-traced explanations for missed reasoning questions that PASSED "
            "the shared card gate (SourceRef + grounding + quality). Generated by "
            "vantage_tools/ai/explanations.py; do not hand-edit."
        ),
        "gated": built.gated,
        "meta": {"passed": built.passed_count, "blocked": built.blocked_count},
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return built


def main() -> None:
    built = write_gated()
    total = built.passed_count + built.blocked_count
    print(
        f"explanations gated: {built.passed_count} shown / {total} authored "
        f"({built.blocked_count} blocked)"
    )
    for sec, by_stem in sorted(built.gated.items()):
        print(f"  {sec}: {len(by_stem)} shown")
    for b in built.blocked:
        print(f"  BLOCKED [{b['section']}] {b['reason']}: {b['stem'][:60]}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
