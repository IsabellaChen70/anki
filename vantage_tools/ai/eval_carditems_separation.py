#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Contamination guard for the offline authored cards (plan item P1).

WHY THIS EXISTS
    `vantage_tools/ai/card_items.json` holds the offline generator's authored,
    corpus-grounded cards. Those cards deliberately teach the same corpus facts the
    retrieval gold set probes, so their stems/spans OVERLAP `gold_set.json`. That
    overlap is only harmless if the authored cards are NEVER an input to a scored
    eval. This module proves exactly that, in two parts:

    [1a] THE REAL GUARD (a PASSING invariant): an AST/import scan asserting that no
         eval / measurement module reads `card_items.json` -- neither by importing
         `authored_cards` (its only loader) nor by referencing the file by name.
         This is what guarantees the authored cards can never contaminate an eval
         score. Mirrors eval_cardgen.py's AST `ai_used` source scan (comments and
         docstrings do not count).

    [1b] HONEST INFORMATIONAL REPORTING (NOT an assertion): the card_items stems /
         answers that are verbatim/near-dups of a `gold_set.json` QUESTION (at the
         pre-registered 0.80 near-dup cutoff, same method as leakage_check.py), and
         the card_items whose cited SOURCE SPAN overlaps a gold item's span. This
         reuse is REAL and EXPECTED and is labeled as such -- it is NOT a leak,
         because [1a] proves card_items is not an eval input.

    Only `authored_cards.py` (the generator) and this checker read card_items.json.

Re-run (stdlib only; no venv / no network / deterministic):
    python3 vantage_tools/ai/eval_carditems_separation.py
Writes vantage_tools/ai/carditems_separation_results.json ; exit 0 = guard PASS
(no eval reads card_items.json), 1 = an eval module reads it.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))  # vantage_tools/ai
TOOLS = os.path.dirname(HERE)  # vantage_tools
CARD_ITEMS = os.path.join(HERE, "card_items.json")
GOLD = os.path.join(HERE, "gold_set.json")
RESULTS_PATH = os.path.join(HERE, "carditems_separation_results.json")

# The ONLY module allowed to read card_items.json (the offline authored generator).
# This checker reads it too, for the informational overlap below; both are excluded
# from the scanned eval set.
ALLOWED_READER = "ai/authored_cards.py"

# Eval / measurement modules that must NEVER read card_items.json, so the authored
# cards can never enter a scored eval. Paths are relative to vantage_tools/.
EVAL_MODULES = [
    "ai/eval_cardgen.py",
    "ai/eval_cardcheck.py",
    "ai/cardcheck_holdout.py",
    "ai/eval_realtext_grounding.py",
    "ai/eval_experiment_design.py",
    "ai/eval_llm_seam.py",
    "ai/canary.py",
    "ai/chapter_cardgen.py",
    "ai/cardgen.py",
    "ai/checker.py",
    "ai/quality.py",
    "ai/retrieval.py",
    "ai/sources.py",
    "leakage_check.py",
    "evaluate_memory.py",
    "evaluate_performance.py",
    "evaluate_paraphrase.py",
    "ablation_interleave.py",
    "score_mapping.py",
    "scoring_parity_test.py",
]

# Same pre-registered near-dup cutoff as leakage_check.py.
LEAK_CUTOFF = 0.80


# --------------------------------------------------------------------------- #
# [1a] AST / import scan  (the real guard)
# --------------------------------------------------------------------------- #
def _docstring_constants(tree: ast.AST) -> set[int]:
    """ids of the string-Constant nodes that are module/class/function docstrings,
    so a mention of "card_items" in a docstring is NOT counted as a read."""
    ds: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ds.add(id(body[0].value))
    return ds


