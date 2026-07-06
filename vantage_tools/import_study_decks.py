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
import colorsys
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
# reach). The imported community decks hardcode a dark card surface on `.card` AND
# the more-specific `.mobile .card` (the class AnkiDroid adds), so their dark
# background/text shows through even with the app's night mode OFF. This forces a
# clean light surface (white background, near-black text) on BOTH selectors with
# !important, recolors clozes and neutralizes the decks' light-on-dark emphasis
# accents so they stay legible on white, kills source-deck background images,
# normalizes the font and size, caps images, and hides Khan-Academy/YouTube links.
#
# The blanket rules above only cover the card surface, clozes, and the bold/italic
# emphasis tags. The decks ALSO color individual words with `<font color="#...">`
# and `style="color: rgb(...)"` picked for the original DARK background (bright
# yellow, cyan, pastel pink, even white). Those slip past the rules above and go
# near-invisible on white. build_color_overrides() scans the collection for every
# such inline color and appends a hue-preserving darkening map (see below), so the
# color coding survives while every word clears ~4.5:1 on white.
# Marker keeps it idempotent (restyle_notetypes truncates here and reappends).
RESTYLE_MARKER = "/* vantage-clean */"
RESTYLE_CSS = (
    "\n" + RESTYLE_MARKER + "\n"
    ".card{background-image:none!important;"
    "font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,sans-serif!important;"
    "font-size:17px!important;line-height:1.55!important}\n"
    # Force a clean light surface on BOTH .card and the more-specific .mobile .card:
    # AnkiDroid adds the .mobile class and the imported decks ship a dark `.mobile
    # .card`, so overriding .card alone is not enough. !important beats the decks' own
    # .card/.mobile .card rules regardless of their specificity or source order.
    ".card,.mobile .card{background-color:#ffffff!important;color:#111827!important}\n"
    # The front (question) and back (answer) are separated by the template's
    # <hr id="answer">. On the white card the default divider is faint, so the two
    # run together. Draw an obvious rule instead: reset the default border, then a
    # clear 2px slate line with generous vertical space so the answer visibly
    # detaches from the question. Scoped to hr#answer (the front/back divider) only,
    # NEVER a bare `.card hr` that would restyle an <hr> a note uses in its OWN
    # content, on BOTH .card and .mobile .card so desktop and AnkiDroid match.
    # !important beats the imported decks' own hr/.card styling regardless of source.
    ".card hr#answer,.mobile .card hr#answer{border:0!important;"
    "border-top:2px solid #94a3b8!important;height:0!important;margin:26px 0!important}\n"
    ".card *{font-family:inherit!important;background-image:none!important;max-width:100%!important}\n"
    # Equation/prompt images (the card's Text field) stay small; explanation diagrams
    # (MileDown puts them in Extra, wrapped in #extra) get a bigger box so their small
    # labels stay readable. Aspect ratio preserved throughout.
    ".card img{max-width:min(100%,200px)!important;max-height:150px!important;"
    "height:auto!important;width:auto!important}\n"
    ".card #extra img{max-width:min(100%,480px)!important;max-height:460px!important}\n"
    '.card a[href*="khan"],.card a[href*="youtu"]{display:none!important}\n'
    # The decks color clozes for a dark background (e.g. .cloze{color:#00F6D1!important})
    # which vanishes on white. A strong blue with higher specificity + !important + later
    # source order beats it on both surfaces. Emphasis tags (bold/italic/underline) are
    # light pastels on dark; make them inherit the near-black text so they stay readable.
    ".card .cloze,.mobile .card .cloze{color:#1d4ed8!important;font-weight:700!important}\n"
    ".card b,.card strong,.card i,.card em,.card u,"
    ".mobile .card b,.mobile .card strong,.mobile .card i,.mobile .card em,.mobile .card u"
    "{color:inherit!important}\n"
)

# WCAG AA contrast floor for normal-size body text. A darkened inline color must
# clear this against the white card before we consider it legible.
CONTRAST_TARGET = 4.5

# The card's body text color (MUST match the `.card{color:...}` value in RESTYLE_CSS
# below). A near-invisible NEUTRAL color (the decks' light-gray/blue-gray default
# text, e.g. #D7DEE9) is not a semantic accent, so instead of hue-darkening it into
# a tinted slate we snap it to this body color so the whole sentence reads uniformly,
# exactly like the rest of the card. Chromatic accents still keep their (darkened) hue.
BODY_TEXT = "#111827"
# Max chroma (max-min channel spread, 0..1) for a color to count as "neutral gray".
# #D7DEE9/#A6ABB9/lightgray sit at ~0.07; muted accents like #6fbbbb/#C695C6 sit at
# 0.19-0.30, so this cleanly separates gray defaults from real color coding.
NEUTRAL_MAX_CHROMA = 0.12

