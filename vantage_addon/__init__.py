# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage Readiness dashboard (MCAT project). An Anki add-on.

Opens a full-window "layer" over Anki that renders the three honest scores
(memory / performance / readiness), the AAMC coverage map, and the best-next
topic, computed live from anki.vantage. Flat-design UI (see web/).
"""

from __future__ import annotations

import os

from aqt import gui_hooks, mw
from aqt.qt import QKeySequence, QMainWindow, QShortcut
from aqt.utils import showInfo, tooltip
from aqt.webview import AnkiWebView

from . import render


# --------------------------------------------------------------------------- #
# Full-window dashboard
# --------------------------------------------------------------------------- #
class VantageDashboard(QMainWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vantage Readiness")
        self.web = AnkiWebView(self, title="vantage")
        self.web.set_bridge_command(self._on_cmd, self)
        self.setCentralWidget(self.web)
        self.resize(1280, 900)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self.reload()

    def reload(self) -> None:
        try:
            body = render.build_body(render.dashboard_dict(mw.col))
        except Exception as exc:  # keep the layer usable even if scoring errors
            body = render.build_body(None, error=repr(exc))
        self.web.stdHtml(body, head=render.FONT_HEAD, default_css=False, context=self)

    def _on_cmd(self, cmd: str):
        if cmd == "vantage:refresh":
            self.reload()
            tooltip("Vantage refreshed", parent=self)
        elif cmd == "vantage:back":
            self.close()
        return None


def open_dashboard() -> None:
    if mw.col is None:
        showInfo("Open a profile first, then reopen Vantage.")
        return
    # keep a reference so it isn't garbage-collected
    mw._vantage_dashboard = VantageDashboard(mw)
    mw._vantage_dashboard.showMaximized()


# --------------------------------------------------------------------------- #
# Entry points: Tools menu + toolbar link
# --------------------------------------------------------------------------- #
def _install_menu() -> None:
    from aqt.qt import QAction

    action = QAction("Vantage Readiness", mw)
    action.setShortcut(QKeySequence("Ctrl+Shift+V"))
    action.triggered.connect(open_dashboard)
    mw.form.menuTools.addAction(action)


def _add_toolbar_link(links, toolbar) -> None:
    links.append(
        toolbar.create_link(
            "vantage",
            "Vantage",
            open_dashboard,
            tip="Open the Vantage readiness dashboard",
            id="vantage",
        )
    )


_install_menu()
gui_hooks.top_toolbar_did_init_links.append(_add_toolbar_link)

# Demo convenience: auto-open the dashboard once the collection loads.
if os.environ.get("VANTAGE_AUTOOPEN"):
    from aqt.qt import QTimer

    gui_hooks.collection_did_load.append(lambda _col: QTimer.singleShot(800, open_dashboard))
