#!/usr/bin/env bash
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Keep the bundled AnkiDroid mobile page in step with the desktop web sources.
#
# The mobile dashboard/practice page
# (anki-android/AnkiDroid/src/main/assets/vantage/index.html) is GENERATED from
# vantage_addon/web/* by render.build_mobile_page. When those sources change and
# the asset is not regenerated (and the APK not rebuilt), the phone silently
# drifts behind the desktop. This is the guard against that.
#
# Staleness reuses build_mobile_asset.py's existing fingerprint: its --check
# regenerates the page in memory and compares the sha256 to the bundled asset on
# disk, so the check can never disagree with the real regenerator.
#
#   current -> report and exit 0
#   stale   -> regenerate the asset (cheap, deterministic, safe) and report that
#              an APK rebuild + reinstall is still needed
#
# Deliberately NOT run by default: gradle + adb. They are slow, need a device, and
# have side effects, so the default only touches the asset. Pass --build to also
# rebuild the playDebug APK and install it on a connected device.
#
# Usage:
#   vantage_tools/sync_mobile.sh           # check, and auto-regenerate the asset if stale
#   vantage_tools/sync_mobile.sh --build   # the above, then gradle assemblePlayDebug + adb install
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANKI_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECTS="$(cd "$ANKI_REPO/.." && pwd)"
MOBILE_REPO="$PROJECTS/anki-android"
ASSET="$MOBILE_REPO/AnkiDroid/src/main/assets/vantage/index.html"
BUILD_PY="$ANKI_REPO/vantage_tools/build_mobile_asset.py"

DO_BUILD=0
if [ "${1:-}" = "--build" ]; then
  DO_BUILD=1
elif [ -n "${1:-}" ]; then
  echo "usage: $(basename "$0") [--build]" >&2
  exit 64
fi

echo "[sync_mobile] checking the bundled mobile asset against the current web sources..."
if python3 "$BUILD_PY" --check; then
  STALE=0
  echo "[sync_mobile] asset is current: mobile matches the desktop web sources."
else
  STALE=1
  echo "[sync_mobile] asset was STALE. Regenerating from current web sources..."
  python3 "$BUILD_PY"
  echo "[sync_mobile] asset was stale, regenerated. APK rebuild and reinstall still needed."
fi

if [ "$DO_BUILD" -eq 0 ]; then
  if [ "$STALE" -eq 1 ]; then
    echo "[sync_mobile] next: rebuild the APK (re-run with --build, or build playDebug in Android Studio) so a device sees the change."
  fi
  exit 0
fi

# ---- opt-in: rebuild the playDebug APK and install it on a device ----
echo "[sync_mobile] --build: rebuilding the playDebug APK..."

# JDK: prefer a set JAVA_HOME, else the project-local JDK 17 the repo builds with.
if [ -z "${JAVA_HOME:-}" ] || [ ! -x "${JAVA_HOME:-}/bin/java" ]; then
  for cand in "$PROJECTS"/android-tools/jdk-17*/Contents/Home; do
    if [ -x "$cand/bin/java" ]; then export JAVA_HOME="$cand"; break; fi
  done
fi
if [ -z "${JAVA_HOME:-}" ] || [ ! -x "${JAVA_HOME}/bin/java" ]; then
  echo "[sync_mobile] ERROR: no JDK 17 found. Set JAVA_HOME to a JDK 17 and retry." >&2
  exit 2
fi
echo "[sync_mobile] JAVA_HOME=$JAVA_HOME"

# Android SDK: gradle reads anki-android/local.properties (sdk.dir) on its own;
# mirror it into ANDROID_HOME so adb below resolves without a global install.
if [ -z "${ANDROID_HOME:-}" ]; then
  sdkdir="$(sed -n 's/^sdk\.dir=//p' "$MOBILE_REPO/local.properties" 2>/dev/null | head -1)"
  [ -n "$sdkdir" ] && export ANDROID_HOME="$sdkdir"
fi
ADB="adb"
if [ -n "${ANDROID_HOME:-}" ] && [ -x "$ANDROID_HOME/platform-tools/adb" ]; then
  ADB="$ANDROID_HOME/platform-tools/adb"
fi

( cd "$MOBILE_REPO" && ./gradlew :AnkiDroid:assemblePlayDebug )

APK_DIR="$MOBILE_REPO/AnkiDroid/build/outputs/apk/play/debug"
# Install the split APK matching the connected device's primary ABI; arm64 default.
abi="$("$ADB" shell getprop ro.product.cpu.abi 2>/dev/null | tr -d '\r' || true)"
[ -n "$abi" ] || abi="arm64-v8a"
apk="$APK_DIR/AnkiDroid-play-$abi-debug.apk"
[ -f "$apk" ] || apk="$APK_DIR/AnkiDroid-play-arm64-v8a-debug.apk"
echo "[sync_mobile] installing $apk (device abi: $abi)"
"$ADB" install -r "$apk"
echo "[sync_mobile] done: playDebug APK rebuilt and installed."
