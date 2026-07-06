# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Source-traced explanations for missed reasoning questions, gated by the SAME
card gate (spec-ai-cardgen.md sec 5).

The feature offers a short explanation of the correct answer when a student misses
a reasoning question, but ONLY if that explanation clears the exact pipeline a
generated card must clear: a SourceRef is required, the claim must pass the
grounding checker, and it must pass the three-way teaching-quality gate. If it fails
any stage it is not shown at all (honesty-first: never an ungrounded or unverified
explanation).

What is proven here, end to end, offline (no network, no model):
  1. a grounded, cited, useful explanation PASSES and is placed in the shown set,
     with its source citation and locator intact;
  2. nothing bypasses the gate -- an ungrounded (negated) explanation, a vague one,
     and one with a missing/invalid SourceRef are all BLOCKED and never shown;
  3. the gate is REUSED, not forked: the explanation path calls
     cardgen.GenerationPipeline.gate_candidate, and its cutoff/thresholds are the
     ones from checker.py / quality.py;
  4. parity + injection: render.py injects ONLY the gated set into BOTH the desktop
     body and the bundled mobile page, so a blocked explanation reaches neither.

The vantage_tools/ai pipeline uses bare imports among its modules, so its directory
is placed on sys.path (as cardgen_bridge does at runtime) before importing it.
render.py is pure at import time and is loaded by path, like the sibling tests.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[2]
_AI = _REPO / "vantage_tools" / "ai"

if str(_AI) not in sys.path:
    sys.path.insert(0, str(_AI))

import cardgen  # noqa: E402  (imported after sys.path setup)
import checker  # noqa: E402
import explanations as expl  # noqa: E402
import quality  # noqa: E402
from sources import load_corpus  # noqa: E402


