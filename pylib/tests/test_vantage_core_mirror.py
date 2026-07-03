# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Drift guard for the vendored scoring core.

The Vantage add-on prefers the canonical `anki.vantage` at runtime and only falls back
to its vendored copy (`vantage_addon/vantage_core`) on a stock/clean Anki that does not
bundle `anki.vantage` (see `vantage_addon/__init__.py::_vantage_collect` and
`render.py`). Because of that fallback the copy cannot be deleted -- but it must never
silently drift from the canonical source (it has before). This test fails the moment the
two diverge, so re-syncing is enforced rather than remembered.
"""

from __future__ import annotations

import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_CANON = _REPO / "pylib" / "anki" / "vantage"
_MIRROR = _REPO / "vantage_addon" / "vantage_core"
# __init__.py is intentionally different: the mirror is a tiny package shim, not the
# full pylib package init. Every other file is a byte-for-byte vendored copy.
_MIRRORED = [
    "scoring.py",
    "collect.py",
    "outline.py",
    "report.py",
    "aamc_outline.json",
    "deck_topic_map.json",
]


def test_vantage_core_is_byte_identical_to_pylib():
    drift = [
        name
        for name in _MIRRORED
        if (_CANON / name).read_text(encoding="utf-8")
        != (_MIRROR / name).read_text(encoding="utf-8")
    ]
    assert not drift, (
        f"vantage_addon/vantage_core has drifted from pylib/anki/vantage in: {drift}. "
        "Re-sync the vendored copy so the two stay byte-identical."
    )
