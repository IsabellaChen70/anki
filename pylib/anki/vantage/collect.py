# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) — collection adapter for the scoring layer.

Turns a live Anki `Collection` into the inputs the pure scoring core needs:

* memory: real per-card FSRS retrievability `R` via Anki's own
  `extract_fsrs_retrievability` SQLite function (the same one the browser
  "Retrievability" column and review ordering use) — never reimplemented.
* coverage: card tags -> AAMC concepts -> weighted coverage (D11).
* readiness gate: count of graded reviews from the revlog (D10).
* performance: application-item outcomes as real Anki cards + revlog. Each answered
  reasoning question is a suspended "anchor" card and each attempt is a revlog row,
  so the correct/incorrect signal that drives Performance + Readiness syncs and
  merges across devices for free (no last-writer-wins clobber). The remaining
  metacognition the revlog can't carry (confidence, miss reason) is written to a
  PER-DEVICE config key so two devices practicing offline don't clobber each other
  on sync; reads merge every per-device key plus the legacy single-list store.

This module imports Anki and is loaded on demand (not from the package __init__),
so the pure core stays testable without a backend.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from . import scoring
from .outline import Outline
from .scoring import (
    READINESS_SECTIONS,
    SECTIONS,
    Calibration,
    ConceptTransfer,
    ConfidenceCalibration,
    MistakeTaxonomy,
    Pacing,
    ScoreResult,
    ScoringConfig,
    SkillTaxonomy,
    StudyPace,
    Trajectory,
)

if TYPE_CHECKING:
    from anki.collection import Collection

# Legacy / fallback store for application-item outcomes: a list of dicts
# {"section": <str>, "correct": <bool>, "confidence": <str|None>, "reason": <str|None>,
#  "concept": <str|None>, "ms": <float|None>, "revlog_id": <int|None>,
#  "logged": <bool>, "ts": <int>}.
# The correct/incorrect outcome now lives in the revlog (see below); this single
# key is kept for older collections and for a device still writing config only
# (e.g. mobile). New metacognition writes go to a PER-DEVICE key instead (below).
PERF_CONFIG_KEY = "vantage_perf_outcomes"

# Per-device metacognition store (confidence / miss reason / timing the revlog
# can't carry). Each device writes ONLY to its own key, "vantage_perf_outcomes::"
# + <local device id>. Config syncs, but distinct keys never conflict, so two
# devices practicing offline both survive the merge (no last-writer-wins clobber).
# Reads union every per-device key plus the legacy single-list key.
PERF_DEVICE_PREFIX = PERF_CONFIG_KEY + "::"  # + <device id>

# A per-device id that must be LOCAL (never synced), so two devices generate two
# different ids and therefore two different per-device keys. Stored in a small
# sibling file next to the collection file (the profile dir, which sync never
# touches). If there's no writable dir (e.g. an in-memory collection) we fall back
# to a config key seeded once -- that one does sync, so it's best-effort only.
DEVICE_ID_SUFFIX = ".vantage_device_id"
DEVICE_ID_CONFIG_KEY = "vantage_device_id"

# Application-item outcomes as first-class Anki cards + revlog (#7A). Each answered
# reasoning question is anchored by one suspended card in REASONING_DECK, tagged with
# its section and a stable per-question id; each attempt is a real revlog row. Because
# revlog syncs and merges natively (append-only, keyed by a millisecond id), two
# devices practicing offline no longer clobber each other's outcomes on sync.
REASONING_DECK = "Vantage Reasoning"
REASONING_SECTION_TAG = "vantage::reasoning::"  # + <section>
REASONING_QID_TAG = "vantage::rq::"  # + <stable per-question id (stem hash)>
# LinkedCardNIDs mechanism (card-level paraphrase test): a reasoning card may
# carry the AAMC concept it tests, which links it to the recall cards of that same
# concept (they share the concept in the outline). This lets the per-concept
# transfer gap compare a concept's recall vs its reworded-item accuracy.
REASONING_CONCEPT_TAG = "vantage::concept::"  # + <concept id, e.g. 1A>
# The AAMC Scientific Inquiry and Reasoning Skill (SIRS) the item tests, the
# second axis of the miss diagnosis (see scoring.SKILLS). Author-tagged and fixed
# per question, so it travels on the anchor card exactly like the concept tag and
# syncs for free. CARS items carry none (SIRS describe the science sections).
REASONING_SKILL_TAG = "vantage::skill::"  # + <skill id: concepts|reasoning|research|data>

# The student's target exam date, stored as an ISO "YYYY-MM-DD" string.
EXAM_CONFIG_KEY = "vantage_exam_date"

# Target readiness composite (3-section scale) and dated readiness snapshots.
TARGET_CONFIG_KEY = "vantage_target_score"
HISTORY_CONFIG_KEY = "vantage_readiness_history"

# Which MCAT review set the student owns ("kaplan" | "tpr" | "ek"); drives the
# per-subject book named in "Study this next". The UI renders the actual titles.
BOOK_CONFIG_KEY = "vantage_book_set"
BOOK_SETS = ("kaplan", "tpr", "ek")

# The Rust topic-interleaver's config blob (mode / topic_tag_prefix / seed, plus
# the optional per-topic-pair `confusability` list this module populates). Shared
# with rslib (see rslib/.../builder/interleave.rs); the engine only consumes the
# map, this side writes it. Default prefix matches the shipped decks (mcat::...).
INTERLEAVE_CONFIG_KEY = "vantage.interleave"
INTERLEAVE_DEFAULT_PREFIX = "mcat"

# AAMC content category -> the standard MCAT prep-book subject to study it from.
# The common comprehensive sets (Kaplan's 7 books, The Princeton Review) are
# organized by these subjects, so this points a student at the right book.
SUBJECT_BY_CONCEPT = {
    "4A": "Physics and Math", "4B": "Physics and Math", "4D": "Physics and Math",
    "4C": "General Chemistry", "4E": "General Chemistry", "5A": "General Chemistry",
    "5B": "General Chemistry", "5E": "General Chemistry",
    "5C": "Organic Chemistry", "5D": "Organic Chemistry",
    "1A": "Biochemistry", "1B": "Biochemistry", "1D": "Biochemistry",
    "1C": "Biology", "2A": "Biology", "2B": "Biology", "2C": "Biology",
    "3A": "Biology", "3B": "Biology",
    "6A": "Behavioral Sciences", "6B": "Behavioral Sciences", "6C": "Behavioral Sciences",
    "7A": "Behavioral Sciences", "7B": "Behavioral Sciences", "7C": "Behavioral Sciences",
    "8A": "Behavioral Sciences", "8B": "Behavioral Sciences", "8C": "Behavioral Sciences",
    "9A": "Behavioral Sciences", "9B": "Behavioral Sciences", "10A": "Behavioral Sciences",
}


