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
from aqt.utils import showInfo
from aqt.webview import AnkiWebView

from . import render
from . import section_mix

# Short, student-facing labels for the three science sections plus CARS.
SECTION_LABELS = {
    "chem_phys": "Chem/Phys",
    "bio_biochem": "Bio/Biochem",
    "psych_soc": "Psych/Soc",
    "cars": "CARS",
}

# Feature 4: the native Anki flag written when a card/question is flagged to revisit
# (1 = red). Reads treat ANY non-zero flag as "flagged" so a flag set from Anki's own
# reviewer (any color) still counts. One place to change the write color.
VANTAGE_FLAG = 1

# A small, self-contained toast shown INSIDE the dashboard webview -- a nicer
# replacement for Anki's built-in yellow tooltip for Vantage's own status messages
# ("Vantage refreshed", validation errors, "added N cards"). Injected with inline
# styles (no stylesheet dependency, survives the stdHtml page swap) and the Outfit
# font the page already loads. Placeholders are filled with json.dumps() so the
# message and accent are always valid JS string literals.
_TOAST_ACCENTS = {
    "info": ("#3b82f6", "rgba(59,130,246,0.22)"),  # Vantage primary blue
    "warn": ("#ef4444", "rgba(239,68,68,0.22)"),  # validation / error
}
_TOAST_TEMPLATE = """
(function () {
  var msg = __VANTAGE_TOAST_MSG__;
  if (!msg || !document.body) return;
  var existing = document.getElementById('vantage-toast');
  if (existing) existing.remove();
  var t = document.createElement('div');
  t.id = 'vantage-toast';
  t.setAttribute('role', 'status');
  t.style.cssText = 'position:fixed;left:50%;bottom:30px;transform:translate(-50%,10px);'
    + 'z-index:2147483647;display:flex;align-items:center;gap:9px;'
    + 'padding:11px 18px 11px 16px;border-radius:999px;'
    + "font-family:Outfit,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    + 'font-size:14px;font-weight:600;letter-spacing:-0.01em;'
    + 'color:#f9fafb;background:rgba(17,24,39,0.94);'
    + 'box-shadow:0 10px 30px rgba(0,0,0,0.22);'
    + '-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);'
    + 'opacity:0;transition:opacity .22s ease,transform .22s ease;pointer-events:none;';
  var dot = document.createElement('span');
  dot.style.cssText = 'width:7px;height:7px;border-radius:50%;flex:none;background:'
    + __VANTAGE_TOAST_DOT__ + ';box-shadow:0 0 0 4px ' + __VANTAGE_TOAST_GLOW__ + ';';
  t.appendChild(dot);
  var label = document.createElement('span');
  label.textContent = msg;
  t.appendChild(label);
  document.body.appendChild(t);
  requestAnimationFrame(function () {
    t.style.opacity = '1';
    t.style.transform = 'translate(-50%,0)';
  });
  setTimeout(function () {
    if (!t.parentNode) return;
    t.style.opacity = '0';
    t.style.transform = 'translate(-50%,10px)';
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 280);
  }, 2200);
})();
"""


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


def _vantage_scoring():
    """The scoring core, resolved like :func:`_vantage_collect` (prefer anki.vantage,
    else the vendored copy). Used for ScoringConfig (the interleave thresholds) and
    section_should_mix (the automatic per-section Mixed/Blocked decision)."""
    try:
        from anki.vantage import scoring
    except ModuleNotFoundError:
        from .vantage_core import scoring
    return scoring


