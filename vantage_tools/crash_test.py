#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) - §7g crash-safety test (DESKTOP).

PRE-REGISTRATION (written before the run; do not weaken after seeing results):
    Pass = zero collections fail SQLite `pragma integrity_check` (and reopen
    cleanly with a readable revlog) after 20 mid-review kills per platform.

What this proves
----------------
Anki stores everything in one SQLite file (``collection.anki2``). If the app is
killed while a review is being written, SQLite's crash recovery must leave the
file consistent: either the interrupted transaction is fully applied or fully
rolled back, never half-written. This harness kills the writer with SIGKILL
(uncatchable, no cleanup, no graceful close) in the middle of an active review
loop, then reopens the file and checks it. A single corrupted collection is a
FAIL.

How each iteration works
------------------------
  1. Copy a fresh test collection to ``iter_NN.anki2`` (the master is either
     built by build_exam_collection or copied from --base).
  2. Spawn a CHILD process that opens that copy through the real Anki Python API
     and reviews as fast as it can in a tight loop:
         card = col.sched.getCard(); card.start_timer(); col.sched.answerCard(...)
     (falling back to answering an arbitrary card so write pressure never stops).
     The child writes a readiness marker only AFTER its first answer has
     committed, so by the time we kill it at least one review is on disk and the
     writer is provably active.
  3. The parent waits for readiness, sleeps a small random delay so the kill
     lands somewhere inside the write loop, then SIGKILLs the child
     (os.kill(pid, 9)). SIGKILL cannot be caught, so no flush/close/checkpoint
     runs - a write is interrupted.
  4. The parent reopens the collection through the real Anki engine (the same
     rusqlite instance the app uses, which registers Anki's custom ``unicase``
     collation - the stock python sqlite3 module cannot run integrity_check on
     this schema because it lacks that collation) and records:
         - reopen_ok            (the app can open the file at all)
         - revlog readable      (select count + newest row parse)
         - pragma integrity_check == "ok"
     The iteration passes only if all three hold.

Honesty notes
-------------
  * The integrity check is run by SQLite itself; we only forward the pragma
    through Anki's connection so the ``unicase`` collation is present.
  * revlog_growth (post-crash revlog count minus the pre-crash baseline) is
    recorded per iteration to show the writer really was committing reviews when
    it was killed - the test is not vacuously passing on an idle process.
  * Results (per-iteration + totals + verdict) are written to
    vantage_tools/crash_results.json and printed as a table.

Usage
-----
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python vantage_tools/crash_test.py
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python vantage_tools/crash_test.py \\
        --iterations 20 --base "$HOME/Library/Application Support/Anki2/User 1/collection.anki2"
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DEFAULT_RESULTS = os.path.join(HERE, "crash_results.json")

PREREGISTRATION = (
    "Pass = zero collections fail SQLite `pragma integrity_check` (and reopen "
    "cleanly with a readable revlog) after 20 mid-review kills per platform."
)

# Deck the harness fills with brand-new cards so the writer has a sustained,
# legitimately-queued supply to review (and be killed) each iteration.
CRASH_DECK = "Crash Deck"
# Anki's backend clamps a deck config's perDay to <= 9999; larger values are
# silently rejected (revert to the default 20).
PER_DAY_LIMIT = 9999
# New cards to seed. Plenty to keep the writer busy for the whole kill window
# even at several thousand answers/sec.
BUFFER_CARDS = 4000


# ---------------------------------------------------------------------------
# CHILD: the process we kill mid-write. Never exits on its own (SIGKILL only).
# ---------------------------------------------------------------------------
def run_child(coll_path: str, ready_path: str) -> int:
    from anki.collection import Collection

    random.seed(os.getpid() ^ int(time.time() * 1000))
    col = Collection(coll_path)
    # Everything the note-add fallback needs if the queue ever drains.
    basic = col.models.by_name("Basic")
    crash_did = col.decks.id(CRASH_DECK)

    answered = 0
    extra = 0
    while True:
        card = col.sched.getCard()
        if card is None:
            # Queue drained inside this iteration (rare with a big buffer). Add a
            # brand-new note and review it: a new card is legitimately top-of-queue
            # (the v3 backend rejects answering an arbitrary out-of-queue card), and
            # the add itself is another interruptible write. Never stop writing.
            note = col.new_note(basic)
            note["Front"] = f"crash-refill {extra}"
            note["Back"] = "x"
            extra += 1
            col.add_note(note, crash_did)
            card = col.sched.getCard()
            if card is None:
                continue
        card.start_timer()
        ease = random.choices([1, 2, 3, 4], weights=[1, 2, 5, 2])[0]
        col.sched.answerCard(card, ease)
        answered += 1
        if answered == 1:
            # First review is committed and on disk -> we are provably writing.
            with open(ready_path, "w") as fh:
                fh.write(str(os.getpid()))
    # unreachable; only SIGKILL stops the loop