@dataclass
class Dashboard:
    memory: ScoreResult
    performance: ScoreResult
    readiness: ScoreResult
    coverage: float
    coverage_by_section: dict[str, float]
    outline_version: str
    n_reviews: int
    n_cards_seen: int
    best_next: Optional[dict] = None
    next_topics: list = field(default_factory=list)
    topic_gaps: list = field(default_factory=list)  # areas with the most topics left
    # per science section: list of 1/0 application-item outcomes. A read-only
    # aggregate the weak-spot quick jump reads to pick the lowest-accuracy section;
    # never a modeled score (the give-up rule still governs any shown number).
    section_outcomes: dict = field(default_factory=dict)
    # Display-only twin of section_outcomes that ALSO includes cars, so the CARS
    # section card can show its reasoning accuracy. Feeds NO score.
    section_reason: dict = field(default_factory=dict)
    # Per science section: mean FSRS recall R (0..1). The SAME memory signal the
    # global Memory score reads, exposed per section so the Practice tab's per-section
    # Flashcards bar shows real recall instead of a maturity fraction. Read-only
    # display, feeds NO score; rounded to 3 decimals to match the mobile JS port.
    section_recall: dict = field(default_factory=dict)
    topic_coverage: float = 0.0  # depth-aware (topic-grain) coverage, for display
    topic_coverage_by_section: dict = field(default_factory=dict)
    book_set: str = "kaplan"  # which prep-book set to name in "Study this next"
    updated_ts: int = 0
    ai_used: bool = False  # the scoring path never calls a model (D12)
    transfer: dict = field(default_factory=dict)  # per-section paraphrase test
    # per-concept paraphrase test: the worst "fluency illusion" concepts first
    fluency_items: list[ConceptTransfer] = field(default_factory=list)
    study_plan: dict = field(default_factory=dict)  # adaptive study vs practice
    calibration: Optional[Calibration] = None  # predicted-vs-observed reliability
    exam_date: Optional[str] = None  # ISO YYYY-MM-DD, or None
    study_pace: Optional[StudyPace] = None  # days-to-exam + daily targets
    confidence: Optional[ConfidenceCalibration] = None  # how sure vs how right
    mistakes: Optional[MistakeTaxonomy] = None  # how you lose points (why)
    skills: Optional[SkillTaxonomy] = None  # how you lose points (which SIRS skill)
    pacing: Optional[Pacing] = None  # time-per-question vs the section budget
    trajectory: Optional[Trajectory] = None  # projected score at exam day
    extra: dict = field(default_factory=dict)


def _cards_r_and_tags(col: "Collection") -> list[tuple[str, Optional[float]]]:
    """Return (tags, R) for every non-suspended card. R is None if no FSRS state."""
    now = int(time.time())
    today = col.sched.today
    next_day_at = col.sched.day_cutoff
    rows = col.db.all(
        """
        select n.tags,
               case when c.data like '%"s"%' then
                   extract_fsrs_retrievability(
                       c.data,
                       case when c.odue != 0 then c.odue else c.due end,
                       c.ivl, ?, ?, ?)
               else null end
        from cards c
        join notes n on c.nid = n.id
        where c.queue != -1
        """,
        today,
        next_day_at,
        now,
    )
    return [(tags or "", r) for tags, r in rows]


def _graded_reviews(col: "Collection") -> int:
    """Number of graded flashcard reviews (Again/Hard/Good/Easy) in the revlog.

    Reasoning-item attempts (#7A) also live in the revlog, but they're excluded
    here so this stays a pure count of flashcard study, which is what the
    memory/readiness give-up gate is measuring."""
    return (
        col.db.scalar(
            "select count() from revlog where ease between 1 and 4 "
            "and cid not in ("
            " select c.id from cards c join notes n on c.nid = n.id"
            " where n.tags like ?)",
            f"%{REASONING_SECTION_TAG}%",
        )
        or 0
    )


def _dicts(raw) -> list[dict]:
    """Config is user-writable and synced, so keep only dict entries: one bad
    value (a stray string/None) must not crash the whole dashboard."""
    if not isinstance(raw, list):
        return []
    return [o for o in raw if isinstance(o, dict)]


def _perf_outcomes(col: "Collection") -> list[dict]:
    """The legacy single-list metacognition store (older builds / mobile)."""
    return _dicts(col.get_config(PERF_CONFIG_KEY, []))


def _all_perf_config(col: "Collection") -> list[dict]:
    """Every config-stored metacognition record, merged across the legacy single
    key and ALL per-device keys. Distinct per-device keys never clobber on sync,
    so both devices' confidence / miss-reason notes survive here. This does not
    double-count with the revlog: outcomes come from the revlog and these records
    only enrich them by revlog id (see _merged_outcomes); each record lives under
    exactly one key, so it is read once."""
    out = list(_perf_outcomes(col))  # legacy single key
    try:
        allc = col.all_config()
    except Exception:
        allc = {}
    if isinstance(allc, dict):
        # sorted for a deterministic merge order across devices
        for key in sorted(k for k in allc if isinstance(k, str)):
            if key.startswith(PERF_DEVICE_PREFIX):
                out.extend(_dicts(allc.get(key)))
    return out


def _device_id(col: "Collection") -> str:
    """A stable, LOCAL (never synced) id for this device. Lives in a sibling file
    next to the collection (the profile dir, which sync doesn't touch), so a second
    device gets a different id -> a different per-device config key -> no clobber.
    Falls back to a once-seeded config key only when there is no writable dir."""
    path = getattr(col, "path", None)
    if isinstance(path, str) and path and path != ":memory:":
        idfile = path + DEVICE_ID_SUFFIX
        try:
            if os.path.exists(idfile):
                with open(idfile, encoding="utf-8") as fh:
                    did = fh.read().strip()
                if did:
                    return did
            did = uuid.uuid4().hex
            with open(idfile, "w", encoding="utf-8") as fh:
                fh.write(did)
            return did
        except OSError:
            pass
    did = col.get_config(DEVICE_ID_CONFIG_KEY, None)
    if not isinstance(did, str) or not did:
        did = uuid.uuid4().hex
        col.set_config(DEVICE_ID_CONFIG_KEY, did)
    return did


def _perf_device_key(col: "Collection") -> str:
    return PERF_DEVICE_PREFIX + _device_id(col)


def _section_from_tags(tags: str) -> Optional[str]:
    """Pull the section key out of a reasoning card's tags (vantage::reasoning::<s>)."""
    for t in tags.split():
        if t.startswith(REASONING_SECTION_TAG):
            return t[len(REASONING_SECTION_TAG) :] or None
    return None


def _concept_from_tags(tags: str) -> Optional[str]:
    """Pull the linked AAMC concept id out of a reasoning card's tags
    (vantage::concept::<cid>), or None if the card isn't concept-linked."""
    for t in tags.split():
        if t.startswith(REASONING_CONCEPT_TAG):
            return t[len(REASONING_CONCEPT_TAG) :] or None
    return None


def _skill_from_tags(tags: str) -> Optional[str]:
    """Pull the SIRS skill id out of a reasoning card's tags
    (vantage::skill::<id>), or None if the item isn't skill-tagged (e.g. CARS)."""
    for t in tags.split():
        if t.startswith(REASONING_SKILL_TAG):
            return t[len(REASONING_SKILL_TAG) :] or None
    return None


def _revlog_outcomes(col: "Collection") -> list[dict]:
    """Reasoning outcomes reconstructed from the revlog: one dict per graded attempt
    on a Vantage Reasoning card. ease >= 2 counts as correct (1 = Again = wrong),
    time is the real milliseconds taken, section comes from the card's tag, and ts
    is the attempt time. These sync/merge across devices for free."""
    rows = col.db.all(
        "select r.id, r.ease, r.time, n.tags "
        "from revlog r join cards c on r.cid = c.id join notes n on c.nid = n.id "
        "where n.tags like ? and r.ease between 1 and 4",
        f"%{REASONING_SECTION_TAG}%",
    )
    out: list[dict] = []
    for rid, ease, ms, tags in rows:
        section = _section_from_tags(tags or "")
        if section is None:
            continue
        out.append(
            {
                "section": section,
                "correct": bool(ease is not None and ease >= 2),
                "concept": _concept_from_tags(tags or ""),
                "skill": _skill_from_tags(tags or ""),
                "ms": float(ms) if ms is not None else None,
                "ts": int(rid) // 1000,
                "revlog_id": int(rid),
            }
        )
    return out


def _has_reasoning_cards(col: "Collection") -> bool:
    """True if any reasoning anchor note exists. A cheap, revlog-free existence
    check (a notes-table tag LIKE that stops at the first hit) that lets the
    expensive reasoning-outcome revlog join+scan be skipped entirely on the common
    early-usage path -- a deck with zero application items. Authoritative: it reads
    the notes table (where the tag actually lives), not the tag registry."""
    return bool(
        col.db.scalar(
            "select 1 from notes where tags like ? limit 1",
            f"%{REASONING_SECTION_TAG}%",
        )
    )


