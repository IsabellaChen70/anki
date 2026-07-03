#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Two-way sync reconcile + conflict test through a REAL self-hosted Anki sync server.

Simulates two devices (A = "desktop", B = "phone") sharing one account, and proves
the two guarantees the brief grades:

  1. RECONCILE (none lost, none double-counted): both devices review OFFLINE -- A
     reviews 10 distinct cards, B reviews 10 different cards -- then reconnect and
     sync. Both collections must end with revlog += 20 and no duplicate ids.
  2. SAME-CARD CONFLICT (documented winner): both devices review the SAME card
     offline. Both reviews must survive (2 revlog rows for that card) and the
     later-timestamp review must be the authoritative last one (last-review-wins,
     D-SYNC1 in docs/spec-sync-mobile.md).

It uses anki's real Rust sync (sync_login / sync_collection / full_upload_or_download)
-- the exact code path AnkiDroid uses -- so it is a faithful, re-runnable proof.

Prereq: a self-hosted server running, e.g.
  SYNC_USER1=vantage:pass SYNC_HOST=0.0.0.0 SYNC_PORT=8080 \\
    SYNC_BASE=out/syncserver_data PYTHONPATH=pylib:out/pylib \\
    out/pyenv/bin/python -m anki.syncserver

Run:
  PYTHONPATH=pylib:out/pylib out/pyenv/bin/python vantage_tools/sync_reconcile_test.py \\
    --base "$HOME/Library/Application Support/Anki2/User 1/collection.anki2" \\
    --endpoint http://127.0.0.1:8080/ --user vantage --password pass
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time

from anki.collection import Collection

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "sync_reconcile_results.json")


def revlog_total(col: Collection) -> int:
    return col.db.scalar("select count() from revlog") or 0


def revlog_distinct(col: Collection) -> int:
    return col.db.scalar("select count(distinct id) from revlog") or 0


def do_sync(col: Collection, auth, who: str) -> str:
    """One sync, handling the first full upload/download. Returns what happened."""
    out = col.sync_collection(auth, sync_media=False)
    req = out.required
    if req == out.NO_CHANGES:
        return "normal"
    if req == out.FULL_UPLOAD:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
        col.reopen(after_full_sync=True)
        return "full_upload"
    if req == out.FULL_DOWNLOAD:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        col.reopen(after_full_sync=True)
        return "full_download"
    raise RuntimeError(
        f"{who}: unexpected full-sync conflict (required={req}); "
        "this controlled test expects fast-forwardable syncs"
    )