# ---------------------------------------------------------------------------
# PARENT helpers
# ---------------------------------------------------------------------------
def copy_collection(src: str, dst: str) -> None:
    """Copy a collection plus any WAL/SHM sidecars for a faithful snapshot."""
    for ext in ("", "-wal", "-shm"):
        s = src + ext
        d = dst + ext
        if os.path.exists(s):
            shutil.copy2(s, d)
        elif os.path.exists(d):
            os.remove(d)


def child_env() -> dict:
    env = os.environ.copy()
    pypath = os.pathsep.join(
        [os.path.join(REPO_ROOT, "pylib"), os.path.join(REPO_ROOT, "out", "pylib")]
    )
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pypath + (os.pathsep + existing if existing else "")
    return env


def revlog_count_stock(path: str) -> int | None:
    """revlog has no unicase index, so the stock sqlite3 module can read it.

    Used only for the pre-crash baseline (fast, no backend spin-up)."""
    try:
        con = sqlite3.connect(path)
        try:
            return int(con.execute("select count() from revlog").fetchone()[0])
        finally:
            con.close()
    except Exception:
        return None


def check_collection(path: str) -> dict:
    """Reopen through the real Anki engine and run the integrity check.

    Returns a dict with reopen_ok / revlog_count / integrity / integrity_ok /
    journal_mode and a derived ``pass`` flag."""
    rec: dict = {
        "reopen_ok": None,
        "revlog_count": None,
        "revlog_readable": None,
        "reopen_error": None,
        "integrity": None,
        "integrity_ok": None,
        "integrity_error": None,
        "journal_mode": None,
    }
    from anki.collection import Collection

    try:
        col = Collection(path)
    except Exception as exc:  # corrupt enough that the app cannot even open it
        rec["reopen_ok"] = False
        rec["reopen_error"] = repr(exc)
        return _finalize(rec)

    try:
        rec["reopen_ok"] = True
        try:
            count = col.db.scalar("select count() from revlog")
            # Parsing the newest row proves the revlog is actually readable,
            # not just countable.
            newest = col.db.all("select id, cid, ease from revlog order by id desc limit 1")
            rec["revlog_count"] = int(count or 0)
            rec["revlog_readable"] = True
            _ = newest
        except Exception as exc:
            rec["revlog_readable"] = False
            rec["reopen_error"] = repr(exc)
        try:
            rows = col.db.all("pragma integrity_check")
            flat = [r[0] for r in rows]
            rec["integrity"] = flat
            rec["integrity_ok"] = flat == ["ok"]
        except Exception as exc:
            rec["integrity_ok"] = False
            rec["integrity_error"] = repr(exc)
        try:
            jm = col.db.all("pragma journal_mode")
            rec["journal_mode"] = jm[0][0] if jm else None
        except Exception:
            pass
    finally:
        try:
            col.close()
        except Exception:
            pass
    return _finalize(rec)


def _finalize(rec: dict) -> dict:
    rec["pass"] = bool(rec.get("reopen_ok") and rec.get("revlog_readable") and rec.get("integrity_ok"))
    return rec


