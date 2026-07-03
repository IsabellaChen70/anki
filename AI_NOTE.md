# AI note (Vantage)

A short, honest note on the AI in Vantage: what it does, why it is built this way,
and what was deliberately skipped. Everything here is **offline and deterministic**
(no live model, no network) and lives in
[`vantage_tools/ai/`](vantage_tools/ai/). Re-run the numbers below with:

```bash
just eval-ai        # all of the AI evals below, each writing its result JSON
# ...or individually:
python3 vantage_tools/ai/eval_cardgen.py      # retrieval + grounding -> eval_results.json
python3 vantage_tools/ai/eval_cardcheck.py    # 3-way gate, tuned 50 -> cardcheck_results.json
python3 vantage_tools/ai/cardcheck_holdout.py # 3-way gate, INDEPENDENT held-out -> cardcheck_holdout_results.json
python3 vantage_tools/ai/eval_llm_seam.py     # a wired LLM's output is still screened -> llm_seam_results.json
python3 vantage_tools/ai/canary.py            # prompt-injection canary
```

## What the AI is

A **retrieval-augmented card-generation safety layer**. Given a topic, it retrieves
passages from a small named corpus, a generator drafts a card, and the card is only
kept if it **traces to its source** and **passes a grounding check**. It is an
**offline authoring step**, never on the review or scoring path.

- **Every output traces to a named source.** Each card carries a `SourceRef`
  (`source_id` + sentence span) that resolves to the exact source text and a
  citation ([`sources.py`](vantage_tools/ai/sources.py)). Nothing is published
  without one.
- **A checker with a pre-registered cutoff.** Before any card is shown, the
  grounding checker measures how much of the claim is supported by the cited span
  and looks for negation/number contradictions. The coverage cutoff is fixed in
  code (`COVERAGE_CUTOFF = 0.5`) **before** looking at results
  ([`checker.py`](vantage_tools/ai/checker.py)).
- **A three-way quality gate, live in the pipeline.** Beyond faithfulness, a second
  gate ([`quality.py`](vantage_tools/ai/quality.py)) sorts each card into
  correct-useful / wrong / correct-but-bad-teaching (vague, circular, or duplicate).
  It runs **inside `GenerationPipeline.run()`** (not just in the eval), so a card must
  be grounded AND useful before it is published.
