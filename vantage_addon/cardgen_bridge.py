# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Desktop-only trigger that connects the coverage map's thin-category signal to
the EXISTING Vantage AI card-generation pipeline (vantage_tools/ai).

This module GENERATES NOTHING and GATES NOTHING itself. It only:

  1. locates the shipped pipeline (vantage_tools/ai) and imports it unchanged;
  2. picks the sanctioned engine for the one AAMC category the student tapped:
       * OFFLINE DEFAULT -- authored, corpus-mapped cards (authored_cards.py) run
         through the pipeline's OWN shared gate. This is what ships (no paid
         vendor, no network), so the button produces real, gated cards out of the
         box.
       * PROVIDER (opt-in) -- if and only if an LLM provider key is configured, the
         pluggable LLM seam runs instead, exactly as make_openai_client documents.
  3. hands back only the cards the pipeline's OWN grounding + quality gate already
     published, with their source traceability intact.

Every safety check (injection screen, grounding checker, three-way quality gate)
lives in vantage_tools/ai and runs on BOTH engines untouched: a card cannot reach
a student without clearing that shared gate (gate_candidate is reused, never
forked), and this module never sets ai_used on the scoring path (the dashboard's
AI-off contract is about scoring, not about a student opting in to make study
cards).

Honesty-first: when the tools are unavailable, or the gate rejects everything, or
a category has no authored source-backed content, the caller is told the truth
("not available" / "no cards passed the check" state). There is no MOCK fallback
and no fabricated success in this path.

Pure at import time (stdlib only) so pylib tests can load it by path without the
add-on's aqt GUI imports; the pipeline import happens lazily inside the calls.
"""

from __future__ import annotations

import hashlib
import os
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# Tunables (UI / desktop-tools knobs, deliberately NOT in ScoringConfig)
# --------------------------------------------------------------------------- #
# These govern the opt-in generation trigger, not any score. ScoringConfig holds
# statistical thresholds for the honest scores (min-n, z-values, band widths);
# putting a card-count or retrieval-depth knob there would pollute the scoring
# core (and its vendored mirror) with a UI concern, so they live here, named.

# How many corpus chunks to retrieve as grounding context for one category tap.
DEFAULT_RETRIEVAL_K = 4
# Cap on how many GATED cards a single tap may add, so one tap can't flood a deck.
MAX_CARDS_PER_TAP = 5

# Env var naming the AI provider key. Its PRESENCE is what flips generation from
# "not set up" to available; without it the trigger stays honestly off.
API_KEY_ENV = "OPENAI_API_KEY"
# Optional override pointing at the vantage_tools/ai directory (for a packaged
# add-on that ships the tools somewhere non-default). Empty/unset -> auto-locate.
AI_DIR_ENV = "VANTAGE_AI_DIR"

# --------------------------------------------------------------------------- #
# Where generated cards land (so they are real, browsable, and count toward
# coverage on the next dashboard refresh)
# --------------------------------------------------------------------------- #
GEN_DECK = "Vantage Generated"
# Marks a card as AI-generated (for auditing / later bulk review). Not an AAMC
# tag: outline.match_tag ignores it, so it never inflates coverage on its own.
AI_GENERATED_TAG = "vantage::ai_generated"
# Config key holding the content hashes already written, so re-tapping a category
# does not pile up duplicates (mirrors the misses-deck dedup in __init__.py).
GEN_SEEN_CONFIG_KEY = "vantage_gen_seen"

# --------------------------------------------------------------------------- #
# Honest outcome statuses
# --------------------------------------------------------------------------- #
STATUS_GENERATED = "generated"  # the pipeline ran (published may still be empty)
STATUS_NOT_CONFIGURED = "not_configured"  # no provider key -> generation is off
STATUS_UNAVAILABLE = "unavailable"  # the vantage_tools/ai pipeline isn't present
STATUS_ERROR = "error"  # an unexpected failure (surfaced honestly, not hidden)


@dataclass
class GenOutcome:
    """The honest result of one category tap. `published` are ONLY cards that
    cleared the pipeline's grounding + quality gate; `blocked` are the human
    reasons the gate rejected the rest (proof the gate ran, and what it caught)."""

    status: str
    published: list[dict] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    topic_tag: str = ""
    query: str = ""
    message: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def published_count(self) -> int:
        return len(self.published)


# --------------------------------------------------------------------------- #
# Locate + import the shipped pipeline (unchanged)
# --------------------------------------------------------------------------- #
def _ai_dir() -> Optional[Path]:
    """Directory holding the vantage_tools/ai pipeline, or None if not found.

    Honors VANTAGE_AI_DIR, else looks for a sibling `vantage_tools/ai` next to the
    add-on (the dev-repo layout) walking a couple of parents up so it also resolves
    from a checkout where the add-on is nested."""
    override = os.environ.get(AI_DIR_ENV)
    if override:
        p = Path(override)
        return p if (p / "cardgen.py").exists() else None
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        cand = base / "vantage_tools" / "ai"
        if (cand / "cardgen.py").exists():
            return cand
    return None


def _import_pipeline() -> Optional[types.SimpleNamespace]:
    """Import the pipeline modules unchanged and return them as a namespace, or
    None when the tools aren't shipped in this build. The modules use bare imports
    among themselves (e.g. `from checker import ...`), so their directory must be
    on sys.path; we add it once at the front so our modules win any name clash."""
    ai_dir = _ai_dir()
    if ai_dir is None:
        return None
    ai_path = str(ai_dir)
    if ai_path not in sys.path:
        sys.path.insert(0, ai_path)
    try:
        import cardgen
        import checker
        import quality
        import retrieval
        import sources
    except Exception:
        return None
    return types.SimpleNamespace(
        cardgen=cardgen,
        checker=checker,
        quality=quality,
        retrieval=retrieval,
        sources=sources,
    )


# --------------------------------------------------------------------------- #
# Category -> generation inputs
# --------------------------------------------------------------------------- #
def category_query(concept_name: str, extra_terms: Optional[list[str]] = None) -> str:
    """The retrieval query for a category: its name plus its topic/alias terms, so
    the retriever surfaces the corpus chunks nearest that content area."""
    terms = [concept_name] + [t for t in (extra_terms or []) if t]
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        t = str(t).replace("_", " ").strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
    return " ".join(out)


def category_coverage_tag(section: str, concept_id: str) -> str:
    """The AAMC tag a generated card carries so it COUNTS toward coverage: the
    same `mcat::<section>::<cid>` shape the shipped decks use, which
    outline.match_tag maps back to the concept id (its coverage bucket) and which
    the Rust interleaver buckets on. `<cid>` is a token in the tag, so a card is
    scored for exactly the category it was generated for."""
    return f"mcat::{section}::{concept_id}"


# --------------------------------------------------------------------------- #
# Provider seam (OFF unless configured)
# --------------------------------------------------------------------------- #
def configured_client(
    mod: types.SimpleNamespace,
) -> tuple[Optional[Callable[[str], str]], bool, str]:
    """Return (client, enabled, detail). The LLM seam is enabled ONLY when a
    provider key is present AND the provider adapter imports; otherwise generation
    stays honestly off. Constructing the client does not hit the network (only the
    later pipeline run would), so this is safe to call offline."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        return None, False, "no_api_key"
    try:
        client = mod.cardgen.make_openai_client(api_key=key)
    except Exception:
        # provider package not installed / adapter failed -> stay off, honestly
        return None, False, "provider_unavailable"
    return client, True, "ok"