def _merged_outcomes(col: "Collection") -> list[dict]:
    """The outcome list every score reads from. Prefers revlog-backed outcomes
    (sync-safe) and enriches each with the confidence / miss reason / linked
    concept kept in config, matched by revlog id. Config records are merged across
    the legacy key AND every per-device key, so two devices' metacognition both
    survive a two-device offline sync (no clobber). Config records with no matching
    revlog row -- older collections, or a device that still writes config only --
    are kept as-is. Purely additive and no double-count: outcomes come from the
    revlog and each config record enriches by revlog id or, if unmatched, is
    appended exactly once (each record lives under one key)."""
    config = _all_perf_config(col)
    # Skip the full revlog join+LIKE entirely when there are no reasoning anchor
    # cards (the common early-usage case), so an application-item-free deck never
    # pays for that scan (measured ~74 ms @50k / ~165 ms @100k on the bench). The
    # result is identical: no reasoning cards means no revlog-backed outcomes.
    revlog = _revlog_outcomes(col) if _has_reasoning_cards(col) else []
    meta_by_rid = {
        o["revlog_id"]: o for o in config if isinstance(o.get("revlog_id"), int)
    }
    seen_rids = {o["revlog_id"] for o in revlog}
    merged: list[dict] = []
    for ro in revlog:
        meta = meta_by_rid.get(ro["revlog_id"], {})
        merged.append(
            {
                "section": ro["section"],
                "correct": ro["correct"],  # outcome always from the revlog (sync-safe)
                "confidence": meta.get("confidence"),
                "reason": meta.get("reason"),
                # concept from the card's tag; fall back to a config-supplied one
                "concept": ro.get("concept") or meta.get("concept"),
                # SIRS skill, same tag-first-then-config precedence as concept
                "skill": ro.get("skill") or meta.get("skill"),
                "ms": ro["ms"] if ro["ms"] is not None else _as_float(meta.get("ms")),
                "ts": ro["ts"],
                "revlog_id": ro["revlog_id"],
            }
        )
    # keep every config record that isn't already represented by a revlog row
    for o in config:
        if isinstance(o.get("revlog_id"), int) and o.get("revlog_id") in seen_rids:
            continue
        merged.append(o)
    return merged


def _reasoning_qid(stem: str) -> str:
    """Stable per-question id from the question text, so re-practicing the same
    question logs onto the same anchor card instead of piling up duplicates."""
    import hashlib

    return hashlib.md5(stem.encode("utf-8")).hexdigest()[:12]


def ensure_reasoning_card(
    col: "Collection",
    section: str,
    stem: str,
    answer: str,
    explain: str,
    concept: Optional[str] = None,
    skill: Optional[str] = None,
) -> Optional[int]:
    """Find or create the suspended anchor card for one reasoning question. The card
    holds the question text (so it's browsable / first-class) and carries the section
    + stable-id tags the scores read. When `concept` is given (an AAMC concept id),
    it also carries the concept tag that links it to that concept's recall cards for
    the card-level paraphrase test. When `skill` is given (a SIRS skill id), it also
    carries the skill tag that feeds the second axis of the miss diagnosis. Returns
    the card id, or None on failure."""
    qid_tag = f"{REASONING_QID_TAG}{_reasoning_qid(stem)}"
    existing = col.db.list(
        "select c.id from cards c join notes n on c.nid = n.id where n.tags like ?",
        f"%{qid_tag}%",
    )
    if existing:
        return int(existing[0])
    try:
        model = col.models.by_name("Basic")
        if model is None:
            return None
        deck_id = col.decks.id(REASONING_DECK)
        note = col.new_note(model)
        note["Front"] = stem
        note["Back"] = f"{answer}<br><br>{explain}" if answer else (explain or "")
        note.tags = [f"{REASONING_SECTION_TAG}{section}", qid_tag]
        if concept:
            note.tags.append(f"{REASONING_CONCEPT_TAG}{concept}")
        if skill:
            note.tags.append(f"{REASONING_SKILL_TAG}{skill}")
        col.add_note(note, deck_id)
        cids = list(note.card_ids())
        if not cids:
            return None
        # anchors are never studied through the queue -- practice.js serves the
        # content; the card exists only so its attempts live in the (synced) revlog.
        col.sched.suspend_cards(cids)
        return int(cids[0])
    except Exception:
        return None


def log_reasoning_outcome(
    col: "Collection",
    section: str,
    stem: str,
    answer: str,
    explain: str,
    correct: bool,
    ms: Optional[float],
    concept: Optional[str] = None,
    skill: Optional[str] = None,
) -> Optional[int]:
    """Record one reasoning attempt as a real revlog row on its anchor card, so the
    outcome syncs and merges natively. An optional `concept` (AAMC concept id) links
    the item to that concept's recall cards for the card-level paraphrase test; an
    optional `skill` (SIRS skill id) feeds the miss diagnosis' skill axis. Returns
    the revlog id (used to link the confidence / miss reason kept in the per-device
    config), or None if the card couldn't be made."""
    cid = ensure_reasoning_card(col, section, stem, answer, explain, concept, skill)
    if cid is None:
        return None
    ease = 3 if correct else 1  # Good vs Again -> read back as correct/incorrect
    try:
        taken = int(ms) if ms is not None else 0
    except (TypeError, ValueError):
        taken = 0
    taken = max(0, min(taken, 600_000))  # clamp to <= 10 min, like Anki caps time
    rid = int(time.time() * 1000)
    # the revlog id is the primary key (a millisecond timestamp); bump on the rare
    # collision, the same rule Anki's own insert uses.
    while col.db.scalar("select 1 from revlog where id = ?", rid):
        rid += 1
    try:
        col.db.execute(
            "insert into revlog (id, cid, usn, ease, ivl, lastIvl, factor, time, type)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rid,
            cid,
            -1,  # usn -1 => pending sync; the server assigns one on next sync
            ease,
            0,
            0,
            0,
            taken,
            1,  # RevlogReviewKind.Review
        )
    except Exception:
        return None
    return rid


def record_metacognition(
    col: "Collection",
    section: str,
    correct: bool,
    confidence: Optional[str] = None,
    reason: Optional[str] = None,
    ms: Optional[float] = None,
    revlog_id: Optional[int] = None,
    concept: Optional[str] = None,
    mode: Optional[str] = None,
    skill: Optional[str] = None,
) -> str:
    """Append one metacognition record (confidence / miss reason / timing / linked
    concept / SIRS skill) to THIS device's OWN per-device config list. Two devices
    practicing offline therefore write to different keys and never clobber each other
    on sync; reads merge every per-device key (see _all_perf_config). The
    correct/incorrect outcome itself still lives in the revlog (sync-safe); pass its
    `revlog_id` so the read-side merge links this record to that outcome and counts
    it once. Returns the per-device key written to."""
    key = _perf_device_key(col)
    lst = _dicts(col.get_config(key, []))
    lst.append(
        {
            "section": section,
            "correct": bool(correct),
            "confidence": confidence,
            "reason": reason,
            "concept": concept,
            "skill": skill,
            "ms": ms,
            "revlog_id": revlog_id,
            "mode": mode,
        }
    )
    col.set_config(key, lst)
    return key