def prep_master(work: str, base: str | None, buffer_cards: int) -> tuple[str, str, int]:
    """Create the master collection every iteration is copied from.

    Returns (master_path, source_label, seeded_cards). The master keeps whatever
    realistic reviewed history it starts with (from build_exam_collection or the
    copied base) AND gets a large buffer of brand-new cards in CRASH_DECK plus a
    raised daily limit, so the child can review continuously and be killed
    mid-write in every iteration."""
    from anki.collection import Collection

    master = os.path.join(work, "master.anki2")
    if base:
        if not os.path.exists(base):
            raise SystemExit(f"--base not found: {base}")
        copy_collection(base, master)
        source = f"copy:{base}"
    else:
        sys.path.insert(0, HERE)
        import build_exam_collection

        build_exam_collection.build(master)
        source = "build_exam_collection"

    col = Collection(master)
    try:
        basic = col.models.by_name("Basic")
        did = col.decks.id(CRASH_DECK)
        conf = col.decks.config_dict_for_deck_id(did)
        conf["new"]["perDay"] = PER_DAY_LIMIT
        conf["rev"]["perDay"] = PER_DAY_LIMIT
        col.decks.update_config(conf)
        for i in range(buffer_cards):
            note = col.new_note(basic)
            note["Front"] = f"crash q{i}"
            note["Back"] = "x"
            col.add_note(note, did)
        # Study CRASH_DECK by default so a fresh copy immediately has due cards.
        col.decks.select(did)
    finally:
        col.close()
    return master, source, buffer_cards


def one_iteration(
    i: int,
    master_path: str,
    work: str,
    kill_delay: tuple[float, float],
    ready_timeout: float,
) -> dict:
    coll_path = os.path.join(work, f"iter_{i:02d}.anki2")
    ready_path = coll_path + ".ready"
    err_path = coll_path + ".child.err"
    for p in (ready_path, err_path):
        if os.path.exists(p):
            os.remove(p)

    copy_collection(master_path, coll_path)
    baseline = revlog_count_stock(coll_path)

    rec: dict = {
        "iteration": i,
        "baseline_revlog": baseline,
        "became_ready": False,
        "killed_while_writing": False,
        "child_exit_code": None,
        "wal_present_after_kill": None,
        "shm_present_after_kill": None,
        "kill_delay_s": None,
    }

    env = child_env()
    with open(err_path, "wb") as errf:
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--child", coll_path, ready_path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=errf,
        )
    try:
        # Wait until the child has committed its first review (or died / timed out).
        t0 = time.time()
        while time.time() - t0 < ready_timeout:
            if os.path.exists(ready_path):
                rec["became_ready"] = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.005)

        if rec["became_ready"] and proc.poll() is None:
            delay = random.uniform(*kill_delay)
            rec["kill_delay_s"] = round(delay, 4)
            time.sleep(delay)
            if proc.poll() is None:
                os.kill(proc.pid, signal.SIGKILL)  # hard kill, mid-write
                rec["killed_while_writing"] = True
    finally:
        try:
            rec["child_exit_code"] = proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            rec["child_exit_code"] = proc.wait()

    # Snapshot crash artifacts before we reopen (reopen will recover/checkpoint).
    rec["wal_present_after_kill"] = os.path.exists(coll_path + "-wal")
    rec["shm_present_after_kill"] = os.path.exists(coll_path + "-shm")

    if not rec["became_ready"]:
        # Harness problem (child never started writing) - capture why.
        try:
            with open(err_path, "r", errors="replace") as fh:
                rec["child_stderr"] = fh.read()[-2000:]
        except Exception:
            rec["child_stderr"] = None

    check = check_collection(coll_path)
    rec.update(check)
    if isinstance(rec.get("revlog_count"), int) and isinstance(baseline, int):
        rec["revlog_growth"] = rec["revlog_count"] - baseline
    else:
        rec["revlog_growth"] = None

    # Tidy per-iteration artifacts (keep results.json only).
    for p in (
        coll_path,
        coll_path + "-wal",
        coll_path + "-shm",
        ready_path,
        err_path,
    ):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    return rec