# --------------------------------------------------------------------------- #
# Generate for one thin category (calls the pipeline UNCHANGED)
# --------------------------------------------------------------------------- #
def generate_for_category(
    concept_id: str,
    concept_name: str,
    section: str,
    extra_terms: Optional[list[str]] = None,
    *,
    client: Optional[Callable[[str], str]] = None,
    enabled: Optional[bool] = None,
    k: int = DEFAULT_RETRIEVAL_K,
    max_cards: int = MAX_CARDS_PER_TAP,
    corpus=None,
) -> GenOutcome:
    """Run the EXISTING generation pipeline scoped to one AAMC category and return
    only the cards its own grounding + quality gate published.

    Two engines, ONE shared gate. When an LLM provider is configured (or a client
    is injected, as tests do to stub the seam with no network) the pluggable LLM
    path runs. With NO provider (the shipped default) it falls back to the offline,
    deterministic authored engine (authored_cards) -- so the button produces real,
    gated cards out of the box, never a fabricated success and never a live model.
    Either way every candidate clears the same screen + grounding + quality gate.
    """
    mod = _import_pipeline()
    if mod is None:
        return GenOutcome(
            status=STATUS_UNAVAILABLE,
            message="Card generation isn't available in this build.",
            detail={"reason": "pipeline_not_found"},
        )

    query = category_query(concept_name, extra_terms)
    # A label for the candidate/prompt (not a coverage tag): identifies the
    # category the batch was generated for, kept distinct from the Anki tag.
    topic_tag = f"mcat::vantage::{str(concept_id).lower()}"

    # Resolve the provider seam. An injected client (tests) is always respected;
    # otherwise it comes from the environment. With NO provider configured (the
    # shipped default) generation is not off: it falls back to the offline,
    # deterministic authored engine below, so the button still produces real,
    # gated cards without any live/paid model (never a fabricated success).
    if client is None:
        client, enabled, _detail = configured_client(mod)
    elif enabled is None:
        enabled = True

    try:
        corpus = corpus or mod.sources.load_corpus()
        if client is not None and enabled:
            # Provider path (opt-in): the untrusted LLM output still flows through
            # GroundingChecker + QualityChecker inside GenerationPipeline.run, so
            # nothing bypasses gating (see make_openai_client's docstring).
            chunks, _ = mod.sources.build_chunks(corpus)
            retriever = mod.retrieval.build_retrievers(chunks)["vantage_rag"]
            generator = mod.cardgen.LLMCardGenerator(
                client=client, enabled=True, model="vantage-category"
            )
            pipe = mod.cardgen.GenerationPipeline(
                corpus,
                chunks,
                retriever,
                mod.checker.GroundingChecker(),
                generator,
                mod.quality.QualityChecker(),
            )
            result = pipe.run(query, topic_tag=topic_tag, k=k)
            published_cands = list(result.published)
            blocked_pairs = list(result.blocked)
            engine = "llm"
        else:
            # Offline default path: authored, corpus-mapped cards scoped to THIS
            # category, run through the SAME shared gate (gate_candidate) via
            # authored_cards. No network, no model. A category with no authored
            # source-backed card publishes nothing (honest empty), never a fake.
            import authored_cards

            pipe = mod.cardgen.GenerationPipeline.default(corpus)
            published_cands, blocked_pairs = authored_cards.cards_for_concept(
                concept_id, corpus, pipe
            )
            engine = "offline_authored"
    except Exception as exc:  # never hide a real failure behind a fake success
        return GenOutcome(
            status=STATUS_ERROR,
            topic_tag=topic_tag,
            query=query,
            message="Something went wrong while generating cards.",
            detail={"error": repr(exc)},
        )

    published = [c.to_dict() for c in published_cands][:max_cards]
    blocked = [reason for _cand, reason in blocked_pairs]
    return GenOutcome(
        status=STATUS_GENERATED,
        published=published,
        blocked=blocked,
        topic_tag=topic_tag,
        query=query,
        message="",
        detail={"engine": engine, "blocked_count": len(blocked_pairs)},
    )


