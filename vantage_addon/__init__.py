# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage Readiness dashboard (MCAT project). An Anki add-on.

Opens a full-window "layer" over Anki that renders the three honest scores
(memory / performance / readiness), the AAMC coverage map, and the best-next
topic, computed live from anki.vantage. Flat-design UI (see web/).
"""

from __future__ import annotations

import json
import os
import time
import traceback

from aqt import gui_hooks, mw
from aqt.qt import QKeySequence, QMainWindow, QShortcut
from aqt.utils import showInfo, tooltip
from aqt.webview import AnkiWebView

from . import render

# Short, student-facing labels for the three science sections plus CARS.
SECTION_LABELS = {
    "chem_phys": "Chem/Phys",
    "bio_biochem": "Bio/Biochem",
    "psych_soc": "Psych/Soc",
    "cars": "CARS",
}


def _vantage_collect():
    """The scoring/collection adapter, resolved the same way render.py does: prefer
    the copy shipped inside Anki (anki.vantage), and fall back to the add-on's
    vendored core so the add-on works on any Anki -- including a clean-machine
    install whose bundled wheel doesn't include anki.vantage."""
    try:
        from anki.vantage import collect
    except ModuleNotFoundError:
        from .vantage_core import collect
    return collect


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
        self._review_card = None
        self._review_queue = None  # None = use Anki's own queue (interleaved); list = a section queue
        self._review_label = None
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self._render_loading()
        self.reload()

    def _render_loading(self) -> None:
        """Paint a tiny placeholder instantly so the first open never shows a blank
        frame while the real dashboard is computed off the main thread."""
        html = (
            '<div style="position:fixed;inset:0;display:flex;align-items:center;'
            'justify-content:center;background:#ffffff;color:#6b7280;'
            'font:500 15px/1.4 Outfit,system-ui,-apple-system,sans-serif;">'
            "Loading your dashboard</div>"
        )
        self.web.stdHtml(html, head=render.FONT_HEAD, default_css=False, context=self)

    def reload(self) -> None:
        """Recompute and repaint the dashboard WITHOUT blocking the Qt main thread.

        `collect.gather` is an O(cards) scan that can take ~250 ms on a large deck;
        run inline it would freeze the UI well past the 100 ms budget. So the whole
        read+render (gather -> dashboard_dict -> build_body) runs on a background
        thread via QueryOp, and only the webview swap returns to the main thread. On
        the way we refresh the interleaver's confusability map from the student's
        latest misses. On failure we show the honest error state, never mock data.
        """
        from aqt.operations import QueryOp

        collect = _vantage_collect()

        def op(col) -> str:
            # Keep the Rust Mixed interleaver aimed at the topics this student
            # actually confuses. Guarded so a write failure never breaks the render.
            try:
                collect.set_interleave_confusability(col)
            except Exception:
                traceback.print_exc()
            data = render.dashboard_dict(col)
            # Persist a compact snapshot so the home screen (deck browser) can show
            # the key signal without ever recomputing on the main thread. Written
            # here, off-thread, only when the compute succeeded; guarded so a cache
            # write failure never breaks the dashboard render.
            try:
                col.set_config(render.SCORE_CACHE_KEY, render.summary_cache(data))
            except Exception:
                traceback.print_exc()
            return render.build_body(data, live=True)

        def success(body: str) -> None:
            self.web.stdHtml(body, head=render.FONT_HEAD, default_css=False, context=self)

        def failure(exc: Exception) -> None:
            traceback.print_exc()  # surface the real cause; the UI stays honest
            body = render.build_body(None, error=repr(exc), live=True)
            self.web.stdHtml(body, head=render.FONT_HEAD, default_css=False, context=self)

        QueryOp(parent=self, op=op, success=success).failure(failure).run_in_background()

    def _on_cmd(self, cmd: str):
        if cmd == "vantage:refresh":
            self.reload()
            tooltip("Vantage refreshed", parent=self)
        elif cmd == "vantage:back":
            self.close()
        elif cmd == "vantage:study":
            self._review_start()
        elif cmd.startswith("vantage:study:"):
            self._review_start(cmd.split(":", 2)[2])
        elif cmd == "vantage:review:show":
            self._review_show_answer()
        elif cmd.startswith("vantage:review:answer:"):
            try:
                ease = int(cmd.rsplit(":", 1)[1])
            except ValueError:
                ease = 3
            self._review_answer(ease)
        elif cmd.startswith("vantage:practice2:"):
            self._record_practice2(cmd)
        elif cmd.startswith("vantage:practice:"):
            self._record_practice(cmd)
        elif cmd.startswith("vantage:examdate:"):
            self._set_exam_date(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:target:"):
            self._set_target(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:bookset:"):
            self._set_book_set(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:open:"):
            from aqt.utils import openLink

            openLink(cmd.split(":", 2)[2])
        return None

    def _set_exam_date(self, iso: str) -> None:
        """Store (or clear) the student's exam date, then recompute the plan."""
        collect = _vantage_collect()

        iso = (iso or "").strip()
        if iso:
            from datetime import date

            try:
                date.fromisoformat(iso)
            except ValueError:
                tooltip("Could not read that date", parent=self)
                return
            mw.col.set_config(collect.EXAM_CONFIG_KEY, iso)
        else:
            mw.col.remove_config(collect.EXAM_CONFIG_KEY)
        self.reload()

    def _set_target(self, value: str) -> None:
        """Store (or clear) the target readiness composite, then recompute."""
        collect = _vantage_collect()

        value = (value or "").strip()
        if value:
            try:
                mw.col.set_config(collect.TARGET_CONFIG_KEY, int(round(float(value))))
            except ValueError:
                tooltip("Enter a number for your target", parent=self)
                return
        else:
            mw.col.remove_config(collect.TARGET_CONFIG_KEY)
        self.reload()

    def _set_book_set(self, brand: str) -> None:
        """Store the student's MCAT book set. No reload: the dashboard swaps the
        named book in place, client-side, so paging isn't disturbed."""
        collect = _vantage_collect()

        brand = (brand or "").strip()
        if brand in collect.BOOK_SETS:
            mw.col.set_config(collect.BOOK_CONFIG_KEY, brand)

    def _record_practice(self, cmd: str) -> None:
        """Fold a practice session into the performance-outcomes store, so the
        Performance score reflects real application-item practice."""
        # cmd: vantage:practice:<section>:<correct>:<total>
        parts = cmd.split(":")
        if len(parts) != 5:
            return
        section = parts[2]
        try:
            correct = int(parts[3])
            total = int(parts[4])
        except ValueError:
            return
        collect = _vantage_collect()

        outcomes = mw.col.get_config(collect.PERF_CONFIG_KEY, [])
        if not isinstance(outcomes, list):
            outcomes = []
        now = int(time.time())
        for i in range(total):
            outcomes.append(
                {"section": section, "correct": i < correct, "predicted": None, "ts": now}
            )
        collect.set_perf_outcomes(mw.col, outcomes)

    def _record_practice2(self, cmd: str) -> None:
        """Fold a rich practice session (per-item confidence + miss reason) into
        the performance store, and turn each missed question into a spaced
        re-review card so the miss comes back until it is beaten.

        Outcomes are written the sync-safe way: the correct/incorrect signal is a
        real revlog attempt on the question's anchor card, and the metacognition
        the revlog can't carry (confidence, miss reason, timing, linked concept)
        goes to THIS device's OWN per-device config key via record_metacognition.
        Two devices practicing offline therefore never clobber each other on sync;
        the read path (_merged_outcomes) merges every per-device key and links each
        record to its revlog outcome by id, counting the answer once."""
        import urllib.parse

        collect = _vantage_collect()

        raw = cmd[len("vantage:practice2:") :]
        try:
            data = json.loads(urllib.parse.unquote(raw))
        except Exception:
            return
        section = data.get("section", "")
        items = data.get("items", [])
        if not isinstance(items, list):
            return
        made = 0
        for it in items:
            correct = bool(it.get("correct"))
            stem = it.get("stem", "") or ""
            answer = it.get("answer", "") or ""
            explain = it.get("explain", "") or ""
            concept = it.get("concept") or None
            # Log the outcome as a real revlog row on a Vantage Reasoning card, so
            # correct/incorrect syncs + merges across devices (no config clobber).
            rid = None
            if stem:
                try:
                    rid = collect.log_reasoning_outcome(
                        mw.col, section, stem, answer, explain, correct,
                        it.get("ms"), concept,
                    )
                except Exception:
                    traceback.print_exc()  # don't hide a real logging failure
            # Metacognition to this device's per-device key, linked to the revlog
            # outcome by id (config-only when no revlog row could be made).
            try:
                collect.record_metacognition(
                    mw.col, section, correct,
                    confidence=it.get("confidence"), reason=it.get("reason"),
                    ms=it.get("ms"), revlog_id=rid, concept=concept,
                )
            except Exception:
                traceback.print_exc()  # don't hide a real logging failure
            if not correct and stem:
                if self._make_miss_card(section, stem, answer, explain):
                    made += 1
        if made:
            tooltip(
                f"Added {made} card{'s' if made != 1 else ''} to review your misses",
                parent=self,
            )

    def _make_miss_card(self, section: str, stem: str, answer: str, explain: str) -> bool:
        """Create one Basic card (deck 'Vantage Misses', FSRS-scheduled) for a
        missed reasoning question. Deduped by the question text so re-practice
        does not pile up copies."""
        import hashlib

        col = mw.col
        seen = col.get_config("vantage_miss_seen", [])
        if not isinstance(seen, list):
            seen = []
        key = hashlib.md5(stem.encode("utf-8")).hexdigest()[:12]
        if key in seen:
            return False
        try:
            model = col.models.by_name("Basic")
            deck_id = col.decks.id("Vantage Misses")
            note = col.new_note(model)
            note["Front"] = stem
            note["Back"] = f"{answer}<br><br>{explain}" if answer else explain
            note.tags = [f"vantage::miss::{section}"]
            col.add_note(note, deck_id)
        except Exception:
            return False
        seen.append(key)
        col.set_config("vantage_miss_seen", seen)
        return True

    # ---- in-dashboard reviewer: real cards, Anki's own scheduler ----
    def _review_start(self, section: str | None = None) -> None:
        """Study inside the dashboard. Cards are scheduled and graded by Anki's
        own engine (col.sched); only the frame around the card is Vantage's.

        section None / "interleave": review through Anki's own queue on the exam
        deck, where topic-interleaving is on, so the order mixes sections. A
        science-section key (e.g. "chem_phys") studies just that section's cards,
        graded the same way (nextIvlStr / answerCard both work per card id).
        """
        col = mw.col
        self._review_card = None
        if section and section != "interleave":
            label = SECTION_LABELS.get(section, section)
            cids = col.db.list(
                "select c.id from cards c join notes n on c.nid = n.id "
                "where n.tags like ? and c.queue >= 0 "
                "order by (c.queue = 0), c.due",
                f"%mcat::{section}::%",
            )
            self._review_queue = list(cids)
            self._review_label = f"{label} flashcards"
        else:
            self._review_queue = None
            self._review_label = "Interleaved review" if section == "interleave" else None
            try:
                did = col.db.scalar(
                    "select did from cards where queue >= 0 group by did order by count(*) desc limit 1"
                )
                if did:
                    col.decks.select(did)
            except Exception:
                pass
        self.web.eval("window.vreview && window.vreview.enter();")
        self._push_next_card()

    def _queue_counts(self) -> dict:
        from anki.utils import ids2str

        ids = self._review_queue or []
        if not ids:
            return {"new": 0, "lrn": 0, "rev": 0}
        rows = mw.col.db.list(f"select queue from cards where id in {ids2str(ids)}")
        return {
            "new": sum(1 for q in rows if q == 0),
            "lrn": sum(1 for q in rows if q in (1, 3)),
            "rev": sum(1 for q in rows if q == 2),
        }

    def _push_next_card(self) -> None:
        col = mw.col
        if self._review_queue is not None:
            card = None
            while self._review_queue:
                candidate = col.get_card(self._review_queue[0])
                # col.get_card leaves the timer unset; without this, answerCard's
                # time_taken() does time.time() - None and raises TypeError.
                candidate.start_timer()
                if candidate.queue < 0:  # suspended/buried since we gathered
                    self._review_queue.pop(0)
                    continue
                card = candidate
                break
            self._review_card = card
            if card is None:
                self.web.eval("window.vreview && window.vreview.done();")
                return
            counts = self._queue_counts()
            deck_label = self._review_label or col.decks.name(card.did)
        else:
            card = col.sched.getCard()
            self._review_card = card
            if card is None:
                self.web.eval("window.vreview && window.vreview.done();")
                return
            c = col.sched.counts()
            counts = {"new": c[0], "lrn": c[1], "rev": c[2]}
            deck_label = self._review_label or col.decks.name(card.did)
        payload = {
            "deck": deck_label,
            "counts": counts,
            "css": card.note_type().get("css", ""),
            "html": card.question(),
        }
        self.web.eval(f"window.vreview && window.vreview.card({json.dumps(payload)});")

    def _review_show_answer(self) -> None:
        card = self._review_card
        if card is None:
            return
        labels = ["Again", "Hard", "Good", "Easy"]
        classes = ["again", "hard", "good", "easy"]
        buttons = []
        for i, ease in enumerate((1, 2, 3, 4)):
            try:
                ivl = mw.col.sched.nextIvlStr(card, ease, short=True)
            except Exception:
                ivl = ""
            buttons.append({"ease": ease, "label": labels[i], "cls": classes[i], "ivl": ivl})
        payload = {
            "css": card.note_type().get("css", ""),
            "html": card.answer(),
            "buttons": buttons,
        }
        self.web.eval(f"window.vreview && window.vreview.answer({json.dumps(payload)});")

    def _review_answer(self, ease: int) -> None:
        card = self._review_card
        if card is None:
            return
        try:
            mw.col.sched.answerCard(card, ease)
        except Exception:
            traceback.print_exc()  # don't hide real grading failures
        if self._review_queue:
            answered = self._review_queue.pop(0)
            if ease == 1:  # Again: keep it in this session, at the back
                self._review_queue.append(answered)
        self._push_next_card()


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


# --------------------------------------------------------------------------- #
# Compact summary on the home screen (Deck Browser + deck Overview)
# --------------------------------------------------------------------------- #
# Show the key readiness signal directly on Anki's home screen so the student
# sees it without opening the full dashboard. This path NEVER recomputes scores:
# the deck list is redrawn on every home visit, so doing Monte-Carlo/IRT work
# here would blow the main-thread budget. Instead we only READ the small snapshot
# the full dashboard writes to collect config (render.SCORE_CACHE_KEY), and hand
# it to render.build_summary. The full standalone dashboard is unchanged.
def _is_mcat_collection(col) -> bool:
    """True only for a Vantage/MCAT collection, so this stays a no-op on ordinary
    Anki profiles. Cheap: a config read plus a scan of the (small) tag list, no
    card search. Once the dashboard has run at least once the cache alone answers
    it; otherwise we look for the shipped mcat:: tag prefix."""
    try:
        if col.get_config(render.SCORE_CACHE_KEY, None) is not None:
            return True
    except Exception:
        pass
    try:
        collect = _vantage_collect()
        prefix = getattr(collect, "INTERLEAVE_DEFAULT_PREFIX", "mcat")
        for tag in col.tags.all():
            if tag == prefix or tag.startswith(prefix + "::"):
                return True
    except Exception:
        pass
    return False


def _home_summary_html(col) -> str | None:
    """The compact card's HTML for the current collection, or None to render
    nothing (non-MCAT collection or no collection open). Read-only + cheap."""
    if col is None or not _is_mcat_collection(col):
        return None
    try:
        cache = col.get_config(render.SCORE_CACHE_KEY, None)
    except Exception:
        cache = None
    try:
        return render.build_summary(cache)
    except Exception:
        traceback.print_exc()  # never break the home screen over the card
        return None


def _on_deck_browser_content(deck_browser, content) -> None:
    html = _home_summary_html(mw.col)
    if html:
        content.stats += html


def _on_overview_content(overview, content) -> None:
    # Optional per-deck surface: the same honest overall snapshot, shown on an
    # MCAT deck's overview. Readiness is a whole-collection number, so it is
    # framed as overall (not per-deck) inside the card.
    html = _home_summary_html(mw.col)
    if html:
        content.table += html


def _on_home_message(handled, message: str, context):
    """Route the home card's button through the pycmd bridge. Only our own
    namespaced command is claimed; everything else passes through untouched."""
    if message == render.SUMMARY_OPEN_CMD:
        open_dashboard()
        return (True, None)
    return handled


gui_hooks.deck_browser_will_render_content.append(_on_deck_browser_content)
gui_hooks.overview_will_render_content.append(_on_overview_content)
gui_hooks.webview_did_receive_js_message.append(_on_home_message)


# Auto-open the dashboard once the collection loads, so launching Anki lands you
# straight on Vantage. On by default; turn it off with the collection config key
# "vantage_autoopen" = false, or override with the VANTAGE_AUTOOPEN env var
# (1 forces on, 0 forces off).
from aqt.qt import QTimer


def _maybe_autoopen(col) -> None:
    env = os.environ.get("VANTAGE_AUTOOPEN")
    if env is not None:
        enabled = env.strip().lower() not in ("", "0", "false", "no")
    else:
        try:
            enabled = bool(col.get_config("vantage_autoopen", True))
        except Exception:
            enabled = True
    if enabled:
        QTimer.singleShot(800, open_dashboard)


gui_hooks.collection_did_load.append(_maybe_autoopen)