def print_table(results: list[dict]) -> None:
    hdr = (
        f"{'it':>3}  {'ready':>5}  {'killed':>6}  {'wal':>3}  "
        f"{'baseRev':>7}  {'postRev':>7}  {'grew':>4}  {'reopen':>6}  "
        f"{'integrity':>9}  {'PASS':>4}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        integ = "ok" if r.get("integrity_ok") else str(r.get("integrity"))
        print(
            f"{r['iteration']:>3}  "
            f"{str(r.get('became_ready')):>5}  "
            f"{str(r.get('killed_while_writing')):>6}  "
            f"{str(r.get('wal_present_after_kill')):>3}  "
            f"{str(r.get('baseline_revlog')):>7}  "
            f"{str(r.get('revlog_count')):>7}  "
            f"{str(r.get('revlog_growth')):>4}  "
            f"{str(r.get('reopen_ok')):>6}  "
            f"{integ:>9}  "
            f"{str(bool(r.get('pass'))):>4}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="§7g desktop crash-safety test")
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument(
        "--base",
        default=None,
        help="collection.anki2 to copy each run (default: build a fresh exam collection)",
    )
    ap.add_argument("--out", default=DEFAULT_RESULTS, help="results JSON path")
    ap.add_argument("--kill-min", type=float, default=0.01)
    ap.add_argument("--kill-max", type=float, default=0.5)
    ap.add_argument("--ready-timeout", type=float, default=30.0)
    ap.add_argument("--buffer-cards", type=int, default=BUFFER_CARDS)
    ap.add_argument("--keep-work", action="store_true", help="do not delete the temp workdir")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="vantage_crash_")
    print(f"workdir: {work}")
    started = time.time()
    try:
        master_path, source, seeded = prep_master(work, args.base, args.buffer_cards)
        master_revlog = revlog_count_stock(master_path)
        print(
            f"master collection: {source}  (baseline revlog rows: {master_revlog}, "
            f"seeded {seeded} new cards in '{CRASH_DECK}', perDay={PER_DAY_LIMIT})"
        )
        print(f"pre-registration: {PREREGISTRATION}\n")

        results: list[dict] = []
        for i in range(1, args.iterations + 1):
            rec = one_iteration(
                i,
                master_path,
                work,
                (args.kill_min, args.kill_max),
                args.ready_timeout,
            )
            results.append(rec)
            print(
                f"  iter {i:>2}: ready={rec['became_ready']} "
                f"killed={rec['killed_while_writing']} "
                f"wal={rec['wal_present_after_kill']} "
                f"revlog {rec.get('baseline_revlog')}->{rec.get('revlog_count')} "
                f"(+{rec.get('revlog_growth')}) "
                f"integrity={'ok' if rec.get('integrity_ok') else rec.get('integrity')} "
                f"PASS={bool(rec.get('pass'))}"
            )

        passes = sum(1 for r in results if r.get("pass"))
        fails = len(results) - passes
        integrity_failures = [r["iteration"] for r in results if not r.get("integrity_ok")]
        reopen_failures = [r["iteration"] for r in results if not r.get("reopen_ok")]
        not_killed = [r["iteration"] for r in results if not r.get("killed_while_writing")]
        verdict = "PASS" if (fails == 0 and len(results) == args.iterations) else "FAIL"

        payload = {
            "test": "vantage-crash-safety-desktop",
            "section": "7g",
            "platform": f"desktop-{sys.platform}",
            "preregistration": PREREGISTRATION,
            "verdict": verdict,
            "collection_source": source,
            "seeded_new_cards": seeded,
            "per_day_limit": PER_DAY_LIMIT,
            "python": sys.version.split()[0],
            "sqlite_runtime": sqlite3.sqlite_version,
            "integrity_engine": "anki rusqlite (registers unicase collation)",
            "iterations_requested": args.iterations,
            "iterations_run": len(results),
            "kill_delay_range_s": [args.kill_min, args.kill_max],
            "totals": {
                "pass": passes,
                "fail": fails,
                "integrity_failures": integrity_failures,
                "reopen_failures": reopen_failures,
                "iterations_not_killed_while_writing": not_killed,
            },
            "elapsed_s": round(time.time() - started, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "results": results,
        }
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)

        print("\n" + "=" * 72)
        print_table(results)
        print("=" * 72)
        print(
            f"iterations: {len(results)}/{args.iterations}   "
            f"pass: {passes}   fail: {fails}"
        )
        print(f"integrity_check failures: {integrity_failures or 'none'}")
        print(f"reopen failures: {reopen_failures or 'none'}")
        if not_killed:
            print(f"NOTE iterations where the writer was not confirmed killed: {not_killed}")
        print(f"\nVERDICT: {verdict}")
        print(f"results written to: {args.out}")
        return 0 if verdict == "PASS" else 1
    except Exception:
        traceback.print_exc()
        return 2
    finally:
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--child":
        # hidden mode: run_child(coll_path, ready_path)
        raise SystemExit(run_child(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
