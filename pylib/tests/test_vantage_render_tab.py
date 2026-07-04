# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Regression tests for the dashboard's "which tab on (re)load" wiring
(vantage_addon/render.py).

The Vantage dashboard is one webview whose tabs (Dashboard / Practice / Progress)
are client-side state. Returning from a study session does a FULL page swap, which
discards that in-page state, so the host has to bake the tab to open into the
rebuilt page. render.build_body injects it as window.__VANTAGE_INITIAL_TAB__, which
dashboard.js reads to land the student back on Practice (the tab they launched from)
instead of resetting to Dashboard.

render.py is pure (only stdlib at import time), so it is loaded by path here and
needs no Anki collection or aqt GUI imports.
"""

from __future__ import annotations

import importlib.util
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO / "vantage_addon" / "render.py"


def _load():
    spec = importlib.util.spec_from_file_location("vantage_render", _MODULE_PATH)
    assert spec and spec.loader, _MODULE_PATH
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


render = _load()

# Minimal payload: build_body only json.dumps() the data, it never inspects it.
_DATA: dict = {}


def test_data_script_defaults_to_dashboard_tab():
    js = render._data_script(_DATA, live=True)
    assert 'window.__VANTAGE_INITIAL_TAB__ = "dashboard";' in js


def test_data_script_bakes_requested_tab():
    js = render._data_script(_DATA, live=True, initial_tab="practice")
    assert 'window.__VANTAGE_INITIAL_TAB__ = "practice";' in js
    # never leak the wrong default alongside it
    assert 'window.__VANTAGE_INITIAL_TAB__ = "dashboard";' not in js


def test_build_body_defaults_to_dashboard_tab():
    body = render.build_body(_DATA, live=True)
    assert 'window.__VANTAGE_INITIAL_TAB__ = "dashboard";' in body


def test_build_body_bakes_practice_tab_for_study_return():
    body = render.build_body(_DATA, live=True, initial_tab="practice")
    assert 'window.__VANTAGE_INITIAL_TAB__ = "practice";' in body


def test_initial_tab_is_set_before_dashboard_script_runs():
    # The global must be defined before dashboard.js executes, or render() cannot
    # read it. dashboard.js exposes window.__vantageRender; assert the global comes
    # first in the page source.
    body = render.build_body(_DATA, live=True, initial_tab="practice")
    tab_at = body.find("window.__VANTAGE_INITIAL_TAB__")
    render_at = body.find("window.__vantageRender")
    assert tab_at != -1 and render_at != -1
    assert tab_at < render_at


def test_mobile_page_defaults_to_dashboard_tab():
    # The bundled mobile page never asks for a non-default tab (its study flow is a
    # separate activity), so it must bake the Dashboard default.
    page = render.build_mobile_page(_DATA)
    assert 'window.__VANTAGE_INITIAL_TAB__ = "dashboard";' in page