# --------------------------------------------------------------------------- #
# Second look: a delayed re-test of a missed reasoning QUESTION (extends the
# concept-level flashcard misses deck to the questions themselves)
# --------------------------------------------------------------------------- #
# The DELAYED SCHEDULE reuses the exact primitive the flashcard misses deck uses:
# a REAL Anki card whose due date is assigned by Anki's own scheduler (FSRS via
# col.sched.set_due_date) -- no interval math is reimplemented here. Each missed
# question gets one suspended anchor card in SECOND_LOOK_DECK, tagged with its
# section and the SAME stable qid its reasoning anchor uses; the card's due
# day-number is the re-serve date. The card is suspended so it never leaks into
# the flashcard reviewer -- the practice UI re-serves the real multiple-choice
# question instead of showing a plain flashcard.
SECOND_LOOK_DECK = "Vantage Second Look"
SECOND_LOOK_SECTION_TAG = "vantage::secondlook::"  # + <section>

# The SECOND-ATTEMPT outcome is tracked DISTINCTLY from the original miss, in a
# per-device config list (the same no-clobber pattern as the metacognition store):
# each device writes only to its own key, reads union every key. A record is
# {"qid", "section", "correct", "ts"} and holds ONLY re-attempts -- the original
# miss stays in the reasoning-anchor revlog and the concept-level misses deck,
# untouched. This is what tells "missed then corrected on a second look" apart
# from "missed and still failing".
SECOND_LOOK_CONFIG_KEY = "vantage_second_look"
SECOND_LOOK_DEVICE_PREFIX = SECOND_LOOK_CONFIG_KEY + "::"  # + <device id>


def _tag_suffix(tags: str, prefix: str) -> Optional[str]:
    """The suffix of the first whitespace-token starting with `prefix`, or None."""
    for t in tags.split():
        if t.startswith(prefix):
            return t[len(prefix) :] or None
    return None


def _second_look_device_key(col: "Collection") -> str:
    return SECOND_LOOK_DEVICE_PREFIX + _device_id(col)


def _has_second_look_cards(col: "Collection") -> bool:
    """Cheap existence check so the due/status scan is skipped entirely for a
    student who has never missed a reasoning question (the common early path)."""
    return bool(
        col.db.scalar(
            "select 1 from notes where tags like ? limit 1",
            f"%{SECOND_LOOK_SECTION_TAG}%",
        )
    )


def _reschedule_second_look(col: "Collection", cid: int, delay_days: int) -> None:
    """Set the card due `delay_days` from today with Anki's own scheduler, then
    re-suspend it so it stays out of the flashcard queue. `set_due_date` turns the
    card into a review card and (under FSRS) updates its memory state -- we never
    compute an interval ourselves."""
    try:
        col.sched.set_due_date([cid], str(max(1, int(delay_days))))
    except Exception:
        return
    try:
        col.sched.suspend_cards([cid])
    except Exception:
        pass


def schedule_second_look(
    col: "Collection",
    section: str,
    stem: str,
    answer: str,
    explain: str,
    concept: Optional[str] = None,
    cfg: Optional[ScoringConfig] = None,
) -> Optional[int]:
    """Schedule (or reschedule) a delayed second look at one missed reasoning
    question. Creates/reuses a real suspended card in SECOND_LOOK_DECK and lets
    Anki's own scheduler assign the future due date -- the same real-card + FSRS
    primitive the flashcard misses deck uses. Deduped by the question's stable qid
    (a re-miss just resets the delay). Returns the card id, or None on failure."""
    cfg = cfg or ScoringConfig()
    qid_tag = f"{REASONING_QID_TAG}{_reasoning_qid(stem)}"
    sec_tag = f"{SECOND_LOOK_SECTION_TAG}{section}"
    existing = col.db.list(
        "select c.id from cards c join notes n on c.nid = n.id "
        "where n.tags like ? and n.tags like ?",
        f"%{sec_tag}%",
        f"%{qid_tag}%",
    )
    if existing:
        cid: Optional[int] = int(existing[0])
    else:
        try:
            model = col.models.by_name("Basic")
            if model is None:
                return None
            deck_id = col.decks.id(SECOND_LOOK_DECK)
            note = col.new_note(model)
            note["Front"] = stem
            note["Back"] = f"{answer}<br><br>{explain}" if answer else (explain or "")
            note.tags = [sec_tag, qid_tag]
            if concept:
                note.tags.append(f"{REASONING_CONCEPT_TAG}{concept}")
            col.add_note(note, deck_id)
            cids = list(note.card_ids())
            if not cids:
                return None
            cid = int(cids[0])
        except Exception:
            return None
    _reschedule_second_look(col, cid, cfg.second_look_delay_days)
    return cid


def _second_look_cards(col: "Collection") -> list[dict]:
    """Every second-look anchor card: its stable qid, section, stem (the note's
    Front field), due day-number, and linked concept. Read straight from the
    cards + notes tables (cheap; no Card/Note objects)."""
    if not _has_second_look_cards(col):
        return []
    rows = col.db.all(
        "select c.id, c.due, n.tags, n.flds from cards c join notes n on c.nid = n.id "
        "where n.tags like ?",
        f"%{SECOND_LOOK_SECTION_TAG}%",
    )
    out: list[dict] = []
    for cid, due, tags, flds in rows:
        tags = tags or ""
        section = _tag_suffix(tags, SECOND_LOOK_SECTION_TAG)
        qid = _tag_suffix(tags, REASONING_QID_TAG)
        if section is None or qid is None:
            continue
        # the Front field holds the exact stem the qid was hashed from, so the
        # practice UI can re-serve the real question by matching it in the bank.
        stem = (flds or "").split("\x1f")[0]
        out.append(
            {
                "cid": int(cid),
                "due": int(due) if due is not None else 0,
                "section": section,
                "qid": qid,
                "stem": stem,
                "concept": _concept_from_tags(tags),
            }
        )
    return out


def _all_second_look_records(col: "Collection") -> list[dict]:
    """Every recorded second-attempt outcome, merged across the legacy single key
    and all per-device keys. Distinct keys never clobber on sync, so both devices'
    second-look results survive a two-device offline merge."""
    out: list[dict] = list(_dicts(col.get_config(SECOND_LOOK_CONFIG_KEY, [])))
    try:
        allc = col.all_config()
    except Exception:
        allc = {}
    if isinstance(allc, dict):
        for key in sorted(k for k in allc if isinstance(k, str)):
            if key.startswith(SECOND_LOOK_DEVICE_PREFIX):
                out.extend(_dicts(allc.get(key)))
    return out


def _latest_second_look_by_qid(records: list[dict]) -> dict[str, dict]:
    """The most recent second-look outcome per qid (by ts, then read order), used
    to tell corrected (latest attempt right) from still-failing (latest wrong)."""
    latest: dict[str, dict] = {}
    for idx, r in enumerate(records):
        qid = r.get("qid")
        if not (isinstance(qid, str) and qid):
            continue
        ts = r.get("ts")
        order = (int(ts) if isinstance(ts, (int, float)) else 0, idx)
        prev = latest.get(qid)
        if prev is None or order >= prev["_order"]:
            latest[qid] = {"_order": order, "correct": bool(r.get("correct"))}
    return latest


def record_second_look_outcome(
    col: "Collection",
    qid: str,
    section: str,
    correct: bool,
    ts: Optional[int] = None,
    cfg: Optional[ScoringConfig] = None,
) -> str:
    """Record ONE second-look re-attempt DISTINCTLY from the original miss, in this
    device's own per-device list (no cross-device clobber). A miss reschedules the
    schedule-carrier card for another delayed look; a pass leaves it resolved (the
    due reader excludes qids whose latest outcome is correct). Returns the key
    written to."""
    cfg = cfg or ScoringConfig()
    key = _second_look_device_key(col)
    lst = _dicts(col.get_config(key, []))
    lst.append(
        {
            "qid": qid,
            "section": section,
            "correct": bool(correct),
            "ts": int(ts) if ts is not None else int(time.time()),
        }
    )
    col.set_config(key, lst)
    if not correct:
        for c in _second_look_cards(col):
            if c["qid"] == qid:
                _reschedule_second_look(col, c["cid"], cfg.second_look_delay_days)
                break
    return key


