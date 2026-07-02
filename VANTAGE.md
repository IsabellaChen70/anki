# Vantage (MCAT readiness, built on Anki)

**Exam: MCAT** (Medical College Admission Test), scored 472 to 528 across four
sections (Chem/Phys, CARS, Bio/Biochem, Psych/Soc), each on a 118 to 132 scale.

Vantage is a desktop + Android study app built on a fork of Anki. It keeps Anki's
FSRS spaced repetition and adds a topic-interleaving review order (in the shared
Rust core), plus an honest readiness layer: three separate scores (memory,
performance, readiness), each with a range, and a give-up rule that refuses a
number when the evidence is thin.

## One engine, three repositories

Anki desktop and AnkiDroid are separate upstream projects, so the work spans
three forks. The shared engine is the Rust core (`rslib`): the interleaving
change lives here, and the phone runs that same code compiled for Android.

| Repo | Branch | Contains |
| --- | --- | --- |
| [IsabellaChen70/anki](https://github.com/IsabellaChen70/anki/tree/vantage/interleaving) | `vantage/interleaving` | Desktop: interleaving in `rslib`, the `anki.vantage` scoring layer (`pylib`), and the `vantage_addon` dashboard UI |
| [IsabellaChen70/Anki-Android](https://github.com/IsabellaChen70/Anki-Android/tree/vantage/dashboard) | `vantage/dashboard` | Phone app: the Vantage dashboard screen (matches the desktop UI) |
| [IsabellaChen70/Anki-Android-Backend](https://github.com/IsabellaChen70/Anki-Android-Backend/tree/vantage/interleaving) | `vantage/interleaving` | Builds the phone's Rust engine from this fork's interleaving (25.09.2 port on `vantage/interleaving-droid`) |

## Install on a clean Mac (no build, no dev tools)

For someone who just wants to run Vantage. You need two files (attached to the
[latest release](https://github.com/IsabellaChen70/anki/releases); GitHub can't
store the 220&nbsp;MB installer in the repo itself):

- `anki-26.05-mac-apple.dmg` — the app (Anki + the Vantage interleaving engine, Python and Qt bundled in)
- `vantage.ankiaddon` — the Vantage dashboard add-on

1. **Install the app.** Open the `.dmg`, drag **Anki** into **Applications**, and launch it. The build is unsigned, so the first launch needs Gatekeeper's okay: right-click **Anki.app → Open → Open** (or System Settings → Privacy & Security → **Open Anyway**).
2. **Install Vantage.** With Anki running, double-click `vantage.ankiaddon` (or **Tools → Add-ons → Install from file…**), then restart Anki.
3. The **Vantage dashboard opens automatically** at startup. You can also reopen it from the Tools menu, the "Vantage" toolbar link, or Cmd+Shift+V.

The add-on is self-contained (it bundles its own scoring core under `vantage_core/`), so it also runs on a stock Anki install of the same version.

## Build and run

**Desktop (this repo).** Needs Rust, Python 3.13, and Node/Yarn; the bundled
`./ninja` fetches the rest.

- Run from source: `./run`
- Build the macOS installer: `./tools/build-installer` (output in `out/installer/dist/`)
- Dashboard: symlink `vantage_addon` into your Anki `addons21` folder, then open it
  from the Tools menu, the "Vantage" toolbar link, or Ctrl/Cmd+Shift+V.
- Rebuild the demo exam deck (real FSRS reviews): `out/pyenv/bin/python vantage_tools/build_exam_collection.py OUT.anki2`

**Android.** Needs JDK 21 and the Android SDK + NDK.

- Engine ([Anki-Android-Backend](https://github.com/IsabellaChen70/Anki-Android-Backend/tree/vantage/interleaving), `vantage/interleaving`): build the interleaving Rust core into the `rsdroid` AAR with `cargo run -p build_rust`.
- App ([Anki-Android](https://github.com/IsabellaChen70/Anki-Android/tree/vantage/dashboard), `vantage/dashboard`): set `local.properties` to `sdk.dir=<sdk>` and `local_backend=true`, then `./gradlew :AnkiDroid:assemblePlayDebug`. Install the matching split, e.g. `adb install -r AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk`.
- Dashboard: DeckPicker overflow menu, "Vantage".

## Key commits (this repo)

- Rust interleaving change: `207318a19` (write-up: [RUST_CHANGE_NOTE.md](RUST_CHANGE_NOTE.md))
- Honest scoring layer (`anki.vantage`): `657999553`
- Dashboard UI add-on (`vantage_addon`): `7886d4799`

## Where things live (this repo)

- `rslib/src/scheduler/queue/builder/interleave.rs` : the interleaving algorithm + Rust tests
- `pylib/anki/vantage/` : scoring (memory / performance / readiness), coverage map, give-up rule, tests
- `vantage_addon/` : the desktop dashboard (opens from the Tools menu or the "Vantage" toolbar link)

## Backlog (planned, post-Wednesday)

- **CARS section, done honestly.** Add short CARS practice passages with questions, scored on real performance, never derived from flashcards. This is the missing "application item" layer, so it also lifts Performance and Readiness out of abstention and lets Readiness become a full 4-section 472 to 528 projection instead of a 3-section partial. Rationale: CARS is Anki's real blind spot (reasoning, not recall), so this is the highest-value differentiator.
- **Restyle the flashcard reviewer.** Theme Anki's FSRS review screen (card template CSS and an accent) so studying feels like part of Vantage. Cosmetic only: keep the real Again/Hard/Good/Easy FSRS grading and the shared engine.

Built on Anki; licensed AGPL-3.0-or-later as upstream. Credit to Ankitects and the AnkiDroid team.
