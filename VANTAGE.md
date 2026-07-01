# Vantage (MCAT readiness, built on Anki)

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

## Key commits (this repo)

- Rust interleaving change: `207318a19` (write-up: [RUST_CHANGE_NOTE.md](RUST_CHANGE_NOTE.md))
- Honest scoring layer (`anki.vantage`): `657999553`
- Dashboard UI add-on (`vantage_addon`): `7886d4799`

## Where things live (this repo)

- `rslib/src/scheduler/queue/builder/interleave.rs` : the interleaving algorithm + Rust tests
- `pylib/anki/vantage/` : scoring (memory / performance / readiness), coverage map, give-up rule, tests
- `vantage_addon/` : the desktop dashboard (opens from the Tools menu or the "Vantage" toolbar link)

Built on Anki; licensed AGPL-3.0-or-later as upstream. Credit to Ankitects and the AnkiDroid team.