def due_second_looks(
    col: "Collection",
    today: Optional[int] = None,
    cfg: Optional[ScoringConfig] = None,
) -> list[dict]:
    """The second looks whose delayed due date has arrived and that are not yet
    resolved (latest re-attempt still wrong, or never re-attempted). Each item
    carries the section, stable qid, stem, and linked concept so the practice UI
    can re-serve the exact question. `today` defaults to the collection's own day
    number; passing a later value fast-forwards the due filter (used in tests)."""
    cards = _second_look_cards(col)
    if not cards:
        return []
    today = col.sched.today if today is None else int(today)
    latest = _latest_second_look_by_qid(_all_second_look_records(col))
    out: list[dict] = []
    for c in cards:
        if c["due"] > today:
            continue  # scheduled, not yet due
        prev = latest.get(c["qid"])
        if prev is not None and prev["correct"]:
            continue  # already corrected on a second look
        out.append(
            {
                "qid": c["qid"],
                "section": c["section"],
                "stem": c["stem"],
                "concept": c["concept"],
            }
        )
    return out


def second_look_status(col: "Collection", today: Optional[int] = None) -> dict:
    """Honest, un-blended second-look tallies for the UI. Raw counts only (never a
    modeled score): how many questions are due to re-attempt now, how many are
    still waiting on their delay, and -- distinct from the original miss -- how
    many previously-missed questions have since been corrected vs are still failing
    on re-attempt. Abstains to all-zero when there is nothing to show."""
    cards = _second_look_cards(col)
    records = _all_second_look_records(col)
    if not cards and not records:
        return {
            "due": [],
            "due_count": 0,
            "scheduled_count": 0,
            "corrected": 0,
            "still_failing": 0,
            "attempts": 0,
        }
    today = col.sched.today if today is None else int(today)
    latest = _latest_second_look_by_qid(records)
    due: list[dict] = []
    scheduled = 0
    for c in cards:
        prev = latest.get(c["qid"])
        if prev is not None and prev["correct"]:
            continue  # resolved -> neither due nor waiting
        if c["due"] <= today:
            due.append(
                {
                    "qid": c["qid"],
                    "section": c["section"],
                    "stem": c["stem"],
                    "concept": c["concept"],
                }
            )
        else:
            scheduled += 1
    corrected = sum(1 for v in latest.values() if v["correct"])
    still_failing = sum(1 for v in latest.values() if not v["correct"])
    return {
        "due": due,
        "due_count": len(due),
        "scheduled_count": scheduled,
        "corrected": corrected,
        "still_failing": still_failing,
        "attempts": len(records),
    }


def _exam_date(col: "Collection") -> Optional[str]:
    raw = col.get_config(EXAM_CONFIG_KEY, None)
    return raw if isinstance(raw, str) and raw else None


def _book_set(col: "Collection") -> str:
    raw = col.get_config(BOOK_CONFIG_KEY, "kaplan")
    return raw if isinstance(raw, str) and raw in BOOK_SETS else "kaplan"


def _reviews_due(col: "Collection") -> int:
    """Cards due today among mcat-tagged notes: review/day-learn due now, plus any
    intraday learning cards. Scoped to notes tagged mcat:: so this daily flashcard
    load stays consistent with the rest of Vantage (not the whole collection)."""
    today = col.sched.today
    due = col.db.scalar(
        "select count() from cards c join notes n on c.nid = n.id "
        "where n.tags like '%mcat::%' and c.queue in (2, 3) and c.due <= ?",
        today,
    ) or 0
    lrn = col.db.scalar(
        "select count() from cards c join notes n on c.nid = n.id "
        "where n.tags like '%mcat::%' and c.queue = 1"
    ) or 0
    return int(due) + int(lrn)


def _new_cards(col: "Collection") -> int:
    """Cards not yet studied (still in the new queue)."""
    return int(col.db.scalar("select count() from cards where queue = 0") or 0)


def _today_iso() -> str:
    import datetime

    return datetime.date.today().isoformat()