# Inline colors appear as the HTML `<font color=>` attribute or a `style="color: ..."`
# declaration. Both hex, rgb()/hsl() and named forms are matched (any case). The
# `(?<!-)` guard on the style form keeps it from matching background-color etc.
_FONT_COLOR_RE = re.compile(
    r'<font[^>]*\bcolor\s*=\s*"?(#[0-9a-fA-F]{3,6}|rgb\([^)]*\)|hsl\([^)]*\)|[a-zA-Z]+)',
    re.I,
)
_STYLE_COLOR_RE = re.compile(
    r"(?<!-)color:\s*(#[0-9a-fA-F]{3,6}|rgb\([^)]*\)|hsl\([^)]*\)|[a-zA-Z]+)", re.I
)

_NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
    "lime": (0, 255, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "aqua": (0, 255, 255),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "purple": (128, 0, 128),
    "orange": (255, 165, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "silver": (192, 192, 192), "maroon": (128, 0, 0), "olive": (128, 128, 0),
    "teal": (0, 128, 128), "navy": (0, 0, 128), "gold": (255, 215, 0),
    "pink": (255, 192, 203), "salmon": (250, 128, 114), "lightsalmon": (255, 160, 122),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "gainsboro": (220, 220, 220), "whitesmoke": (245, 245, 245),
    "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
    "lightblue": (173, 216, 230), "lightgreen": (144, 238, 144),
    "lightpink": (255, 182, 193), "lightyellow": (255, 255, 224),
    "lightcyan": (224, 255, 255), "mediumseagreen": (60, 179, 113),
    "seagreen": (46, 139, 87), "indianred": (205, 92, 92), "khaki": (240, 230, 140),
    "tan": (210, 180, 140), "violet": (238, 130, 238), "plum": (221, 160, 221),
    "skyblue": (135, 206, 235), "lightskyblue": (135, 206, 250),
    "greenyellow": (173, 255, 47), "aquamarine": (127, 255, 212),
    "turquoise": (64, 224, 208),
}


def _parse_color(token: str) -> tuple[int, int, int] | None:
    """Turn a `#rgb`, `#rrggbb`, `rgb()`, `hsl()`, or named color into an RGB triple."""
    t = token.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{6})", t)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.fullmatch(r"#([0-9a-f]{3})", t)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,.*)?\)", t)
    if m:
        return tuple(max(0, min(255, int(float(x)))) for x in m.groups())  # type: ignore[return-value]
    m = re.fullmatch(
        r"hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*(?:,.*)?\)", t
    )
    if m:
        h, s, ll = (float(x) for x in m.groups())
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, ll / 100.0, s / 100.0)
        return round(r * 255), round(g * 255), round(b * 255)
    return _NAMED_COLORS.get(t)


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.x relative luminance."""

    def lin(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_on_white(rgb: tuple[int, int, int]) -> float:
    """WCAG contrast ratio of `rgb` text against a white (#fff) background."""
    return (1.0 + 0.05) / (_rel_luminance(rgb) + 0.05)


def _hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken_for_white(
    rgb: tuple[int, int, int], target: float = CONTRAST_TARGET
) -> tuple[int, int, int]:
    """Darken `rgb` just enough to clear `target` contrast on white, keeping hue.

    Only lightness is lowered (hue and saturation are held), and we take the
    LIGHTEST value that still clears the floor so the color stays as vivid, and
    as distinguishable from its neighbors, as legibility allows. Black clears any
    target, so the loop always terminates.
    """
    h, l, s = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))
    steps = int(l / 0.02) + 2
    for i in range(steps):
        li = max(0.0, l - i * 0.02)
        cand = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, li, s))
        if _contrast_on_white(cand) >= target:  # type: ignore[arg-type]
            return cand  # type: ignore[return-value]
    return (0, 0, 0)


def _chroma(rgb: tuple[int, int, int]) -> float:
    """How colorful `rgb` is: the channel spread, normalized to 0..1 (0 == gray)."""
    return (max(rgb) - min(rgb)) / 255.0


def _readable_on_white(
    rgb: tuple[int, int, int], target: float = CONTRAST_TARGET
) -> tuple[int, int, int]:
    """Make a low-contrast color legible on white.

    NEUTRAL near-gray colors (the decks' light-gray/blue-gray DEFAULT text) carry no
    color coding, so snap them to the body text color instead of hue-darkening them
    into a tinted slate: the whole sentence then reads uniformly, matching the rest
    of the card. CHROMATIC accents keep their hue via hue-preserving darkening."""
    if _chroma(rgb) <= NEUTRAL_MAX_CHROMA:
        return _parse_color(BODY_TEXT)  # type: ignore[return-value]
    return _darken_for_white(rgb, target)


