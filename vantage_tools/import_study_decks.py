#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Import the MileDown + Mr. Pankow study decks and adapt them to Vantage.

Replaces the synthetic demo cards with the real community decks and makes the
coverage/section scoring attribute them correctly:

  * MileDown ships rich `MileDown::<Subject>::<Subtopic>` tags. Its subtopics
    already resolve to AAMC concepts through the outline aliases (28/31 concepts),
    and the topic->category rollup in collect.gather closes the rest, so MileDown
    needs no retagging: Physics/Gen-Chem/OChem -> Chem/Phys, Biology/Biochem ->
    Bio/Biochem, Behavioral -> Psych/Soc all follow from its own tags.
  * Pankow ships UNtagged, organized by subdeck (e.g. "P/S Deck::MrPankow 6A",
    "P/S Deck::8C::Social Behavior"). We read the AAMC code from the subdeck name
    and add `mcat::psych_soc::<code>` so it counts toward Psych/Soc coverage.
    Pankow's "9C" (social inequality) maps to AAMC 10A.

The synthetic demo notes (the only pre-existing `mcat::` cards) are captured
BEFORE import and removed at the end when --remove-demo is set.

Re-run:
  out/pyenv/bin/python vantage_tools/import_study_decks.py \\
    --collection "$HOME/Library/Application Support/Anki2/User 1/collection.anki2" \\
    --miledown "$HOME/Downloads/MileDown's MCAT Anki Deck.apkg" \\
    --pankow "$HOME/Downloads/Mr_Pankow_P_S Deck.apkg" --remove-demo