def review(col: Collection, cids: list[int], ease: int) -> None:
    """Answer specific cards (a real review each: revlog row + reschedule)."""
    for cid in cids:
        card = col.get_card(cid)
        card.start_timer()
        col.sched.answerCard(card, ease)
        time.sleep(0.01)  # guarantee distinct millisecond revlog ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="collection.anki2 to seed both devices")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/")
    ap.add_argument("--user", default="vantage")
    ap.add_argument("--password", default="pass")
    ap.add_argument("--n", type=int, default=10, help="offline reviews per device")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="vantage_sync_")
    a_path = os.path.join(work, "deviceA.anki2")
    b_path = os.path.join(work, "deviceB.anki2")

    # Device A starts from the base collection; copy the -wal too for a consistent
    # snapshot of a possibly-open source. Device B starts empty and full-downloads.
    shutil.copy(args.base, a_path)
    for ext in ("-wal", "-shm"):
        if os.path.exists(args.base + ext):
            shutil.copy(args.base + ext, a_path + ext)

    failures: list[str] = []
    results: dict = {
        "endpoint": args.endpoint,
        "n_per_device": args.n,
        "checks": [],
        "numbers": {},
    }

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  ' + detail) if detail else ''}")
        results["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    def _write() -> None:
        results["passed"] = not failures
        results["n_failed"] = len(failures)
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, sort_keys=True)
            fh.write("\n")

    A = Collection(a_path)
    B = Collection(b_path)
    try:
        authA = A.sync_login(args.user, args.password, args.endpoint)
        authB = B.sync_login(args.user, args.password, args.endpoint)

        print("\n== initial sync (A force-uploads base, B force-downloads -> shared) ==")
        # Force a clean full upload/download so the test is idempotent across runs
        # regardless of what the server already holds.
        A.close_for_full_sync()
        A.full_upload_or_download(auth=authA, server_usn=None, upload=True)
        A.reopen(after_full_sync=True)
        print("  A: full_upload (reset server to base)")
        B.close_for_full_sync()
        B.full_upload_or_download(auth=authB, server_usn=None, upload=False)
        B.reopen(after_full_sync=True)
        print("  B: full_download")

        r0_a, r0_b = revlog_total(A), revlog_total(B)
        check("initial revlog counts match", r0_a == r0_b, f"A={r0_a} B={r0_b}")

        cids = list(A.find_cards("-is:suspended"))
        need = 2 * args.n + 1
        if len(cids) < need:
            print(f"  base has only {len(cids)} non-suspended cards, need {need}")
            return 2
        set_a = cids[: args.n]
        set_b = cids[args.n : 2 * args.n]
        card_c = cids[2 * args.n]

        print(f"\n== offline: A reviews {args.n} cards, B reviews {args.n} different cards ==")
        review(A, set_a, ease=3)
        time.sleep(0.2)
        review(B, set_b, ease=3)

        print("== reconnect + reconcile ==")
        print(f"  A push: {do_sync(A, authA, 'A')}")
        print(f"  B push+pull: {do_sync(B, authB, 'B')}")
        print(f"  A pull: {do_sync(A, authA, 'A')}")

        a_tot, b_tot = revlog_total(A), revlog_total(B)
        check("A revlog grew by 20", a_tot == r0_a + 2 * args.n, f"{r0_a} -> {a_tot}")
        check("B revlog grew by 20", b_tot == r0_b + 2 * args.n, f"{r0_b} -> {b_tot}")
        check("A: no duplicate revlog ids", revlog_total(A) == revlog_distinct(A))
        check("B: no duplicate revlog ids", revlog_total(B) == revlog_distinct(B))
        check("both sides identical revlog count", a_tot == b_tot, f"A={a_tot} B={b_tot}")
        results["numbers"].update(
            {
                "initial_revlog": r0_a,
                "A_revlog_after_reconcile": a_tot,
                "B_revlog_after_reconcile": b_tot,
                "A_distinct_ids": revlog_distinct(A),
                "B_distinct_ids": revlog_distinct(B),
            }
        )

        print("\n== same-card conflict (A: Again, then later B: Easy) ==")
        # card_c may already carry prior review history, so baseline its row count.
        c0 = A.db.scalar("select count() from revlog where cid=?", card_c) or 0
        review(A, [card_c], ease=1)  # A answers first (earlier timestamp)
        time.sleep(0.3)
        review(B, [card_c], ease=4)  # B answers later (later timestamp -> should win)
        print(f"  A push: {do_sync(A, authA, 'A')}")
        print(f"  B push+pull: {do_sync(B, authB, 'B')}")
        print(f"  A pull: {do_sync(A, authA, 'A')}")

        for name, col in (("A", A), ("B", B)):
            rows = col.db.scalar("select count() from revlog where cid=?", card_c) or 0
            last_ease = col.db.scalar(
                "select ease from revlog where cid=? order by id desc limit 1", card_c
            )
            results["numbers"][f"conflict_rows_{name}"] = rows
            results["numbers"][f"conflict_last_ease_{name}"] = last_ease
            check(
                f"{name}: both conflict reviews retained (+2)",
                rows == c0 + 2,
                f"rows={rows} (baseline {c0})",
            )
            check(
                f"{name}: later-timestamp review wins (last ease = Easy/4)",
                last_ease == 4,
                f"last_ease={last_ease}",
            )
            check(f"{name}: still no duplicate revlog ids", revlog_total(col) == revlog_distinct(col))

        print("\n" + "=" * 60)
        if failures:
            print(f"RESULT: {len(failures)} CHECK(S) FAILED: {failures}")
            return 1
        print("RESULT: two-way sync verified - no reviews lost or double-counted,")
        print("        and the same-card conflict resolves to the later review.")
        return 0
    finally:
        try:
            _write()
            print(f"\nwrote {os.path.relpath(RESULTS_PATH, HERE)}")
        except Exception:
            pass
        try:
            A.close()
        except Exception:
            pass
        try:
            B.close()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