def _overrides_for_tokens(font_tokens: set[str], style_tokens: set[str]) -> str:
    """Build the scoped legibility rules for the given inline colors.

    Emits a rule ONLY for colors below the contrast floor; already-legible colors
    are left untouched so their coding is preserved verbatim. Neutral grays snap to
    the body color and chromatic accents are hue-darkened (see _readable_on_white).
    Each rule is scoped to `.card` and `.mobile .card` and uses !important so it beats
    the note's own inline color (an important stylesheet rule outranks a normal inline
    style)."""
    rules: list[str] = []
    for tok in sorted(font_tokens):
        rgb = _parse_color(tok)
        if rgb is None or _contrast_on_white(rgb) >= CONTRAST_TARGET:
            continue
        dark = _hex(_readable_on_white(rgb))
        rules.append(
            f'.card [color="{tok}" i],.mobile .card [color="{tok}" i]'
            f"{{color:{dark}!important}}"
        )
    for tok in sorted(style_tokens):
        rgb = _parse_color(tok)
        if rgb is None or _contrast_on_white(rgb) >= CONTRAST_TARGET:
            continue
        dark = _hex(_readable_on_white(rgb))
        # Match the raw color token (guaranteed present in the style attribute);
        # no note uses rgb()/hsl() anywhere but text color, so this cannot hit a
        # background. `i` flag keeps it case-insensitive.
        rules.append(
            f'.card [style*="{tok}" i],.mobile .card [style*="{tok}" i]'
            f"{{color:{dark}!important}}"
        )
    if not rules:
        return ""
    return (
        "/* vantage-clean nested-color contrast map: light inline colors authored\n"
        "   for the dark source deck (font color=, style color:) made legible on white\n"
        f"   (>= ~{CONTRAST_TARGET}:1): neutral grays -> body color, accents hue-darkened. */\n"
        + "\n".join(rules)
        + "\n"
    )


def _collect_inline_colors(col: Collection) -> tuple[set[str], set[str]]:
    """Scan every note field for inline `<font color=>` and `style="color:"` values."""
    fonts: set[str] = set()
    styles: set[str] = set()
    for row in col.db.all("SELECT flds FROM notes"):
        flds = row[0]
        if not flds or "color" not in flds.lower():
            continue
        for m in _FONT_COLOR_RE.finditer(flds):
            fonts.add(m.group(1).lower())
        for m in _STYLE_COLOR_RE.finditer(flds):
            styles.add(m.group(1).strip())
    return fonts, styles


def build_color_overrides(col: Collection) -> str:
    """Scan the collection and return the inline-color legibility CSS (neutral grays
    snapped to the body color, chromatic accents hue-darkened)."""
    fonts, styles = _collect_inline_colors(col)
    return _overrides_for_tokens(fonts, styles)


# Matches a `color:` PROPERTY (not background-color / border-color / --*-color, which
# are excluded by the lookbehind) and captures its value up to ; } or {.
_CSS_COLOR_DECL_RE = re.compile(r"(?<![-\w])color\s*:\s*([^;}{]+)", re.I)


def _darken_css_colors(css: str) -> str:
    """Darken every low-contrast text `color:` VALUE inside a note type's own CSS.

    The imported decks style whole classes for their dark surface (e.g.
    `#extra{color:#D7DEE9}`, `.cloze b{color:#00F6D1!important}`, `b{color:#ffc9ff}`)
    which the appended blanket rules can't reach because those selectors are more
    specific. Rewriting the VALUE in place (selector, specificity and !important all
    preserved) fixes class-colored text too: neutral gray defaults snap to the body
    color and chromatic accents are hue-preserved (see _readable_on_white).
    background-color and already-legible values are left untouched; the pass is
    idempotent (re-running finds dark values already above the floor and leaves them)."""

    def repl(m: re.Match) -> str:
        raw = m.group(1)
        imp = re.search(r"!\s*important", raw, re.I)
        value = raw[: imp.start()] if imp else raw
        rgb = _parse_color(value.strip())
        if rgb is None or _contrast_on_white(rgb) >= CONTRAST_TARGET:
            return m.group(0)
        dark = _hex(_readable_on_white(rgb))
        return f"color: {dark}{' !important' if imp else ''}"

    return _CSS_COLOR_DECL_RE.sub(repl, css)


def restyle_notetypes(col: Collection) -> int:
    """Apply the Vantage-clean CSS to every note type. Two contrast passes run:
    the note's OWN low-contrast text `color:` values are darkened in place, then the
    Vantage-clean block (plus the per-collection inline-color map) is appended after
    the marker. Truncating at the marker and reappending makes re-runs UPDATE the
    block (not duplicate or skip); both passes are idempotent."""
    mm = col.models
    overrides = build_color_overrides(col)
    n = 0
    for nt in mm.all():
        css = nt.get("css", "")
        idx = css.find(RESTYLE_MARKER)
        base = _darken_css_colors(css[:idx] if idx != -1 else css).rstrip()
        new = base + RESTYLE_CSS + overrides
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
