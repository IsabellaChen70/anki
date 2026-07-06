# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Validate the authored reasoning question bank (vantage_addon/web/reasoning_bank.*.json).

This is an honesty gate for the content, not the scoring: every item must be
well formed (a stem, exactly four non-empty choices, an in-range answer, an
explanation), and every science item must be tagged to an AAMC content category
that actually exists in the outline (no orphan concepts). CARS carries no
concept because it is not in the AAMC outline.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "vantage_addon" / "web"
_OUTLINE = _REPO / "pylib" / "anki" / "vantage" / "aamc_outline.json"
_SECTIONS = ("cars", "chem_phys", "bio_biochem", "psych_soc")


def _outline_concepts_by_section() -> dict[str, set[str]]:
    data = json.loads(_OUTLINE.read_text(encoding="utf-8"))
    by_section: dict[str, set[str]] = {}
    for concept in data.get("concepts", []):
        by_section.setdefault(concept["section"], set()).add(concept["id"])
    return by_section


def _bank_files() -> list[tuple[str, Path]]:
    out = []
    for sec in _SECTIONS:
        path = _WEB / f"reasoning_bank.{sec}.json"
        if path.exists():
            out.append((sec, path))
    return out


def test_bank_files_present() -> None:
    present = [sec for sec, _ in _bank_files()]
    assert present, "no reasoning_bank.*.json files found under vantage_addon/web/"


def test_items_are_well_formed() -> None:
    for sec, path in _bank_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("section") == sec, f"{sec}: section field mismatch"
        passages = data.get("passages") or []
        assert passages, f"{sec}: no passages"
        for p in passages:
            paras = p.get("paragraphs")
            assert isinstance(paras, list) and paras, f"{sec}: passage missing paragraphs"
            questions = p.get("questions") or []
            assert questions, f"{sec}: passage with no questions"
            for q in questions:
                stem = q.get("stem")
                assert isinstance(stem, str) and stem.strip(), f"{sec}: empty stem"
                choices = q.get("choices")
                assert isinstance(choices, list) and len(choices) == 4, (
                    f"{sec}: question does not have exactly 4 choices: {stem[:60]}"
                )
                assert all(isinstance(c, str) and c.strip() for c in choices), (
                    f"{sec}: blank choice in: {stem[:60]}"
                )
                answer = q.get("answer")
                assert isinstance(answer, int) and 0 <= answer <= 3, (
                    f"{sec}: answer index out of range in: {stem[:60]}"
                )
                explain = q.get("explain")
                assert isinstance(explain, str) and explain.strip(), (
                    f"{sec}: missing explanation in: {stem[:60]}"
                )


def test_science_questions_tag_real_concepts() -> None:
    by_section = _outline_concepts_by_section()
    for sec, path in _bank_files():
        if sec == "cars":
            continue
        valid = by_section.get(sec, set())
        assert valid, f"outline has no concepts for {sec}"
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data["passages"]:
            for q in p["questions"]:
                cid = q.get("concept")
                assert cid, f"{sec}: science question missing concept: {q['stem'][:60]}"
                assert cid in valid, (
                    f"{sec}: concept {cid!r} is not an AAMC content category in the outline"
                )


# The four AAMC Scientific Inquiry and Reasoning Skills, mirror of scoring.SKILLS.
# Kept as a literal so the content test does not import the scoring package.
_VALID_SKILLS = {"concepts", "reasoning", "research", "data"}


def test_skill_tags_are_valid_sirs_skills() -> None:
    """The second miss axis. `skill` is optional (tagging is an ongoing pass), but
    any value present must be one of the four AAMC SIRS ids, and CARS items carry
    none (the SIRS describe the science sections; CARS is never modeled)."""
    for sec, path in _bank_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data["passages"]:
            for q in p["questions"]:
                skill = q.get("skill")
                if skill is None:
                    continue
                assert skill in _VALID_SKILLS, (
                    f"{sec}: skill {skill!r} is not a valid SIRS id "
                    f"({sorted(_VALID_SKILLS)}): {q['stem'][:60]}"
                )
                assert sec != "cars", (
                    f"cars item carries a SIRS skill but CARS is not modeled: {q['stem'][:60]}"
                )