# --------------------------------------------------------------------------- #
# Write the gated cards into the student's collection
# --------------------------------------------------------------------------- #
def _card_dedup_key(concept_id: str, published: dict) -> str:
    """Stable hash of (category, claim, source locator) so re-tapping a category
    doesn't duplicate a card already added."""
    claim = published.get("claim") or published.get("answer") or ""
    locator = (published.get("source_ref") or {}).get("locator") or ""
    raw = f"{concept_id}|{claim}|{locator}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _card_back(published: dict) -> str:
    """The card back: the answer plus a visible source line, so traceability rides
    with the card (honesty-first). Both the citation and the exact locator come
    from the pipeline's provenance -- we never invent a source."""
    answer = str(published.get("answer") or "").strip()
    prov = published.get("provenance") or {}
    locator = (
        (published.get("source_ref") or {}).get("locator") or prov.get("locator") or ""
    )
    citation = prov.get("citation") or ""
    src_bits = " ".join(
        b for b in [citation, f"({locator})" if locator else ""] if b
    ).strip()
    if src_bits:
        return f"{answer}<br><br><small>Source: {src_bits}</small>"
    return answer


def write_generated_cards(
    col,
    concept_id: str,
    section: str,
    published: list[dict],
    deck_name: str = GEN_DECK,
) -> int:
    """Write ONLY the gated cards to a real deck, tagged so they count toward the
    category's coverage on the next refresh. Returns how many new cards were added.

    Nothing ungated can reach here: `published` is exactly the pipeline's gate
    output. Deduped by content so a second tap on the same category is a no-op for
    cards already present."""
    if not published:
        return 0
    seen = col.get_config(GEN_SEEN_CONFIG_KEY, [])
    if not isinstance(seen, list):
        seen = []
    seen_set = set(seen)
    coverage_tag = category_coverage_tag(section, concept_id)
    made = 0
    try:
        model = col.models.by_name("Basic")
        if model is None:
            return 0
        deck_id = col.decks.id(deck_name)
    except Exception:
        return 0
    for card in published:
        key = _card_dedup_key(concept_id, card)
        if key in seen_set:
            continue
        stem = str(card.get("stem") or "").strip()
        if not stem:
            continue
        # The concept tag counts the card toward the category; a finer topic tag
        # (the authored item's outline alias, when present) counts it toward that
        # specific topic, so the coverage map's "X of Y topics covered" gap shrinks.
        tags = [AI_GENERATED_TAG, coverage_tag]
        topic_alias = (card.get("provenance") or {}).get("coverage_alias")
        if topic_alias:
            tags.append(f"mcat::{section}::{topic_alias}")
        try:
            note = col.new_note(model)
            note["Front"] = stem
            note["Back"] = _card_back(card)
            note.tags = tags
            col.add_note(note, deck_id)
        except Exception:
            continue
        seen_set.add(key)
        seen.append(key)
        made += 1
    if made:
        col.set_config(GEN_SEEN_CONFIG_KEY, seen)
    return made
