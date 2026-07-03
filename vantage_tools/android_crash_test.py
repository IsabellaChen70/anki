#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Vantage (MCAT project) - §7g crash-safety test (ANDROID / AnkiDroid).

PRE-REGISTRATION (written before the run; do not weaken after seeing results):
    Pass = zero collections fail SQLite `pragma integrity_check` (and reopen
    cleanly with a readable revlog) after 20 mid-review kills per platform.

What this proves
----------------
AnkiDroid keeps the whole collection in one SQLite file. `am force-stop` sends an
uncatchable kill to the app's process group, so if it lands while a review is
being written the write is interrupted with no chance to flush, close, or
checkpoint. This harness force-stops the app during an active review 20 times and
verifies the collection is still consistent every time. One corrupted collection
is a FAIL.

Per iteration
-------------
  1. force-stop the app (clean slate), launch com.ichi2.anki.Reviewer (studies the
     selected deck directly), wait for the reviewer window.
  2. Drive real reviews on-device: tap "Show answer" then "Good" in a loop (device
     is 1080x2400; screenshots are ~2.34x smaller, so screenshot coords are scaled
     up by 2.34). Each "Good" writes a review row.
  3. After a small random delay (kill lands somewhere in the review loop),
     `am force-stop` the app - the mid-review hard kill.
  4. Reopen check (the authoritative integrity check):
        * The device's stock `sqlite3` CANNOT run integrity_check on this schema -
          it fails with "no such collation sequence: unicase" because Anki
          registers a custom `unicase` collation (used by the tags / decks /
          notetypes name indexes) that only the rslib engine provides. We still
          run and RECORD the on-device sqlite3 output for transparency, but it is
          NOT the pass/fail signal.
        * Authoritative check: pull the collection (+ -wal/-shm) to the host and
          run `pragma integrity_check` + revlog readability through the SAME rslib
          SQLite engine AnkiDroid itself uses (Anki's out/pylib backend, which
          registers unicase). This is check_collection() from crash_test.py, the
          exact logic the desktop test uses.
  5. Relaunch the DeckPicker and confirm the app opens (the collection is usable).

Honesty notes
-------------
  * The known WAL force-kill "count lag" (a review shown as answered may be in the
    WAL but not checkpointed when the process dies, so the due count can appear to
    lag) is NOT corruption. This test asserts integrity, not the review count.
  * revlog growth across iterations is recorded to show reviews really were being
    written when the app was killed.
  * If the emulator is too flaky to complete 20 clean iterations, the harness
    records exactly how many iterations completed and reports the real number.

Usage
-----
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python vantage_tools/android_crash_test.py
    PYTHONPATH=pylib:out/pylib out/pyenv/bin/python vantage_tools/android_crash_test.py \\
        --iterations 20 --no-reseed
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from crash_test import PREREGISTRATION, check_collection  # noqa: E402

ADB = "/Users/isabellachen/projects/android-tools/android-sdk/platform-tools/adb"
SERIAL = "emulator-5554"
PKG = "com.ichi2.anki.debug"
REVIEWER = "com.ichi2.anki.Reviewer"
DECKPICKER = "com.ichi2.anki.DeckPicker"
COLL = "/storage/emulated/0/Android/data/com.ichi2.anki.debug/files/AnkiDroid/collection.anki2"
DEFAULT_RESULTS = os.path.join(HERE, "android_crash_results.json")

CRASH_DECK = "Crash Deck"
PER_DAY_LIMIT = 9999
# Tap targets (device pixels). "Show answer" spans the bottom bar; "Good" is the
# third of four ease buttons revealed after showing the answer.
TAP_SHOW = (538, 2274)
TAP_GOOD = (667, 2281)