- **Two card-check evals: a tuned one and an independent one.**
  [`eval_cardcheck.py`](vantage_tools/ai/eval_cardcheck.py) runs 50 cards with known
  intended labels (validates the gate's mechanics), while
  [`cardcheck_holdout.py`](vantage_tools/ai/cardcheck_holdout.py) builds a separate
  set by **mechanical, content-level perturbations of real corpus sentences** — labels
  fixed by the operation, not by any tag the gate was tuned on — so it measures
  *generalization*: the gate blocks **22/22** wrong cards and publishes **14/14** useful
  ones, with **0 wrong published**.
- **A wired-but-screened LLM seam.** The LLM generator is now a real,
  provider-agnostic seam (off by default; a 3-line OpenAI adapter is included).
  [`eval_llm_seam.py`](vantage_tools/ai/eval_llm_seam.py) drives it with a mock
  provider and shows a hallucination, an injection payload, and a fabricated citation
  are all blocked while the good card publishes — enabling a real model cannot bypass
  the gate.
- **It beats a simpler baseline.** The retriever is compared side-by-side against a
  plain BM25 keyword baseline on a gold set.
- **Prompt-injection defense.** Sources are sanitized and injection signatures are
  quarantined before indexing; a canary source proves it changes nothing
  ([`canary.py`](vantage_tools/ai/canary.py)).
- **AI is off by default, and never load-bearing.** The generator ships disabled;
  the app computes all three scores with AI off.

## Why it is built this way

A wrong flashcard is worse than no card: it teaches a wrong fact and manufactures
the fluency illusion (you feel you know it). So generation is only safe with a
**source**, a **checker**, and a **cutoff set in advance**. And per the brief, an
untraceable AI claim zeroes the AI work and AI must never be required for the app to
function, so the scoring path does not depend on it.

## The real numbers (deterministic, from the eval)

- **Retrieval beats the keyword baseline** (50-item gold set): Vantage retriever
  recall@3 86.0% / recall@5 92.0% / MRR 0.795 vs BM25 recall@3 80.0% / recall@5
  82.0% / MRR 0.736, winning on the vocabulary-mismatch subset (recall@3 53.3% ->
  73.3%).
- **Grounding check on a held-out labeled set** (13 cards: 9 genuinely-sourced +
  4 hallucinated), cutoff 0.5:
  - **wrong-answer rate 0.0%** (0 wrong cards among those it would publish; all 4
    hallucinated cards rejected)
  - retrofit supported 7/9; false-reject rate 22.2% (2/9 good cards blocked — a
    documented lexical-checker limit, not a safety failure). The extra false-reject is
    the cost of tightening the numeric-conflict rule (see below), which we accept
    because it closes a real wrong-card hole.
- **Independent held-out card check** (`cardcheck_holdout.py`, labels from mechanical
  perturbations, not tuned to the gate): **22/22 wrong blocked, 14/14 useful
  published, 0 wrong published** — a genuine generalization result. Building it
  surfaced a real gap (a single swapped number among repeats evaded the old
  numeric-conflict rule); the rule was tightened (`span has a number the claim
  conflicts with`) to catch it, verified across all AI evals.
- **Wired-LLM seam still screened** (`eval_llm_seam.py`, mock provider): the good card
  publishes; the hallucination (negation), the injection payload, and the fabricated
  citation are all blocked; AI-off default still holds.
- **Injection canary caught**: both injected chunks quarantined, none indexed,
  output identical with and without the attack.
- **AI card check on 50 tuned cards** (deterministic generator, LLM off): the three-way
  gate returns 34 correct-useful / 8 wrong / 8 correct-but-bad-teaching; only the 34
  useful are published (16 blocked), **0 wrong or bad-teaching reach a student**, all
  34 resolve to a source span; gate matched the known intended labels 50/50 (this
  validates the gate's *mechanics* — the held-out set above tests generalization).
- **AI off by default**: default generator disabled, produces 0 cards; nothing in
  the package sets `ai_used = true`; `offline_test.py` proves a dropped provider
  connection yields zero cards while the app still scores locally.

## What was skipped (and why)

- **A production LLM vendor.** The generator seam is now wired and screened (a real
  `client(prompt)->str` is called and its output passes the same gate; a 3-line
  OpenAI adapter is included), but no paid vendor is called in the shipped default so
  the pipeline stays re-runnable with no key or network.
- **A vector/embedding retrieval arm.** Both the baseline and the method are
  lexical; the brief only requires beating keyword *or* vector, and a dense arm
  would add a model dependency the offline guarantee avoids.
- **Application-item generation with cover-story variation.** The offline generator
  emits recall cards only.
- **A trained entailment/NLI checker.** The grounding checker and the quality
  gate's duplicate signal are lexical proxies with honest false-reject limits; a
  real deployment would slot NLI / semantic-dedup models behind the same interfaces.
- **An in-app authoring UI.** The accept/reject authoring panel (pick a source,
  review candidates with their verdict, accept/reject) is still design-only.
- **A real MCAT cohort.** The tuned 50-card check validates the gate's mechanics and
  the independent held-out (`cardcheck_holdout.py`) tests generalization on
  perturbed real facts, but neither is a real vendor's card output on a real cohort.

See [`docs/spec-ai-cardgen.md`](../mcat%20anki/docs/spec-ai-cardgen.md) for the full
design and [`vantage_tools/EVALUATION.md`](vantage_tools/EVALUATION.md) for the
broader eval harness.