def reads_card_items(path: str) -> list[str]:
    """Reasons a module reads card_items.json: importing `authored_cards` (its only
    loader) or a real (non-docstring) string literal naming the file. AST-based."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    docstrings = _docstring_constants(tree)
    reasons: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "authored_cards":
                    reasons.append(f"line {node.lineno}: import authored_cards")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "authored_cards":
                reasons.append(f"line {node.lineno}: from authored_cards import ...")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if "card_items" in node.value:
                reasons.append(
                    f"line {getattr(node, 'lineno', '?')}: string {node.value!r}"
                )
    return reasons


def import_scan() -> tuple[list[dict], dict[str, list[str]]]:
    scanned: list[dict] = []
    offenders: dict[str, list[str]] = {}
    for rel in EVAL_MODULES:
        p = os.path.join(TOOLS, rel)
        if not os.path.exists(p):
            scanned.append({"module": rel, "present": False, "reads_card_items": False})
            continue
        r = reads_card_items(p)
        scanned.append(
            {"module": rel, "present": True, "reads_card_items": bool(r), "reasons": r}
        )
        if r:
            offenders[rel] = r
    return scanned, offenders


# --------------------------------------------------------------------------- #
# near-dup similarity  (same method as leakage_check.py)
# --------------------------------------------------------------------------- #
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def word_ngrams(text: str, n: int = 3) -> set[str]:
    w = normalize(text).split()
    if not w:
        return set()
    if len(w) < n:
        return {" ".join(w)}
    return {" ".join(w[i : i + n]) for i in range(len(w) - n + 1)}


def char_ngrams(text: str, n: int = 5) -> set[str]:
    s = normalize(text).replace(" ", "")
    if not s:
        return set()
    if len(s) < n:
        return {s}
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def similarity(a: str, b: str) -> float:
    if normalize(a) == normalize(b):
        return 1.0
    return max(jaccard(word_ngrams(a), word_ngrams(b)), jaccard(char_ngrams(a), char_ngrams(b)))


def _locator(sid: str, s0, s1) -> str:
    return f"{sid}#s{s0}" if s0 == s1 else f"{sid}#s{s0}-s{s1}"


# --------------------------------------------------------------------------- #
# [1b] informational overlap  (NOT an assertion -- known, expected reuse)
# --------------------------------------------------------------------------- #
def gold_overlap() -> tuple[list[dict], list[dict]]:
    items = json.load(open(CARD_ITEMS, encoding="utf-8"))["items"]
    gold = json.load(open(GOLD, encoding="utf-8"))["items"]
    text_hits: list[dict] = []
    span_hits: list[dict] = []
    for it in items:
        stem = it.get("stem", "") or ""
        answer = it.get("answer", "") or ""
        # (i) text near-dup of a gold QUESTION at the 0.80 cutoff
        best_sim, best_gid, best_field = 0.0, None, ""
        for g in gold:
            q = g.get("question", "")
            for field, txt in (("stem", stem), ("answer", answer)):
                s = similarity(txt, q)
                if s > best_sim:
                    best_sim, best_gid, best_field = s, g["gold_id"], field
        if best_sim >= LEAK_CUTOFF:
            text_hits.append(
                {
                    "card_id": it.get("id"),
                    "field": best_field,
                    "gold_id": best_gid,
                    "similarity": round(best_sim, 3),
                }
            )
        # (ii) cited SOURCE SPAN overlaps a gold item's span
        sr = it.get("source_ref") or {}
        sid, s0, s1 = sr.get("source_id"), sr.get("start"), sr.get("end")
        if sid is not None and s0 is not None and s1 is not None:
            for g in gold:
                gsp = g.get("span") or []
                if g.get("source_id") == sid and len(gsp) == 2 and int(s0) <= int(gsp[1]) and int(gsp[0]) <= int(s1):
                    span_hits.append(
                        {
                            "card_id": it.get("id"),
                            "card_locator": _locator(sid, s0, s1),
                            "gold_id": g["gold_id"],
                            "gold_locator": _locator(sid, gsp[0], gsp[1]),
                        }
                    )
    text_hits.sort(key=lambda r: -r["similarity"])
    span_hits.sort(key=lambda r: (r["card_id"] or "", r["gold_id"]))
    return text_hits, span_hits


def main() -> int:
    scanned, offenders = import_scan()
    text_hits, span_hits = gold_overlap()
    n_present = sum(1 for s in scanned if s["present"])
    guard_pass = not offenders

    bar = "=" * 74
    print(bar)
    print("CARD_ITEMS SEPARATION GUARD (P1): authored cards can never enter an eval")
    print(bar)
    print(f"allowed reader (by design): {ALLOWED_READER}")
    print(f"eval/measurement modules scanned (must NOT read card_items.json): {n_present}")
    for s in scanned:
        if not s["present"]:
            print(f"  (absent)  {s['module']}")
            continue
        print(f"  {'READS card_items!!' if s['reads_card_items'] else 'clean':<18} {s['module']}")
    print(f"\n[1a] GUARD -- no eval module reads card_items.json: {'PASS' if guard_pass else 'FAIL'}")
    for m, r in offenders.items():
        print(f"     OFFENDER {m}: {r}")

    print(
        f"\n[1b] INFO (NOT a leak; card_items is not an eval input) -- known reuse of gold-set content:"
    )
    print(f"     card_items stem/answer that near-dup a gold QUESTION (>= {LEAK_CUTOFF}): {len(text_hits)}")
    for h in text_hits:
        print(f"       {h['card_id']:<34} {h['field']:<6} ~= gold {h['gold_id']}  sim={h['similarity']:.3f}")
    print(f"     card_items whose cited SPAN overlaps a gold span: {len(span_hits)}")
    for h in span_hits:
        print(f"       {h['card_id']:<34} {h['card_locator']:<22} == gold {h['gold_id']} ({h['gold_locator']})")

    artifact = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "leak_cutoff": LEAK_CUTOFF,
        "allowed_reader": ALLOWED_READER,
        "eval_modules_scanned": [s["module"] for s in scanned if s["present"]],
        "eval_modules_absent": [s["module"] for s in scanned if not s["present"]],
        "no_eval_reads_card_items": guard_pass,
        "offenders": offenders,
        "gold_text_near_dups_informational": text_hits,
        "gold_span_overlaps_informational": span_hits,
        "invariant": "no eval consumes card_items.json; the gold-set reuse is therefore non-contaminating",
        "note": (
            "card_items.json is read ONLY by authored_cards.py (the offline generator) "
            "and by this checker. No eval/measurement module reads it, so the authored "
            "cards cannot change any eval score. The listed gold-set text/span overlaps "
            "are real and expected (the cards teach the same corpus facts the gold "
            "questions probe) and are informational, not leaks."
        ),
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(RESULTS_PATH, TOOLS)}")
    print(
        "RESULT: "
        + ("PASS -- no eval consumes card_items.json" if guard_pass else "FAIL -- an eval reads card_items.json")
    )
    return 0 if guard_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