def _as_float(x) -> Optional[float]:
    """Best-effort float; None for a missing or malformed value (config is untrusted)."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def gather(
    col: "Collection",
    cfg: Optional[ScoringConfig] = None,
    outline: Optional[Outline] = None,
) -> Dashboard:
    """Compute the three honest scores + coverage + best-next-topic for a collection."""
    cfg = cfg or ScoringConfig()
    outline = outline or Outline.load()

    # --- memory + coverage + per-concept mastery in one pass over the cards ---
    r_values: list[float] = []
    covered: set[str] = set()
    covered_topics: set[str] = set()  # finer than `covered`; drives topic-level gaps
    concept_r: dict[str, list[float]] = {}
    for tags, r in _cards_r_and_tags(col):
        toks = tags.split()
        card_concepts = {
            cid for cid in (outline.match_tag(t) for t in toks) if cid is not None
        }
        card_topics = {
            tid for tid in (outline.match_tag_topic(t) for t in toks) if tid is not None
        }
        covered |= card_concepts
        covered_topics |= card_topics
        if r is not None:
            r_values.append(r)
            for cid in card_concepts:
                concept_r.setdefault(cid, []).append(r)

    # Some decks encode the topic in the DECK path rather than in tags (e.g. Pankow
    # P/S subdecks like ".../9B::Demographics"). Match those deck names too, via the
    # exact deck_topic_map, so their topics count -- non-destructive (no card edits).
    for d in col.decks.all_names_and_ids():
        tid = outline.deck_topic(d.name)
        if tid is not None and col.db.scalar(
            "select 1 from cards where did = ? limit 1", d.id
        ):
            covered_topics.add(tid)

    # A card that matches a finer TOPIC also covers that topic's parent category,
    # so topic-tagged decks (e.g. MileDown "Cytoskeleton" -> topic 2A.3) count
    # toward category coverage even when the category's own aliases miss the tag.
    for tid in covered_topics:
        t = outline.topic(tid)
        if t is not None:
            covered.add(t.category)

    coverage = outline.weighted_coverage(covered)
    coverage_by_section = outline.coverage_by_section(covered)
    # Depth-aware coverage for DISPLAY (how much of the exam you actually have cards
    # for, at the topic grain). The category-level `coverage` above still drives the
    # readiness breadth gate (touched every area); this finer number is what the UI
    # shows so "% covered" no longer saturates at 100% while topics remain to study.
    topic_coverage = outline.topic_weighted_coverage(covered_topics, covered)
    topic_coverage_by_section = outline.topic_coverage_by_section(covered_topics, covered)
    n_reviews = _graded_reviews(col)

    memory = scoring.memory_score(r_values, coverage, cfg)

    # --- performance (application-item outcomes; abstains until enough exist) ---
    # revlog-backed reasoning outcomes (sync-safe) merged with the config store that
    # still carries confidence / miss reason; additive, so old collections are
    # unaffected.
    perf = _merged_outcomes(col)
    perf_flat = [1 if o.get("correct") else 0 for o in perf]
    performance = scoring.performance_score(perf_flat, coverage, cfg)

    section_outcomes: dict[str, list[int]] = {s: [] for s in SECTIONS}
    for o in perf:
        s = o.get("section")
        if s in section_outcomes:
            section_outcomes[s].append(1 if o.get("correct") else 0)

    # Display-only twin of section_outcomes that ALSO includes cars, so the CARS
    # section card can render its reasoning accuracy. Built from the SAME merged
    # outcomes; it feeds NO score -- section_outcomes above still drives readiness,
    # transfer, and calibration unchanged, and cars already reaches readiness via the
    # IRT section_items path below, so this never double-counts.
    section_reason: dict[str, list[int]] = {s: [] for s in READINESS_SECTIONS}
    for o in perf:
        s = o.get("section")
        if s in section_reason:
            section_reason[s].append(1 if o.get("correct") else 0)

    # per-section memory (mean recall), used both to prior the projection and for
    # the paraphrase test
    section_r: dict[str, list[float]] = {s: [] for s in SECTIONS}
    for cid, rs in concept_r.items():
        concept = outline.concept(cid)
        if concept is not None and concept.section in section_r:
            section_r[concept.section].extend(rs)
    section_recall = {s: (sum(v) / len(v)) for s, v in section_r.items() if v}

    # projection combines reasoning (evidence) with memory (prior): flashcards and
    # reasoning together produce the score. This classic ability->scale path is the
    # honest fallback.
    readiness = scoring.readiness(
        section_outcomes, coverage, coverage_by_section, n_reviews, cfg,
        section_memory=section_recall,
    )
    # IRT latent-ability readiness (the signature). Additive: the IRT score feeds
    # the dashboard only when the flag is on AND it clears every honesty gate
    # (give-up, min items, and per-section test information); otherwise we keep the
    # classic result above. Item difficulty/discrimination come from metadata when
    # present, else a fixed prior.
    if cfg.readiness_use_irt:
        section_items: dict[str, list[scoring.IrtItem]] = {
            s: [] for s in scoring.READINESS_SECTIONS
        }
        for o in perf:
            s = o.get("section")
            if s in section_items:
                b = _as_float(o.get("difficulty"))
                a = _as_float(o.get("discrimination"))
                section_items[s].append(
                    scoring.IrtItem(
                        correct=1 if o.get("correct") else 0,
                        b=b if b is not None else cfg.irt_default_difficulty,
                        a=a if a is not None else cfg.irt_default_discrimination,
                    )
                )
        irt = scoring.irt_readiness(
            section_items, coverage, coverage_by_section, n_reviews, cfg
        )
        if not irt.abstained:
            readiness = irt

    transfer = scoring.transfer_gap(section_recall, section_outcomes, cfg)

    # card-level paraphrase test: per concept (a recall card and its reworded
    # variants share a concept link), recall vs application, worst fluency illusion
    # first. Application outcomes carry the linked concept (from the reasoning card
    # tag); recall is the mean retrievability of that concept's studied cards.
    concept_app: dict[str, list[int]] = {}
    for o in perf:
        cid = o.get("concept")
        if isinstance(cid, str) and cid:
            concept_app.setdefault(cid, []).append(1 if o.get("correct") else 0)
    concept_recall_mean = {
        cid: (sum(rs) / len(rs)) for cid, rs in concept_r.items() if rs
    }
    concept_section: dict[str, str] = {}
    for cid in set(concept_recall_mean) | set(concept_app):
        c = outline.concept(cid)
        if c is not None:
            concept_section[cid] = c.section
    fluency_items = scoring.concept_transfer_gaps(
        concept_recall_mean, concept_app, concept_section, cfg
    )

    # calibration: use section recall (what FSRS says you remember) as the model's
    # predicted P(correct) for each application item in that section, then check it
    # against the observed outcome. A gap is the fluency illusion, made auditable.
    calib_pairs: list[tuple[float, int]] = []
    for s, outs in section_outcomes.items():
        if s in section_recall:
            calib_pairs.extend((section_recall[s], o) for o in outs)
    calib = scoring.calibration(calib_pairs, cfg)

    next_topics = _next_topics(outline, covered, concept_r, covered_topics)
    best_next = next_topics[0] if next_topics else None
    # Only show the finer topic breakdown once some cards actually carry
    # topic-grain tags; a category-only-tagged deck would otherwise read 0/N
    # everywhere, overstating the gap.
    topic_gaps = _topic_gaps(outline, covered_topics) if covered_topics else []
    plan = study_plan(outline, covered, concept_r, cfg)

    # metacognition + diagnosis from the per-item practice records
    confidence = scoring.confidence_calibration(
        [(o.get("confidence"), 1 if o.get("correct") else 0) for o in perf], cfg
    )
    mistakes = scoring.mistake_taxonomy(
        [(o.get("section"), o.get("reason")) for o in perf if not o.get("correct")], cfg
    )
    # Second axis of the same diagnosis: which SIRS skill the misses cluster in.
    # Skill is the question's author-tag (sync-safe, off the anchor card), so this
    # reads it straight off each wrong outcome, same source as the cause above.
    skills = scoring.skill_taxonomy(
        [(o.get("section"), o.get("skill")) for o in perf if not o.get("correct")], cfg
    )

    # pacing coach: time per question vs the real section budget. ms comes from
    # untrusted config, so coerce it and let pacing_coach drop the empty ones.
    pacing = scoring.pacing_coach(
        [(o.get("section"), _as_float(o.get("ms"))) for o in perf], cfg
    )

    # score trajectory: snapshot today's readiness, then project to exam day.
    exam_date = _exam_date(col)
    today_iso = _today_iso()

    # Read stored history defensively (config is user-writable and synced): keep
    # only well-formed {"d": <iso str>, "point": <number>} points so one corrupt
    # entry can't crash the dashboard.
    raw_history = col.get_config(HISTORY_CONFIG_KEY, [])
    history: list[dict] = []
    if isinstance(raw_history, list):
        for h in raw_history:
            if not isinstance(h, dict):
                continue
            d = h.get("d")
            point = _as_float(h.get("point"))
            if isinstance(d, str) and d and point is not None:
                n_raw = h.get("n")
                n_pt = int(n_raw) if isinstance(n_raw, (int, float)) else len(SECTIONS)
                history.append({"d": d, "point": point, "n": n_pt})

    # Record a readiness point that is LIVE and covers at least all three science
    # sections (CARS optional). Tag it with how many sections it spans so a later
    # jump from a 3-section to a 4-section composite (once CARS is scored) never mixes
    # two scales into one misleading slope. A partial/abstained readiness is never
    # written and never feeds the trajectory below.
    modeled = set((readiness.extra or {}).get("modeled_sections", []))
    n_modeled = len(modeled)
    is_full_composite = (
        not readiness.abstained
        and readiness.band is not None
        and set(SECTIONS) <= modeled
    )
    if is_full_composite:
        point = round(readiness.band.point, 1)
        existing = next((h for h in history if h["d"] == today_iso), None)
        # Write at most once per day: only when today's point or its scale changed,
        # so a dashboard refresh doesn't rewrite the collection every render.
        if (
            existing is None
            or existing.get("point") != point
            or existing.get("n") != n_modeled
        ):
            history = [h for h in history if h["d"] != today_iso]
            history.append({"d": today_iso, "point": point, "n": n_modeled})
            col.set_config(HISTORY_CONFIG_KEY, history)

    target = col.get_config(TARGET_CONFIG_KEY, None)
    target = target if isinstance(target, (int, float)) else None
    days_left = None
    if exam_date:
        try:
            import datetime

            days_left = (datetime.date.fromisoformat(exam_date) - datetime.date.fromisoformat(today_iso)).days
        except ValueError:
            days_left = None
    weakest = None
    r_sections = (readiness.extra or {}).get("sections") if not readiness.abstained else None
    if r_sections:
        weakest = min(r_sections, key=lambda s: r_sections[s].point)
    # Only project while readiness is a live full composite; once it drops below
    # the give-up line, stop feeding stale points so the trajectory panel abstains
    # instead of projecting from an out-of-date snapshot. Feed only same-scale
    # snapshots (today's section count), so adding CARS restarts the trend cleanly
    # rather than projecting across two scales.
    traj_history = (
        [h for h in history if h.get("n", len(SECTIONS)) == n_modeled]
        if is_full_composite
        else []
    )
    traj = scoring.trajectory(
        traj_history,
        int(target) if target else None,
        days_left,
        weakest,
        cfg,
        n_sections=n_modeled or len(SECTIONS),
    )

    # study pace: days until the exam + a transparent daily target to get there.
    # The reasoning goal scales to how many AAMC concepts are not yet exam-ready
    # (uncovered or recall below the content-ready line), i.e. real breadth left.
    concepts_to_practice = 0
    for c in outline.concepts:
        rs = concept_r.get(c.id, [])
        recall = (sum(rs) / len(rs)) if rs else 0.0
        if recall < cfg.content_ready_recall:
            concepts_to_practice += 1
    # Reasoning answered *today*, for the practice screen's "X of Y today" counter.
    # Anki's day boundary (col.sched.day_cutoff is the next rollover), so today's
    # window is [cutoff - 1 day, cutoff). Legacy config-only outcomes with no ts are
    # simply not counted toward today (they lack an attempt time).
    day_start = int(col.sched.day_cutoff) - 86400
    reasoning_today = sum(
        1 for o in perf if isinstance(o.get("ts"), int) and o["ts"] >= day_start
    )
    pace = scoring.study_pace(
        exam_date,
        _today_iso(),
        _reviews_due(col),
        _new_cards(col),
        len(perf),
        cfg,
        concepts_to_practice=concepts_to_practice,
        cards_studied=len(r_values),
        reasoning_today=reasoning_today,
    )
    # Exam-countdown-aware DEFAULT split of the daily reasoning goal across
    # sections: heavier, thinner sections get more of it as the exam nears. Uses
    # the same AAMC weights and depth-aware coverage the dashboard already shows,
    # and the same days_left as the trajectory. Only the DEFAULT suggestion; a
    # manual section choice (practice.js) is never seen here. CARS has no outline
    # weight, so it is naturally left out (never fabricated).
    pace.reasoning_focus = scoring.reasoning_focus(
        pace.reasoning_per_day,
        {s: outline.section_weight(s) for s in outline.sections},
        topic_coverage_by_section,
        days_left,
        cfg,
    )

    return Dashboard(
        memory=memory,
        performance=performance,
        readiness=readiness,
        coverage=coverage,
        coverage_by_section=coverage_by_section,
        topic_coverage=topic_coverage,
        topic_coverage_by_section=topic_coverage_by_section,
        outline_version=outline.version,
        n_reviews=n_reviews,
        n_cards_seen=len(r_values),
        best_next=best_next,
        next_topics=next_topics,
        topic_gaps=topic_gaps,
        section_outcomes={s: list(v) for s, v in section_outcomes.items()},
        section_reason={s: list(v) for s, v in section_reason.items()},
        section_recall={s: round(v, 3) for s, v in section_recall.items()},
        book_set=_book_set(col),
        updated_ts=int(time.time()),
        ai_used=False,
        transfer=transfer,
        fluency_items=fluency_items,
        study_plan=plan,
        calibration=calib,
        exam_date=exam_date,
        study_pace=pace,
        confidence=confidence,
        mistakes=mistakes,
        skills=skills,
        pacing=pacing,
        trajectory=traj,
    )


def _next_topics(
    outline: Outline,
    covered: set[str],
    concept_r: dict[str, list[float]],
    covered_topics: Optional[set[str]] = None,
    top: int = 6,
) -> list[dict]:
    """Concepts ranked by weight x (1 - mastery), heaviest-weakest first; uncovered
    concepts count as mastery 0 (D10). Each carries where-to-study info.

    When the outline has topics, `topics` lists the category's still-UNCOVERED
    topic names (heaviest first) so "study next" points at the specific gaps, not
    generic aliases; `topics_covered`/`topics_total` give the finer progress. Falls
    back to category aliases when a category has no authored topics."""
    covered_topics = covered_topics or set()
    items = []
    for c in outline.concepts:
        rs = concept_r.get(c.id, [])
        mastery = (sum(rs) / len(rs)) if rs else 0.0
        if c.topics:
            uncovered = [t for t in c.topics if t.id not in covered_topics]
            # heaviest-first; if every topic is already touched, show the heaviest
            # ones as review targets rather than an empty list.
            shown = sorted(uncovered or list(c.topics), key=lambda t: t.weight, reverse=True)
            topic_names = [t.name for t in shown[:4]]
            topics_total = len(c.topics)
            topics_covered = topics_total - len(uncovered)
        else:
            topic_names = [a.replace("_", " ") for a in c.aliases[:4]]
            topics_total = 0
            topics_covered = 0
        items.append(
            {
                "concept_id": c.id,
                "name": c.name,
                "section": c.section,
                "weight": c.weight,
                "mastery": round(mastery, 3),
                "covered": c.id in covered,
                "priority": round(c.weight * (1.0 - mastery), 3),
                "subject": SUBJECT_BY_CONCEPT.get(c.id, ""),
                "topics": topic_names,
                "topics_covered": topics_covered,
                "topics_total": topics_total,
            }
        )
    items.sort(key=lambda x: x["priority"], reverse=True)
    return items[:top]


def _topic_gaps(
    outline: Outline, covered_topics: set[str], top: int = 6
) -> list[dict]:
    """Content areas with the most still-unstudied topics, for the coverage panel's
    finer breakdown. Ranked by unstudied-topic count times the area's weight, so the
    heaviest gaps lead. Only areas that still have a gap are returned (a fully
    covered area is not a to-do)."""
    coverage = outline.topic_coverage_by_category(covered_topics)
    rows = []
    for c in outline.concepts:
        pair = coverage.get(c.id)
        if not pair:
            continue
        covered_n, total = pair
        if covered_n >= total:
            continue
        rows.append(
            {
                "concept_id": c.id,
                "name": c.name,
                "section": c.section,
                "covered": covered_n,
                "total": total,
                "_rank": (total - covered_n) * (c.weight or 1.0),
            }
        )
    rows.sort(key=lambda r: r["_rank"], reverse=True)
    for r in rows:
        del r["_rank"]
    return rows[:top]


@dataclass
class StudyItem:
    concept_id: str
    name: str
    section: str
    weight: float
    recall: Optional[float]  # None if the concept has no studied cards yet
    priority: float


def study_plan(
    outline: Outline,
    covered: set[str],
    concept_recall: dict[str, list[float]],
    cfg: ScoringConfig,
    top: int = 3,
) -> dict[str, list[StudyItem]]:
    """Adaptive plan: what to study (content) vs what to practice (reasoning).

    Content comes before transfer: you cannot apply a concept you have not
    learned (transfer-appropriate processing, Morris/Bransford/Franks 1977). A
    concept is a content gap to study on flashcards when it is uncovered or its
    recall is below the content-ready line; once recall clears that line it is
    ready to practice on reasoning items. Study gaps are ranked by
    weight x (1 - recall) so the heaviest, weakest topics lead; practice topics
    are ranked by weight.
    """
    study: list[StudyItem] = []
    practice: list[StudyItem] = []
    for c in outline.concepts:
        rs = concept_recall.get(c.id, [])
        recall = (sum(rs) / len(rs)) if rs else None
        if recall is None or recall < cfg.content_ready_recall:
            mastery = recall if recall is not None else 0.0
            study.append(
                StudyItem(
                    c.id, c.name, c.section, c.weight,
                    round(recall, 3) if recall is not None else None,
                    round(c.weight * (1.0 - mastery), 3),
                )
            )
        else:
            practice.append(
                StudyItem(c.id, c.name, c.section, c.weight, round(recall, 3), round(c.weight, 3))
            )
    study.sort(key=lambda x: x.priority, reverse=True)
    practice.sort(key=lambda x: x.priority, reverse=True)
    return {"study": study[:top], "practice": practice[:top]}


def set_perf_outcomes(col: "Collection", outcomes: list[dict]) -> None:
    """Write the interim application-item outcomes store (used for demos/tests)."""
    col.set_config(PERF_CONFIG_KEY, outcomes)


# --------------------------------------------------------------------------- #
# confusability matrix: which topics the student actually confuses, so the Rust
# Mixed interleaver can alternate THOSE pairs more often
# --------------------------------------------------------------------------- #
# Why weight interleaving by confusability at all: interleaving trains
# discrimination, and its benefit is largest for genuinely *confusable*
# categories -- for dissimilar material the effect shrinks toward null
# (Brunmair & Richter, 2019, Psychological Bulletin, "Similarity matters: A
# meta-analysis of interleaved learning and its moderators"). So rather than a
# blind round-robin that treats every topic pair as equally worth separating, we
# spend the interleaver's adjacencies on the topics THIS student mixes up, read
# from their own error data.


def confusability_pairs(
    outcomes: list[dict],
    concept_tags: dict[str, list[str]],
    cfg: ScoringConfig,
) -> list[dict]:
    """Build the per-topic-pair confusability weights the Rust Mixed interleaver
    reads, from the student's OWN misses.

    Signal: within one AAMC section (same content domain, so genuinely similar --
    the case interleaving helps, per Brunmair & Richter 2019), two concepts are
    weighted by how much BOTH are missed on application items. We use the product
    of the two concepts' miss counts as a co-miss proxy (a concept never missed
    contributes nothing), then normalize the pair weights to a 0..1 scale. This is
    a marginal-count proxy for true co-missing, which is the honest best we can do
    without reliable per-session grouping; the engine only uses the *relative*
    ordering of the weights, so the scale itself is immaterial.

    `concept_tags` maps an AAMC concept id to the review-bucket note tags that
    teach it, because the interleaver buckets review cards by note tag; the pairs
    are therefore keyed by those full tags (e.g. "mcat::bio_biochem::1A"), exactly
    the bucket keys the engine groups on. A concept with no such tag has no review
    bucket, so it is never emitted.

    Honesty-first (the give-up rule): returns an EMPTY list -- which the engine
    treats as bit-for-bit identical to the naive round-robin -- unless the error
    data clears the gate: at least `cfg.min_mistakes` missed application items that
    name a concept, and at least two distinct missed-and-taggable concepts sharing
    a section (you need two to have a pair). Deterministic and de-duplicated."""
    miss_by_section: dict[str, dict[str, int]] = {}
    total_missed = 0
    for o in outcomes:
        if o.get("correct"):
            continue
        cid = o.get("concept")
        section = o.get("section")
        if not (isinstance(cid, str) and cid):
            continue
        if not (isinstance(section, str) and section):
            continue
        counts = miss_by_section.setdefault(section, {})
        counts[cid] = counts.get(cid, 0) + 1
        total_missed += 1

    # give-up gate: too little error signal -> abstain to naive interleaving
    if total_missed < cfg.min_mistakes:
        return []

    # raw co-miss strength per within-section concept pair (both must be missed and
    # both must map to a real review bucket, else there is nothing to reorder)
    raw: dict[tuple[str, str], float] = {}
    for counts in miss_by_section.values():
        concepts = sorted(c for c in counts if concept_tags.get(c))
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                a, b = concepts[i], concepts[j]
                raw[(a, b)] = float(counts[a] * counts[b])

    if not raw:
        return []

    max_w = max(raw.values())
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for (a, b), w in raw.items():
        weight = round(w / max_w, 6)
        for ta in concept_tags.get(a, []):
            for tb in concept_tags.get(b, []):
                if ta == tb:
                    continue
                key = (ta, tb) if ta < tb else (tb, ta)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({"topic_a": key[0], "topic_b": key[1], "weight": weight})
    pairs.sort(key=lambda p: (p["topic_a"], p["topic_b"]))
    return pairs


def interleave_priorities(
    outcomes: list[dict],
    concept_tags: dict[str, list[str]],
    cfg: ScoringConfig,
) -> list[dict]:
    """Per-topic study priority for the Rust Mixed interleaver: lead the session
    with the topics the student misses most, so weak areas come up first.

    Same miss signal and give-up gate as `confusability_pairs`: a tag inherits its
    concept's application-item miss count, normalized to 0..1 (the engine only uses
    the relative order, to pick the starting bucket). Returns an EMPTY list below
    the gate, which the engine treats as the historical seed-chosen start.
    Deterministic and de-duplicated."""
    miss: dict[str, int] = {}
    total_missed = 0
    for o in outcomes:
        if o.get("correct"):
            continue
        cid = o.get("concept")
        if not (isinstance(cid, str) and cid):
            continue
        total_missed += 1
        if concept_tags.get(cid):
            miss[cid] = miss.get(cid, 0) + 1

    if total_missed < cfg.min_mistakes or not miss:
        return []

    max_miss = max(miss.values())
    out: list[dict] = []
    seen: set[str] = set()
    for cid in sorted(miss, key=lambda c: (-miss[c], c)):
        weight = round(miss[cid] / max_miss, 6)
        for tag in concept_tags.get(cid, []):
            if tag in seen:
                continue
            seen.add(tag)
            out.append({"topic": tag, "weight": weight})
    return out


def _concept_tags(
    col: "Collection", outline: Outline, prefix: str
) -> dict[str, list[str]]:
    """Map each AAMC concept id to the review-bucket note tags that teach it.

    The interleaver buckets a review card by its first note tag under `<prefix>::`,
    so we take the collection's distinct tags, keep those under the prefix, and map
    each to a concept with the SAME `outline.match_tag` the coverage scan uses
    (so a tag is bucketed here exactly as it is scored there). Deterministic."""
    out: dict[str, list[str]] = {}
    full_prefix = prefix + "::"
    try:
        all_tags = col.tags.all()
    except Exception:
        all_tags = []
    for tag in sorted(set(all_tags)):
        if not (isinstance(tag, str) and tag.startswith(full_prefix)):
            continue
        cid = outline.match_tag(tag)
        if cid is not None:
            out.setdefault(cid, [])
            if tag not in out[cid]:
                out[cid].append(tag)
    return out


def set_interleave_confusability(
    col: "Collection",
    outcomes: Optional[list[dict]] = None,
    outline: Optional[Outline] = None,
    cfg: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Compute the student's confusability map and persist it into the
    `vantage.interleave` config so the Rust Mixed interleaver alternates the topics
    they actually confuse (Brunmair & Richter 2019). Merges into the existing
    config blob so mode / topic_tag_prefix / seed are preserved, and only rewrites
    when the map changes (so a dashboard refresh doesn't dirty the collection every
    render). Additive + honesty-first: an empty map means naive interleaving, which
    the engine reproduces bit-for-bit. Returns the pairs written (or already set)."""
    cfg = cfg or ScoringConfig()
    outline = outline or Outline.load()
    if outcomes is None:
        outcomes = _merged_outcomes(col)

    raw_cfg = col.get_config(INTERLEAVE_CONFIG_KEY, None)
    conf_cfg = dict(raw_cfg) if isinstance(raw_cfg, dict) else {}
    prefix = conf_cfg.get("topic_tag_prefix")
    if not (isinstance(prefix, str) and prefix):
        prefix = INTERLEAVE_DEFAULT_PREFIX

    concept_tags = _concept_tags(col, outline, prefix)
    pairs = confusability_pairs(outcomes, concept_tags, cfg)
    priorities = interleave_priorities(outcomes, concept_tags, cfg)

    existing = conf_cfg.get("confusability")
    existing_norm = existing if isinstance(existing, list) else []
    existing_pri = conf_cfg.get("priorities")
    existing_pri_norm = existing_pri if isinstance(existing_pri, list) else []
    if existing_norm == pairs and existing_pri_norm == priorities:
        return pairs  # unchanged -> don't rewrite (avoids needless sync churn)
    conf_cfg["confusability"] = pairs
    conf_cfg["priorities"] = priorities
    col.set_config(INTERLEAVE_CONFIG_KEY, conf_cfg)
    return pairs