def _vantage_outline():
    """Load the AAMC outline the same way render.py/collect resolve their core:
    prefer the copy shipped inside Anki, else the add-on's vendored snapshot.
    Returns a loaded Outline, or None if it can't be read (handled honestly by the
    caller). Used by the card-generation trigger to resolve a tapped category id to
    its name/section/topics."""
    try:
        from anki.vantage.outline import Outline
    except ModuleNotFoundError:
        try:
            from .vantage_core.outline import Outline
        except Exception:
            return None
    try:
        return Outline.load()
    except Exception:
        return None


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
        self._review_section = None  # section key, "interleave", or None (mixed)
        self._review_mix = False  # True = section matured -> interleave its review-stage cards
        self._review_answered: set = set()  # card ids studied this session
        self._review_continued = False  # True once past today's due into the broader pool
        self._review_end_ts = 0.0  # Feature 3: session deadline (epoch s); 0 = no cap
        # Feature 2 (desktop): fire a local due-cards notification ONCE per open
        # (not on every reload). Desktop has no background daemon, so this is the
        # honest substitute: a heads-up when you open Vantage and cards are waiting.
        self._due_notified = False
        self._last_reviews_due = 0
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

    def _web_toast(self, msg: str, kind: str = "info") -> None:
        """Show a small, in-webview toast for Vantage's own status messages -- a
        nicer, on-brand replacement for Anki's built-in yellow tooltip."""
        dot, glow = _TOAST_ACCENTS.get(kind, _TOAST_ACCENTS["info"])
        js = (
            _TOAST_TEMPLATE.replace("__VANTAGE_TOAST_MSG__", json.dumps(msg))
            .replace("__VANTAGE_TOAST_DOT__", json.dumps(dot))
            .replace("__VANTAGE_TOAST_GLOW__", json.dumps(glow))
        )
        try:
            self.web.eval(js)
        except Exception:
            traceback.print_exc()

    def _maybe_notify_due(self) -> None:
        """Fire a local OS notification ONCE per open when flashcards are due, using
        the SAME reviews_due the dashboard shows (never a separate count). Desktop
        has no background service, so this only fires while Vantage is open; a true
        background daemon is deliberately out of scope. macOS-only (osascript), and
        fully guarded so it can never break the dashboard. Silent when nothing is due."""
        if self._due_notified:
            return
        self._due_notified = True  # once per open, even across later reloads
        due = int(self._last_reviews_due or 0)
        if due <= 0:
            return
        import sys as _sys

        if _sys.platform != "darwin":
            return
        try:
            import subprocess

            body = f"{due} flashcard{'s' if due != 1 else ''} due to review today."
            script = f'display notification {json.dumps(body)} with title "Vantage"'
            subprocess.Popen(["osascript", "-e", script])
        except Exception:
            traceback.print_exc()

    def reload(self, toast: str | None = None, initial_tab: str = "dashboard") -> None:
        """Recompute and repaint the dashboard WITHOUT blocking the Qt main thread.

        `collect.gather` is an O(cards) scan that can take ~250 ms on a large deck;
        run inline it would freeze the UI well past the 100 ms budget. So the whole
        read+render (gather -> dashboard_dict -> build_body) runs on a background
        thread via QueryOp, and only the webview swap returns to the main thread. On
        the way we refresh the interleaver's confusability map from the student's
        latest misses. On failure we show the honest error state, never mock data.

        The repaint replaces the whole page, which would jump the scroll position to
        the top. So we read the current scroll offset first and restore it after the
        swap, so editing the target or exam date leaves you where you were.

        `toast`, if given, is shown as an in-webview toast AFTER the swap completes
        (so the page replacement doesn't wipe it).

        `initial_tab` is baked into the rebuilt page so it opens on that tab. The
        full-page swap discards the in-webview tab state, so returning from a study
        session (which is always launched from Practice) passes "practice" here to
        land the student back where they launched it, not on Dashboard.
        """
        self.web.evalWithCallback(
            "window.scrollY || 0",
            lambda s: self._reload_keeping_scroll(s, toast, initial_tab),
        )

    def _reload_keeping_scroll(
        self,
        scroll_y: object = 0,
        toast: str | None = None,
        initial_tab: str = "dashboard",
    ) -> None:
        from aqt.operations import QueryOp

        try:
            saved_scroll = max(0, int(scroll_y or 0))
        except (TypeError, ValueError):
            saved_scroll = 0

        collect = _vantage_collect()

        def op(col) -> str:
            # Keep the Rust Mixed interleaver aimed at the topics this student
            # actually confuses. Guarded so a write failure never breaks the render.
            try:
                collect.set_interleave_confusability(col)
            except Exception:
                traceback.print_exc()
            data = render.dashboard_dict(col)
            # Stash today's due-card count (the SAME reviews_due the plan shows) so
            # the once-per-open notification reuses the exact dashboard value.
            try:
                self._last_reviews_due = int((data.get("study_pace") or {}).get("reviews_due") or 0)
            except Exception:
                self._last_reviews_due = 0
            # Persist a compact snapshot so the home screen (deck browser) can show
            # the key signal without ever recomputing on the main thread. Written
            # here, off-thread, only when the compute succeeded; guarded so a cache
            # write failure never breaks the dashboard render.
            try:
                col.set_config(render.SCORE_CACHE_KEY, render.summary_cache(data))
            except Exception:
                traceback.print_exc()
            return render.build_body(data, live=True, initial_tab=initial_tab)

        def success(body: str) -> None:
            self.web.stdHtml(body, head=render.FONT_HEAD, default_css=False, context=self)
            self._maybe_notify_due()
            if saved_scroll:
                # Wait for the new content to lay out, then jump back to where the
                # student was, so an edit never yanks them to the top.
                self.web.eval(
                    "requestAnimationFrame(function(){requestAnimationFrame("
                    f"function(){{window.scrollTo(0,{saved_scroll});}});}});"
                )
            if toast:
                self._web_toast(toast)

        def failure(exc: Exception) -> None:
            traceback.print_exc()  # surface the real cause; the UI stays honest
            body = render.build_body(None, error=repr(exc), live=True)
            self.web.stdHtml(body, head=render.FONT_HEAD, default_css=False, context=self)

        QueryOp(parent=self, op=op, success=success).failure(failure).run_in_background()

    def _trigger_sync(self) -> None:
        """Additive Sync button: run Anki's real sync (the same code path as the
        toolbar Sync action), then reload the dashboard so the scores reflect
        anything just pulled. This is on top of the existing auto-sync on open and
        close, not a replacement. On success the reload resets the button; on
        failure we tell the webview so it shows a plain-language message (Anki also
        surfaces its own error dialog)."""
        try:
            auth = mw.pm.sync_auth()
        except Exception:
            auth = None
        if not auth:
            self._web_toast(
                "Sign in to Anki sync first (Tools > Preferences > Syncing)", kind="warn"
            )
            self.web.eval("window.vantageSyncDone && window.vantageSyncDone(false);")
            return

        def after_sync() -> None:
            self.reload(toast="Synced")

        try:
            mw._sync_collection_and_media(after_sync)
        except Exception:
            traceback.print_exc()
            self.web.eval("window.vantageSyncDone && window.vantageSyncDone(false);")

    def _on_cmd(self, cmd: str):
        if cmd == "vantage:refresh":
            self.reload(toast="Vantage refreshed")
        elif cmd.startswith("vantage:refresh:"):
            # Refresh, keeping the student on the tab they were on. The current tab
            # (window.__vtab) rides along from the web layer so the full-page rebuild
            # restores it via __VANTAGE_INITIAL_TAB__ instead of resetting to Dashboard.
            tab = cmd.split(":", 2)[2]
            if tab not in ("dashboard", "practice", "progress"):
                tab = "dashboard"
            self.reload(toast="Vantage refreshed", initial_tab=tab)
        elif cmd == "vantage:sync:trigger":
            self._trigger_sync()
        elif cmd == "vantage:studydone":
            # Returned from the in-dashboard reviewer: recompute so the scores
            # reflect the just-studied cards. Silent (no tooltip) on every exit.
            # The reviewer is always launched from the Practice tab, so land back
            # there (the full-page swap would otherwise reset to Dashboard).
            self.reload(initial_tab="practice")
        elif cmd == "vantage:back":
            self.close()
        elif cmd == "vantage:study":
            self._review_start()
        elif cmd.startswith("vantage:studytimed:"):
            # Feature 3: vantage:studytimed:<minutes>:<section-or-interleave>. Matched
            # BEFORE the generic vantage:study: prefix so the more specific command wins.
            parts = cmd.split(":", 3)
            try:
                minutes = max(0, min(180, int(parts[2])))
            except (IndexError, ValueError):
                minutes = 0
            section = parts[3] if len(parts) > 3 else None
            if section == "interleave":
                section = None
            self._review_start(section, limit_secs=minutes * 60)
        elif cmd.startswith("vantage:review:flag:"):
            # Feature 4: flag/unflag the card on screen. Metadata only, no advance.
            self._review_set_flag(cmd.rsplit(":", 1)[1])
        elif cmd.startswith("vantage:flagq:"):
            # Feature 4: flag/unflag a reasoning question (creates/reuses its anchor).
            self._flag_reasoning(cmd[len("vantage:flagq:") :])
        elif cmd.startswith("vantage:study:"):
            self._review_start(cmd.split(":", 2)[2])
        elif cmd == "vantage:review:more":
            self._review_more()
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
        elif cmd.startswith("vantage:gencards:"):
            self._generate_cards(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:examdatesave:"):
            # Persist-only (no reload): fires on every value change so the exam date is
            # committed to config even if the field never blurs before an external Sync.
            self._set_exam_date(cmd.split(":", 2)[2], reload=False)
        elif cmd.startswith("vantage:examdate:"):
            self._set_exam_date(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:targetsave:"):
            # Persist-only (no reload): fires on every keystroke so the target is
            # committed to config even if the field never blurs before an external
            # Sync (the onchange/reload path only fires on blur or Enter).
            self._set_target(cmd.split(":", 2)[2], reload=False)
        elif cmd.startswith("vantage:target:"):
            self._set_target(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:bookset:"):
            self._set_book_set(cmd.split(":", 2)[2])
        elif cmd.startswith("vantage:open:"):
            from aqt.utils import openLink

            openLink(cmd.split(":", 2)[2])
        return None

    def _set_exam_date(self, iso: str, reload: bool = True) -> None:
        """Store (or clear) the student's exam date, then recompute the plan.

        `reload=False` is the persist-only path used by the input's `oninput` so the
        value reaches config even if the field never blurs before an external Sync; the
        blur/Enter `onchange` path keeps `reload=True` to recompute the plan.
        """
        collect = _vantage_collect()

        iso = (iso or "").strip()
        if iso:
            from datetime import date

            try:
                date.fromisoformat(iso)
            except ValueError:
                self._web_toast("Could not read that date", kind="warn")
                return
            mw.col.set_config(collect.EXAM_CONFIG_KEY, iso)
        else:
            mw.col.remove_config(collect.EXAM_CONFIG_KEY)
        if reload:
            self.reload()

    def _set_target(self, value: str, reload: bool = True) -> None:
        """Store (or clear) the target readiness composite, then recompute.

        `reload=False` is the persist-only path used by the input's `oninput` (every
        keystroke) so the value reaches config even if the field never blurs before an
        external Sync. The blur/Enter `onchange` path keeps `reload=True` to recompute.
        """
        collect = _vantage_collect()

        value = (value or "").strip()
        if value:
            try:
                mw.col.set_config(collect.TARGET_CONFIG_KEY, int(round(float(value))))
            except ValueError:
                self._web_toast("Enter a number for your target", kind="warn")
                return
        else:
            mw.col.remove_config(collect.TARGET_CONFIG_KEY)
        if reload:
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
        # "practice" or "test": tags each answer so Test-mode results are
        # distinguishable in reporting, while feeding the SAME performance pipeline.
        mode = data.get("mode")
        items = data.get("items", [])
        if not isinstance(items, list):
            return
        made = 0
        sl_total = 0  # second-look re-attempts recorded in this batch
        sl_cleared = 0  # of those, how many were corrected this time
        for it in items:
            correct = bool(it.get("correct"))
            stem = it.get("stem", "") or ""
            answer = it.get("answer", "") or ""
            explain = it.get("explain", "") or ""
            concept = it.get("concept") or None
            # The SIRS skill the item tests (author-tagged in the bank): the second
            # axis of the miss diagnosis. Tagged onto the anchor card like concept.
            skill = it.get("skill") or None
            # A batch can mix sections (a second-look session pulls from every
            # section that has one due), so honor the item's own section when set.
            it_section = it.get("section") or section
            is_second_look = bool(it.get("second_look"))
            qid = it.get("qid") or None
            # Log the outcome as a real revlog row on a Vantage Reasoning card, so
            # correct/incorrect syncs + merges across devices (no config clobber). A
            # second look is a real re-attempt of the same question, so it flows
            # through the SAME pipeline as any re-practice -- not a new blend.
            rid = None
            if stem:
                try:
                    rid = collect.log_reasoning_outcome(
                        mw.col, it_section, stem, answer, explain, correct,
                        it.get("ms"), concept, skill,
                    )
                except Exception:
                    traceback.print_exc()  # don't hide a real logging failure
            # Metacognition to this device's per-device key, linked to the revlog
            # outcome by id (config-only when no revlog row could be made).
            try:
                collect.record_metacognition(
                    mw.col, it_section, correct,
                    confidence=it.get("confidence"), reason=it.get("reason"),
                    ms=it.get("ms"), revlog_id=rid, concept=concept, mode=mode,
                    skill=skill,
                )
            except Exception:
                traceback.print_exc()  # don't hide a real logging failure
            if is_second_look and qid:
                # Re-attempt of a previously-missed question: record the result
                # DISTINCTLY from the original miss (its own per-device store). A
                # miss reschedules another delayed look; a pass resolves it. This
                # never touches the concept-level misses deck or the miss signal.
                try:
                    collect.record_second_look_outcome(mw.col, qid, it_section, correct)
                    sl_total += 1
                    if correct:
                        sl_cleared += 1
                except Exception:
                    traceback.print_exc()
            elif not correct and stem:
                # A fresh miss: keep the existing concept-level flashcard reminder
                # AND schedule a delayed second look at THIS exact question, so the
                # two mechanisms stay complementary and independent.
                if self._make_miss_card(it_section, stem, answer, explain):
                    made += 1
                try:
                    collect.schedule_second_look(
                        mw.col, it_section, stem, answer, explain, concept
                    )
                except Exception:
                    traceback.print_exc()
        if sl_total:
            self._web_toast(
                f"You cleared {sl_cleared} of {sl_total} second look"
                f"{'s' if sl_total != 1 else ''}"
            )
        elif made:
            self._web_toast(
                f"Added {made} card{'s' if made != 1 else ''} to review your misses"
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

    def _generate_cards(self, concept_id: str) -> None:
        """Opt-in: generate cards for one thin AAMC category the student tapped.

        Runs the EXISTING vantage_tools generation pipeline (cited sources + the
        same grounding and quality gate as every other AI card) scoped to this one
        category, then writes ONLY the cards that PASSED the gate into a real deck
        so they count toward coverage on the refresh. Nothing is generated unless
        the student taps this suggestion; the pipeline and its gate are called
        unchanged (see cardgen_bridge).

        Honest states, never a fabricated success and never MOCK:
          * not set up   -> no provider configured, say so plainly.
          * nothing new  -> the gate rejected everything (or all were duplicates).
          * error        -> tell the student, log the real cause to the console.

        The provider call can hit the network, so generation runs off the Qt main
        thread (QueryOp); the note-writing then happens on the main thread in the
        success callback, exactly like the misses deck.
        """
        from . import cardgen_bridge

        concept_id = (concept_id or "").strip()
        outline = _vantage_outline()
        concept = outline.concept(concept_id) if outline is not None else None
        if concept is None:
            self._web_toast(
                "Couldn't find that topic to generate cards for", kind="warn"
            )
            return
        name = concept.name
        section = concept.section
        # Retrieval terms from the category's own topics (or aliases): they steer
        # retrieval toward the nearest corpus chunks. The pipeline still decides
        # what, if anything, is grounded enough to publish.
        terms = [t.name for t in getattr(concept, "topics", ())] or [
            a.replace("_", " ") for a in getattr(concept, "aliases", ())
        ]
        self._web_toast(f"Generating cards for {name}. This can take a moment.")

        from aqt.operations import QueryOp

        def op(col) -> object:
            # Provider/CPU work only (may touch the network); NO collection writes
            # here. Returns the gate's published cards for the main thread to write.
            return cardgen_bridge.generate_for_category(
                concept_id, name, section, terms
            )

        def success(outcome: object) -> None:
            st = getattr(outcome, "status", cardgen_bridge.STATUS_ERROR)
            if st == cardgen_bridge.STATUS_NOT_CONFIGURED:
                self._web_toast(
                    "AI card generation isn't set up on this computer yet",
                    kind="warn",
                )
                return
            if st == cardgen_bridge.STATUS_UNAVAILABLE:
                self._web_toast(
                    "Card generation isn't available in this build", kind="warn"
                )
                return
            if st != cardgen_bridge.STATUS_GENERATED:
                self._web_toast(
                    "Couldn't generate cards, please try again", kind="warn"
                )
                return
            made = 0
            published = getattr(outcome, "published", []) or []
            if published:
                try:
                    made = cardgen_bridge.write_generated_cards(
                        mw.col, concept_id, section, published
                    )
                except Exception:
                    traceback.print_exc()  # don't hide a real write failure
            if made:
                # Refresh so the new cards count toward coverage; land on Progress,
                # where the suggestion lives.
                self.reload(
                    toast=f"Added {made} checked card{'s' if made != 1 else ''} for {name}",
                    initial_tab="progress",
                )
            else:
                self._web_toast(
                    f"No new cards passed the check for {name}", kind="warn"
                )

        def failure(exc: Exception) -> None:
            traceback.print_exc()  # surface the real cause; UI stays honest
            self._web_toast("Couldn't generate cards, please try again", kind="warn")

        QueryOp(parent=self, op=op, success=success).failure(failure).run_in_background()

    # ---- in-dashboard reviewer: real cards, Anki's own scheduler ----
    def _review_start(self, section: str | None = None, limit_secs: int = 0) -> None:
        """Study inside the dashboard, DUE cards only. Cards are scheduled and graded
        by Anki's own engine (col.sched); only the frame around the card is Vantage's.

        section None / "interleave": review through Anki's own queue, where topic
        interleaving is on, so the order mixes sections. A science-section key studies
        just that section's due cards. When today's due queue is exhausted the reviewer
        offers to keep going with the broader non-due pool (see _review_more); grading
        reschedules every card normally in both phases.
        """
        col = mw.col
        self._review_card = None
        # Section keys no longer carry a marker: the Mixed vs Blocked choice is made
        # automatically below from the section's card maturity. None / "interleave"
        # still mean the whole-queue review (Anki's own interleaved scheduler queue).
        self._review_section = section
        self._review_answered = set()
        self._review_continued = False
        # Feature 3: optional session time cap. 0 = no cap (unchanged flow). The
        # deadline is enforced server-side in _review_answer (a session-END only,
        # never a scoring change); the webview gets end_ms only to show a countdown.
        self._review_end_ts = (time.time() + limit_secs) if limit_secs > 0 else 0.0
        end_ms = int(self._review_end_ts * 1000) if self._review_end_ts else 0
        # Feature 4: the flagged pool -- every non-suspended card flagged to revisit,
        # across sections. Suspended reasoning anchors (queue -1) are excluded (they
        # are re-served in practice.js), so this is a flashcards-only queue.
        if section == "flagged":
            self._review_section = None  # generic done screen, no section "keep going"
            self._review_continued = True
            self._review_queue = col.db.list(
                "select c.id from cards c where c.flags != 0 and c.queue >= 0 order by c.due"
            )
            self._review_label = "Flagged cards"
            self.web.eval(
                f"window.vreview && window.vreview.enter({json.dumps({'endMs': end_ms})});"
            )
            self._push_next_card()
            return
        if section and section != "interleave":
            label = section_mix.section_label(section, SECTION_LABELS)
            scoring = _vantage_scoring()
            cfg = scoring.ScoringConfig()
            # Decide Mixed vs Blocked from the section's OVERALL maturity (the share
            # of ALL its review-stage cards that have matured), not just today's due
            # slice, so the call is stable day to day and matches the dashboard's
            # status label. Honest default is Blocked (see scoring.section_should_mix).
            mature_count, review_count = self._section_maturity_counts(col, section, cfg)
            should_mix, _reason = scoring.section_should_mix(
                mature_count, review_count, cfg
            )
            self._review_mix = should_mix
            # Only cards actually DUE now: new (queue 0), intraday learning whose
            # second-timestamp due has arrived (queue 1), or review/day-learning whose
            # day-number due is today or earlier (queue 2/3). A card just graded
            # (rescheduled to the future) therefore does not reappear this session.
            # c.queue rides along so a Mixed section interleaves ONLY its review-stage
            # (queue 2) cards, keeping new/still-learning cards grouped by topic.
            today = col.sched.today
            now = int(time.time())
            rows = col.db.all(
                "select c.id, n.tags, c.queue from cards c join notes n on c.nid = n.id "
                "where n.tags like ? and ("
                "  c.queue = 0"
                "  or (c.queue = 1 and c.due <= ?)"
                "  or (c.queue in (2, 3) and c.due <= ?)"
                ") order by (c.queue = 0), c.due",
                f"%mcat::{section}::%",
                now,
                today,
            )
            self._review_queue = self._order_section_rows(rows, should_mix)
            self._review_label = f"{label} mixed" if should_mix else f"{label} flashcards"
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
        self.web.eval(
            f"window.vreview && window.vreview.enter({json.dumps({'endMs': end_ms})});"
        )
        self._push_next_card()

    def _section_maturity_counts(self, col, section: str, cfg) -> tuple[int, int]:
        """(mature_count, review_count) over the section's review-stage cards.

        review_count is its non-suspended review-stage cards (queue 2); mature_count
        is those that have matured (ivl >= cfg.interleave_mature_ivl_days). Measured
        over the WHOLE review pool -- not just today's due cards -- so the auto
        Mixed/Blocked decision is stable across days and matches the dashboard label.
        """
        ivls = col.db.list(
            "select c.ivl from cards c join notes n on c.nid = n.id "
            "where n.tags like ? and c.queue = 2",
            f"%mcat::{section}::%",
        )
        review_count = len(ivls)
        mature_count = sum(1 for ivl in ivls if ivl >= cfg.interleave_mature_ivl_days)
        return (mature_count, review_count)

    def _order_section_rows(self, rows, mix: bool) -> list:
        """Order a section's ``(cid, tags, queue)`` rows for study.

        Mixed: interleave ONLY the review-stage subset (queue 2) across topics, then
        append the new / still-learning cards (queue 0/1/3) grouped by topic. Brand
        new and learning cards are never folded into the discrimination round-robin
        (the whole point of the maturity gate); they stay in focused topic blocks,
        drained after the interleaved reviews. Blocked: the whole section grouped by
        topic (focused acquisition). Mirrors the Rust engine's Mixed/Blocked modes.
        """
        if mix:
            review_rows = [(cid, tags) for cid, tags, q in rows if q == 2]
            other_rows = [(cid, tags) for cid, tags, q in rows if q != 2]
            return section_mix.interleave_cids_by_topic(
                review_rows, "mcat::"
            ) + section_mix.block_cids_by_topic(other_rows, "mcat::")
        return section_mix.block_cids_by_topic(
            [(cid, tags) for cid, tags, q in rows], "mcat::"
        )

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
                self._review_done()
                return
            counts = self._queue_counts()
            deck_label = self._review_label or col.decks.name(card.did)
        else:
            card = col.sched.getCard()
            self._review_card = card
            if card is None:
                self._review_done()
                return
            c = col.sched.counts()
            counts = {"new": c[0], "lrn": c[1], "rev": c[2]}
            deck_label = self._review_label or col.decks.name(card.did)
        payload = {
            "deck": deck_label,
            "counts": counts,
            "css": card.note_type().get("css", ""),
            "html": card.question(),
            "flag": card.user_flag(),  # Feature 4: restore the star per card
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
            "flag": card.user_flag(),  # Feature 4: keep the star through show-answer
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
        try:
            self._review_answered.add(card.id)  # so the "keep going" pool skips it
        except Exception:
            pass
        if self._review_queue:
            answered = self._review_queue.pop(0)
            if ease == 1:  # Again: keep it in this session, at the back
                self._review_queue.append(answered)
        # Feature 3 time cap: the card just answered graded normally (above). If the
        # session clock has run out, end here instead of fetching the next card. This
        # is a session-END only; nothing about scheduling or grading changed.
        if self._review_end_ts and time.time() >= self._review_end_ts:
            self._review_done(timeup=True)
            return
        self._push_next_card()

    def _broader_pool(self) -> list:
        """The section's (or, for the mixed queue, the whole exam's) non-suspended
        cards not yet answered this session. This is exactly the all-non-suspended
        set the old 'Study all' used, minus what was just studied, so the "keep
        going" continuation drills the broader non-due pool. Grading still
        reschedules each card normally; nothing here changes how cards are scored."""
        col = mw.col
        section = self._review_section
        if section and section != "interleave":
            rows = col.db.all(
                "select c.id, n.tags, c.queue from cards c join notes n on c.nid = n.id "
                "where n.tags like ? and c.queue >= 0 order by (c.queue = 0), c.due",
                f"%mcat::{section}::%",
            )
            # Match the initial queue: same session Mixed/Blocked decision, and the
            # same review-only interleave (new/learning stay grouped by topic).
            cids = self._order_section_rows(rows, self._review_mix)
        else:
            cids = col.db.list(
                "select c.id from cards c join notes n on c.nid = n.id "
                "where n.tags like '%mcat::%' and c.queue >= 0"
            )
        answered = self._review_answered or set()
        pool = [c for c in cids if c not in answered]
        if not (section and section != "interleave"):
            import random

            random.shuffle(pool)  # keep the mixed queue mixed, not single-section blocked
        return pool

    def _review_done(self, timeup: bool = False) -> None:
        """End of the session: the honest 'nice work' state. At time-up (Feature 3)
        we don't offer 'keep going' (the student asked to stop at N minutes); when
        the pool naturally empties we still offer the broader non-due pool as today."""
        section = self._review_section
        sec_label = section_mix.section_label(section, SECTION_LABELS)
        can_continue = (
            (not timeup)
            and (not self._review_continued)
            and len(self._broader_pool()) > 0
        )
        payload = {"section": sec_label, "canContinue": can_continue, "timeup": bool(timeup)}
        self.web.eval(f"window.vreview && window.vreview.done({json.dumps(payload)});")

    def _review_more(self) -> None:
        """Keep studying: load the broader non-due pool and continue. One-way (the
        pool is finite); once it runs out the done state won't offer more again."""
        self._review_continued = True
        self._review_queue = self._broader_pool()
        self._review_card = None
        self._push_next_card()

    def _review_set_flag(self, want: str) -> None:
        """Feature 4: flag/unflag the card on screen. Metadata only -- no reschedule
        and no advance, so the session stays exactly where it is. Writes the native
        Anki flag (red) so it syncs and is browsable; clears to 0 to unflag."""
        card = self._review_card
        if card is None:
            return
        try:
            new = VANTAGE_FLAG if int(want) else 0
        except ValueError:
            new = 0
        try:
            mw.col.set_user_flag_for_cards(new, [card.id])
        except Exception:
            traceback.print_exc()

    def _flag_reasoning(self, raw: str) -> None:
        """Feature 4: flag/unflag a reasoning question. It has no queue card until
        answered, so create (or reuse) its suspended anchor via the existing
        recording primitive (ensure_reasoning_card), then set the native flag on that
        anchor -- the same card its attempts already log onto."""
        import urllib.parse

        collect = _vantage_collect()
        try:
            data = json.loads(urllib.parse.unquote(raw))
        except Exception:
            return
        stem = (data.get("stem") or "").strip()
        if not stem:
            return
        on = bool(data.get("on", True))
        try:
            cid = collect.ensure_reasoning_card(
                mw.col,
                data.get("section", ""),
                stem,
                data.get("answer", "") or "",
                data.get("explain", "") or "",
                data.get("concept") or None,
                data.get("skill") or None,
            )
            if cid is not None:
                mw.col.set_user_flag_for_cards(VANTAGE_FLAG if on else 0, [cid])
        except Exception:
            traceback.print_exc()


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