def _load_render():
    path = _REPO / "vantage_addon" / "render.py"
    spec = importlib.util.spec_from_file_location("vantage_render_expl", path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vantage_render_expl"] = mod
    spec.loader.exec_module(mod)
    return mod


# A real, grounded, cited explanation (the same shape as an authored item). Its
# claim only restates what src_catalysis already says, so it should pass.
_PASS_ITEM = {
    "section": "chem_phys",
    "stem": "A catalyst, such as an enzyme, speeds up a reaction mainly by:",
    "explanation": (
        "A catalyst speeds up a reaction by providing an alternative pathway "
        "with a lower activation energy."
    ),
    "source_ref": {"source_id": "src_catalysis", "start": 0, "end": 0},
}

# (a) ungrounded: negates its cited span (claim asserts the catalyst shifts the
# equilibrium; the span says it does not) -> grounding rejects it as WRONG.
_NEGATION_ITEM = {
    "section": "chem_phys",
    "stem": "As a catalyst, carbonic anhydrase changes the reaction's:",
    "explanation": (
        "A catalyst shifts the equilibrium toward products by lowering the "
        "activation energy."
    ),
    "source_ref": {"source_id": "src_catalysis", "start": 2, "end": 2},
}

# (b) grounded but too vague to teach (fewer than the quality gate's minimum
# content tokens) -> BAD_TEACHING.
_VAGUE_ITEM = {
    "section": "chem_phys",
    "stem": "A catalyst, such as an enzyme, speeds up a reaction mainly by:",
    "explanation": "Activation energy.",
    "source_ref": {"source_id": "src_catalysis", "start": 0, "end": 0},
}

# (c) no SourceRef at all -> blocked before any check ("SourceRef required").
_NO_REF_ITEM = {
    "section": "chem_phys",
    "stem": "A catalyst, such as an enzyme, speeds up a reaction mainly by:",
    "explanation": (
        "A catalyst speeds up a reaction by providing an alternative pathway "
        "with a lower activation energy."
    ),
}

# (c') a SourceRef that does not resolve (out-of-range sentence index). Without the
# gate's resolve-guard this would crash the checker; it must be a clean block.
_BAD_REF_ITEM = {
    "section": "chem_phys",
    "stem": "A catalyst, such as an enzyme, speeds up a reaction mainly by:",
    "explanation": (
        "A catalyst speeds up a reaction by providing an alternative pathway "
        "with a lower activation energy."
    ),
    "source_ref": {"source_id": "src_catalysis", "start": 99, "end": 99},
}


def _pipe(corpus=None):
    corpus = corpus or load_corpus()
    return corpus, cardgen.GenerationPipeline.default(corpus)


# --------------------------------------------------------------------------- #
# 1. A grounded, cited, useful explanation passes and is shown
# --------------------------------------------------------------------------- #
def test_grounded_explanation_passes_and_is_shown():
    corpus, pipe = _pipe()
    res = expl.gate_item(_PASS_ITEM, pipe, corpus)
    assert res.published, res.reason
    # grounded above the checker's own cutoff (no new literal introduced here)
    assert res.coverage is not None and res.coverage >= checker.COVERAGE_CUTOFF
    # traceability rides with it: shown text + a real citation + the exact locator
    assert res.text == _PASS_ITEM["explanation"]
    assert res.source and "OpenStax" in res.source
    assert res.locator == "src_catalysis#s0"

    # and it lands in the shown (gated) set the UI reads
    built = expl.build_gated([_PASS_ITEM], corpus)
    shown = built.gated.get("chem_phys", {}).get(_PASS_ITEM["stem"])
    assert shown and shown["text"] == _PASS_ITEM["explanation"]
    assert built.passed_count == 1 and built.blocked_count == 0


# --------------------------------------------------------------------------- #
# 2. Nothing bypasses the gate: ungrounded / vague / no-source are all blocked
#    and never reach the shown set (REGRESSION: red/green protocol).
# --------------------------------------------------------------------------- #
def test_ungrounded_explanation_is_blocked_and_not_shown():
    corpus, pipe = _pipe()
    res = expl.gate_item(_NEGATION_ITEM, pipe, corpus)
    assert not res.published
    assert res.reason.startswith("wrong:grounding")  # the real checker ran
    built = expl.build_gated([_NEGATION_ITEM], corpus)
    assert built.gated == {} and built.blocked_count == 1


def test_vague_explanation_is_blocked_and_not_shown():
    corpus, pipe = _pipe()
    res = expl.gate_item(_VAGUE_ITEM, pipe, corpus)
    assert not res.published
    assert res.reason == "correct_but_bad_teaching:vague"
    assert expl.build_gated([_VAGUE_ITEM], corpus).gated == {}


def test_missing_or_invalid_source_ref_is_blocked_not_crash():
    # SourceRef is REQUIRED: no ref, and an unresolvable ref, both block cleanly
    # (the second would crash the checker without the gate's resolve-guard).
    corpus, pipe = _pipe()
    for item in (_NO_REF_ITEM, _BAD_REF_ITEM):
        res = expl.gate_item(item, pipe, corpus)
        assert not res.published
        assert res.reason == "missing_source_ref"
        assert expl.build_gated([item], corpus).gated == {}


# --------------------------------------------------------------------------- #
# 3. The gate is reused (not forked) and its thresholds come from the pipeline
# --------------------------------------------------------------------------- #
def test_uses_shared_gate_and_pipeline_thresholds():
    # the shared per-candidate gate the card generator also uses
    assert hasattr(cardgen.GenerationPipeline, "gate_candidate")
    # the quality gate reuses the checker's coverage cutoff (one source of truth)
    assert quality.GROUNDING_CUTOFF == checker.COVERAGE_CUTOFF

    # gating the item through explanations == gating the equivalent Candidate
    # directly through the pipeline (proof it is the same code path).
    corpus, pipe = _pipe()
    cand = expl.explanation_candidate(_PASS_ITEM, corpus)
    outcome = pipe.gate_candidate(cand, accepted_answers=[])
    res = expl.gate_item(_PASS_ITEM, pipe, corpus)
    assert outcome.published == res.published is True


# --------------------------------------------------------------------------- #
# 4. The authored, shipped source-map is honest: every item passes the gate
# --------------------------------------------------------------------------- #
def test_all_authored_explanations_pass_the_gate():
    corpus, _ = _pipe()
    items = expl.load_items()
    assert items, "no authored explanation items found"
    built = expl.build_gated(items, corpus)
    assert built.blocked_count == 0, [b for b in built.blocked]
    assert built.passed_count == len(items)
    # every shown explanation resolves to a real, non-empty corpus span
    for item in items:
        ref = expl._source_ref(item)
        assert ref is not None
        assert corpus.resolve(ref).strip()


# --------------------------------------------------------------------------- #
# 5. Parity + injection: render.py injects ONLY the gated set, on desktop + mobile
# --------------------------------------------------------------------------- #
def test_render_injects_gated_explanations_on_desktop_and_mobile():
    render = _load_render()
    body = render.build_body({}, live=True)
    mobile = render.build_mobile_page({})
    for page in (body, mobile):
        assert "window.__VANTAGE_EXPLANATIONS__" in page
        # a known gated explanation (stem + shown text) is present
        assert _PASS_ITEM["stem"] in page
        assert _PASS_ITEM["explanation"] in page
        # a blocked explanation's text is NEVER injected
        assert _NEGATION_ITEM["explanation"] not in page