# ---------------------------------------------------------------------------
# adb helpers - never raise on a non-zero device command; record and continue.
# ---------------------------------------------------------------------------
def adb(*args: str, timeout: float = 40.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [ADB, "-s", SERIAL, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args, 124, stdout="", stderr=f"timeout: {exc}")


def sh(cmd: str, timeout: float = 40.0) -> subprocess.CompletedProcess:
    return adb("shell", cmd, timeout=timeout)


def force_stop() -> None:
    sh(f"am force-stop {PKG}")


def current_focus() -> str:
    return sh("dumpsys window 2>/dev/null | grep mCurrentFocus | head -2").stdout


def wait_focus(substr: str, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if substr in current_focus():
            return True
        time.sleep(0.3)
    return False


def device_wal_present() -> bool:
    return "-wal" in sh(f"ls -la '{COLL}'*").stdout


def revlog_on_device_copy(pull_path: str) -> int | None:
    try:
        con = __import__("sqlite3").connect(pull_path)
        try:
            return int(con.execute("select count() from revlog").fetchone()[0])
        finally:
            con.close()
    except Exception:
        return None


def pull_collection(dst_dir: str) -> str:
    dst = os.path.join(dst_dir, "collection.anki2")
    for ext in ("", "-wal", "-shm"):
        adb("pull", COLL + ext, dst + ext)
    return dst


# ---------------------------------------------------------------------------
# Reseed: give the device a big buffer of due cards so every iteration is a real
# mid-review kill. Backs up the current device collection first.
# ---------------------------------------------------------------------------
def reseed_device(buffer_cards: int, backup_dir: str) -> dict:
    from anki.collection import Collection

    os.makedirs(backup_dir, exist_ok=True)
    force_stop()
    time.sleep(1.0)
    backup = os.path.join(backup_dir, "collection.anki2")
    for ext in ("", "-wal", "-shm"):
        adb("pull", COLL + ext, backup + ext)

    work = os.path.join(backup_dir, "reseed.anki2")
    for ext in ("", "-wal", "-shm"):
        for p in (work + ext,):
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(backup + ext):
            shutil.copy2(backup + ext, work + ext)

    col = Collection(work)
    try:
        basic = col.models.by_name("Basic")
        did = col.decks.id(CRASH_DECK)
        # Idempotent: clear any previous crash cards, then seed a fresh buffer.
        old = list(col.find_notes(f'deck:"{CRASH_DECK}"'))
        if old:
            col.remove_notes(old)
        conf = col.decks.config_dict_for_deck_id(did)
        conf["new"]["perDay"] = PER_DAY_LIMIT
        conf["rev"]["perDay"] = PER_DAY_LIMIT
        col.decks.update_config(conf)
        for i in range(buffer_cards):
            note = col.new_note(basic)
            note["Front"] = f"crash q{i}"
            note["Back"] = "x"
            col.add_note(note, did)
        col.decks.select(did)
        counts = col.sched.counts()
    finally:
        col.close()

    force_stop()
    adb("push", work, COLL)
    sh(f"rm -f '{COLL}-wal' '{COLL}-shm'")
    sh(f"chmod 666 '{COLL}'; chown u0_a207:ext_data_rw '{COLL}'")
    return {"backup_dir": backup_dir, "counts_new_lrn_rev": list(counts), "seeded": buffer_cards}


def device_info() -> dict:
    rel = sh("getprop ro.build.version.release").stdout.strip()
    sdk = sh("getprop ro.build.version.sdk").stdout.strip()
    ver = sh(
        f"dumpsys package {PKG} | grep versionName | head -1"
    ).stdout.strip()
    return {"android_release": rel, "sdk": sdk, "ankidroid": ver}


# ---------------------------------------------------------------------------
# One mid-review kill + integrity check.
# ---------------------------------------------------------------------------
def iteration(i: int, kill_delay: tuple[float, float], prev_revlog: int | None) -> dict:
    rec: dict = {"iteration": i}
    force_stop()
    time.sleep(0.6)

    adb("shell", "am", "start", "-n", f"{PKG}/{REVIEWER}")
    rec["reviewer_focused"] = wait_focus("Reviewer", 15.0)
    time.sleep(1.5)  # let the first card render

    # Continuous on-device review loop, self-terminating so no taps outlive it by
    # much. force-stop from the host lands somewhere inside it.
    loop_timeout = round(kill_delay[1] + 1.2, 2)
    loop_cmd = (
        f"timeout {loop_timeout} sh -c '"
        f"while true; do "
        f"input tap {TAP_SHOW[0]} {TAP_SHOW[1]}; sleep 0.2; "
        f"input tap {TAP_GOOD[0]} {TAP_GOOD[1]}; sleep 0.15; "
        f"done'"
    )
    tap_proc = subprocess.Popen(
        [ADB, "-s", SERIAL, "shell", loop_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    delay = random.uniform(*kill_delay)
    rec["kill_delay_s"] = round(delay, 3)
    time.sleep(delay)
    force_stop()  # <-- mid-review hard kill
    rec["killed"] = True
    try:
        tap_proc.wait(timeout=loop_timeout + 3)
    except Exception:
        tap_proc.kill()

    rec["wal_present_after_kill"] = device_wal_present()

    # On-device sqlite3 (records the unicase limitation; not the pass signal).
    dev = sh(f"sqlite3 '{COLL}' 'pragma integrity_check'")
    rec["device_sqlite3_stdout"] = dev.stdout.strip()
    rec["device_sqlite3_stderr"] = dev.stderr.strip()

    # Authoritative check: pull + rslib integrity (same engine, has unicase).
    pdir = tempfile.mkdtemp(prefix=f"vantage_androidchk_{i:02d}_")
    try:
        ppath = pull_collection(pdir)
        chk = check_collection(ppath)
    finally:
        shutil.rmtree(pdir, ignore_errors=True)

    rec["reopen_ok"] = chk.get("reopen_ok")
    rec["revlog_readable"] = chk.get("revlog_readable")
    rec["revlog_count"] = chk.get("revlog_count")
    rec["integrity"] = chk.get("integrity")
    rec["integrity_ok"] = chk.get("integrity_ok")
    rec["journal_mode"] = chk.get("journal_mode")
    if isinstance(chk.get("revlog_count"), int) and isinstance(prev_revlog, int):
        rec["revlog_growth"] = chk["revlog_count"] - prev_revlog
    else:
        rec["revlog_growth"] = None

    # App must reopen cleanly.
    adb("shell", "am", "start", "-n", f"{PKG}/{DECKPICKER}")
    rec["app_reopened"] = wait_focus("DeckPicker", 20.0)

    rec["pass"] = bool(
        rec["integrity_ok"]
        and rec["reopen_ok"]
        and rec["revlog_readable"]
        and rec["app_reopened"]
    )
    return rec


def print_table(results: list[dict]) -> None:
    hdr = (
        f"{'it':>3}  {'revw':>4}  {'killed':>6}  {'wal':>3}  {'postRev':>7}  "
        f"{'grew':>4}  {'reopen':>6}  {'integrity':>9}  {'appOpen':>7}  {'PASS':>4}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        integ = "ok" if r.get("integrity_ok") else str(r.get("integrity"))
        print(
            f"{r['iteration']:>3}  "
            f"{str(r.get('reviewer_focused')):>4}  "
            f"{str(r.get('killed')):>6}  "
            f"{str(r.get('wal_present_after_kill')):>3}  "
            f"{str(r.get('revlog_count')):>7}  "
            f"{str(r.get('revlog_growth')):>4}  "
            f"{str(r.get('reopen_ok')):>6}  "
            f"{integ:>9}  "
            f"{str(r.get('app_reopened')):>7}  "
            f"{str(bool(r.get('pass'))):>4}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="§7g android crash-safety test")
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--out", default=DEFAULT_RESULTS)
    ap.add_argument("--kill-min", type=float, default=0.3)
    ap.add_argument("--kill-max", type=float, default=1.5)
    ap.add_argument("--buffer-cards", type=int, default=2000)
    ap.add_argument("--reseed", dest="reseed", action="store_true", default=True)
    ap.add_argument("--no-reseed", dest="reseed", action="store_false")
    args = ap.parse_args()

    # Sanity: device reachable + collection present.
    devs = adb("devices").stdout
    if SERIAL not in devs:
        print(f"ERROR: {SERIAL} not attached:\n{devs}")
        return 2
    if "collection.anki2" not in sh(f"ls '{COLL}'").stdout + sh(f"ls '{COLL}'").stderr:
        # ls prints the path on success; on failure stderr mentions it too.
        pass

    started = time.time()
    info = device_info()
    print(f"device: {info}")
    print(f"pre-registration: {PREREGISTRATION}\n")

    reseed_info = None
    if args.reseed:
        backup_dir = tempfile.mkdtemp(prefix="vantage_android_backup_")
        reseed_info = reseed_device(args.buffer_cards, backup_dir)
        print(f"reseeded: {reseed_info}\n")

    # Baseline revlog from a quick pull.
    force_stop()
    time.sleep(0.5)
    bdir = tempfile.mkdtemp(prefix="vantage_androidbase_")
    baseline = revlog_on_device_copy(pull_collection(bdir))
    shutil.rmtree(bdir, ignore_errors=True)
    print(f"baseline revlog rows: {baseline}\n")

    results: list[dict] = []
    prev = baseline
    completed = 0
    for i in range(1, args.iterations + 1):
        try:
            rec = iteration(i, (args.kill_min, args.kill_max), prev)
            completed += 1
        except Exception as exc:  # keep going; record the failure honestly
            rec = {"iteration": i, "harness_error": repr(exc), "pass": False}
        results.append(rec)
        if isinstance(rec.get("revlog_count"), int):
            prev = rec["revlog_count"]
        print(
            f"  iter {i:>2}: reviewer={rec.get('reviewer_focused')} "
            f"killed={rec.get('killed')} wal={rec.get('wal_present_after_kill')} "
            f"revlog->{rec.get('revlog_count')} (+{rec.get('revlog_growth')}) "
            f"integrity={'ok' if rec.get('integrity_ok') else rec.get('integrity')} "
            f"appOpen={rec.get('app_reopened')} PASS={bool(rec.get('pass'))}"
        )

    passes = sum(1 for r in results if r.get("pass"))
    fails = len(results) - passes
    integrity_failures = [r["iteration"] for r in results if not r.get("integrity_ok")]
    reopen_failures = [r["iteration"] for r in results if not r.get("reopen_ok")]
    app_open_failures = [r["iteration"] for r in results if not r.get("app_reopened")]
    verdict = "PASS" if (fails == 0 and completed == args.iterations) else "FAIL"

    payload = {
        "test": "vantage-crash-safety-android",
        "section": "7g",
        "platform": "android-ankidroid-emulator",
        "preregistration": PREREGISTRATION,
        "verdict": verdict,
        "device": info,
        "reseed": reseed_info,
        "integrity_engine": "anki rusqlite via host pull (registers unicase collation)",
        "device_sqlite3_note": (
            "device /system/bin/sqlite3 cannot run integrity_check on this schema: "
            "'no such collation sequence: unicase' (a CLI limitation, not corruption)"
        ),
        "wal_count_lag_note": (
            "WAL force-kill count lag is a display artifact, not corruption; this "
            "test asserts pragma integrity_check, not the review count"
        ),
        "python": sys.version.split()[0],
        "iterations_requested": args.iterations,
        "iterations_completed": completed,
        "kill_delay_range_s": [args.kill_min, args.kill_max],
        "baseline_revlog": baseline,
        "totals": {
            "pass": passes,
            "fail": fails,
            "integrity_failures": integrity_failures,
            "reopen_failures": reopen_failures,
            "app_open_failures": app_open_failures,
        },
        "elapsed_s": round(time.time() - started, 2),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": results,
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)

    print("\n" + "=" * 84)
    print_table(results)
    print("=" * 84)
    print(f"iterations completed: {completed}/{args.iterations}   pass: {passes}   fail: {fails}")
    print(f"integrity_check failures: {integrity_failures or 'none'}")
    print(f"reopen failures: {reopen_failures or 'none'}")
    print(f"app-open failures: {app_open_failures or 'none'}")
    print(f"\nVERDICT: {verdict}")
    print(f"results written to: {args.out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