"""

from __future__ import annotations

import argparse
import re

from anki.collection import Collection

# Pankow subdeck AAMC code -> Vantage concept id(s). "9C" is Pankow's label for
# social inequality, which AAMC calls 10A.
PANKOW_CODES: dict[str, list[str]] = {
    "6A": ["6A"], "6B": ["6B"], "6C": ["6C"],
    "7A": ["7A"], "7B": ["7B"], "7C": ["7C"],
    "8A": ["8A"], "8B": ["8B"], "8C": ["8C"],
    "9A": ["9A"], "9B": ["9B"], "9C": ["10A"], "10A": ["10A"],
}
_CODE_RE = re.compile(r"(\d+[A-Z])(?:/(\d+[A-Z]))?")

# MileDown's top-level subject -> Vantage section. Its subtopics already drive
# coverage via the outline aliases; this section tag is what the in-dashboard
# section study queue (which filters on mcat::<section>::) reads.
MILEDOWN_SECTION: dict[str, str] = {
    "Physics": "chem_phys",
    "General_Chemistry": "chem_phys",
    "OChem": "chem_phys",
    "All_MCAT_Equations": "chem_phys",
    "Biology": "bio_biochem",
    "Biochemistry": "bio_biochem",
    # MileDown::Behavioral is intentionally NOT mapped: Psych/Soc study is Pankow's
    # job here, so MileDown's Behavioral cards stay out of the P/S study queue
    # (they still count toward P/S coverage via the outline aliases).
}


def retag_miledown(col: Collection) -> int:
    """Add mcat::<section>::miledown to each MileDown note, by its subject tag, so
    the section study queue serves them (coverage already works via aliases)."""
    retagged = 0
    for nid in col.find_notes("tag:MileDown::*"):
        note = col.get_note(nid)
        secs = set()
        for t in note.tags:
            if t.startswith("MileDown::"):
                parts = t.split("::")
                if len(parts) > 1:
                    sec = MILEDOWN_SECTION.get(parts[1])
                    if sec:
                        secs.add(sec)
        add = [f"mcat::{s}::miledown" for s in secs if f"mcat::{s}::miledown" not in note.tags]
        if add:
            note.tags.extend(add)
            col.update_note(note)
            retagged += 1
    return retagged


# Appended to each note type's CSS so imported cards render like the app on BOTH
# desktop native review AND AnkiDroid (which the web reviewer's overrides can't
# reach). Theme-safe: it does NOT force background/text colors, so AnkiDroid night
# mode still works; it only kills source-deck backgrounds, normalizes the font and
# size, caps images, and hides Khan-Academy/YouTube links. Marker keeps it idempotent.
RESTYLE_MARKER = "/* vantage-clean */"
RESTYLE_CSS = (
    "\n" + RESTYLE_MARKER + "\n"
    ".card{background-image:none!important;"
    "font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,sans-serif!important;"
    "font-size:17px!important;line-height:1.55!important}\n"
    ".card *{font-family:inherit!important;background-image:none!important;max-width:100%!important}\n"
    # Equation/prompt images (the card's Text field) stay small; explanation diagrams
    # (MileDown puts them in Extra, wrapped in #extra) get a bigger box so their small
    # labels stay readable. Aspect ratio preserved throughout.
    ".card img{max-width:min(100%,200px)!important;max-height:150px!important;"
    "height:auto!important;width:auto!important}\n"
    ".card #extra img{max-width:min(100%,480px)!important;max-height:460px!important}\n"
    '.card a[href*="khan"],.card a[href*="youtu"]{display:none!important}\n'
    ".card .cloze{font-weight:700}\n"
)


def restyle_notetypes(col: Collection) -> int:
    """Apply the Vantage-clean CSS to every note type. The block is always appended
    last, so truncating at the marker and reappending makes re-runs UPDATE it (not
    duplicate or skip)."""
    mm = col.models
    n = 0
    for nt in mm.all():
        css = nt.get("css", "")
        idx = css.find(RESTYLE_MARKER)
        base = (css[:idx] if idx != -1 else css).rstrip()
        new = base + RESTYLE_CSS
        if new != css:
            nt["css"] = new
            mm.update_dict(nt)
            n += 1
    return n


def _import(col: Collection, path: str) -> None:
    from anki.collection import ImportAnkiPackageOptions, ImportAnkiPackageRequest

    col.import_anki_package(
        ImportAnkiPackageRequest(package_path=path, options=ImportAnkiPackageOptions())
    )


def retag_pankow(col: Collection) -> int:
    """Tag every Pankow card with mcat::psych_soc::<code> from its subdeck name."""
    retagged = 0
    for d in col.decks.all_names_and_ids():
        if "P/S Deck" not in d.name:
            continue
        m = _CODE_RE.search(d.name)
        concepts: list[str] = []
        if m:
            for code in (m.group(1), m.group(2)):
                if code:
                    concepts += PANKOW_CODES.get(code, [])
        tags = [f"mcat::psych_soc::{c}" for c in concepts] or ["mcat::psych_soc"]
        for cid in col.decks.cids(d.id, children=False):
            note = col.get_card(cid).note()
            add = [t for t in tags if t not in note.tags]
            if add:
                note.tags.extend(add)
                col.update_note(note)
                retagged += 1
    return retagged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--miledown")
    ap.add_argument("--pankow")
    ap.add_argument("--remove-demo", action="store_true")
    ap.add_argument(
        "--retag-only",
        action="store_true",
        help="skip import/removal; only (re)apply the section tags + note-type restyle",
    )
    ap.add_argument(
        "--restyle-only",
        action="store_true",
        help="only append the Vantage-clean CSS to note types (for desktop + AnkiDroid)",
    )
    args = ap.parse_args()

    col = Collection(args.collection)
    try:
        if args.restyle_only:
            print(f"restyled {restyle_notetypes(col)} note types")
        elif args.retag_only:
            md, pk = retag_miledown(col), retag_pankow(col)
            print(f"tagged {md} MileDown + {pk} Pankow; restyled {restyle_notetypes(col)} note types")
        else:
            demo = list(col.find_notes("tag:mcat::*"))  # capture BEFORE import/retag
            before = col.card_count()
            print(f"start: {before} cards, {len(demo)} existing demo (mcat::) notes")
            _import(col, args.miledown)
            print("imported MileDown")
            _import(col, args.pankow)
            print("imported Pankow")
            after = col.card_count()
            print(f"after import: {after} cards (+{after - before})")
            md, pk = retag_miledown(col), retag_pankow(col)
            print(f"tagged {md} MileDown + {pk} Pankow; restyled {restyle_notetypes(col)} note types")
            if args.remove_demo and demo:
                col.remove_notes(demo)
                print(f"removed {len(demo)} demo notes")
        print(f"final: {col.card_count()} cards")
    finally:
        col.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
