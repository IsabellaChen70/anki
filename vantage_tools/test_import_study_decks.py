# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Regression tests for the Vantage-clean color-contrast override.

The earlier RESTYLE_CSS block whitened the card and recolored clozes but left
nested inline colors (``<font color="#...">`` and ``style="color: rgb(...)"``)
untouched. Those were authored for a dark background, so on the new white
surface they became near-invisible (yellow ~1.1:1, cyan ~1.25:1, even white
text). These tests pin the fix: every low-contrast inline color is darkened to
>= 4.5:1 on white while its hue is preserved, and already-legible colors are
left alone.
"""

from __future__ import annotations

import colorsys
import importlib.util
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOD_PATH = os.path.join(_HERE, "import_study_decks.py")
_spec = importlib.util.spec_from_file_location("import_study_decks", _MOD_PATH)
isd = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(isd)

TARGET = isd.CONTRAST_TARGET


def _contrast(token: str) -> float:
    rgb = isd._parse_color(token)
    assert rgb is not None, token
    return isd._contrast_on_white(rgb)


def _hue(rgb):
    r, g, b = (c / 255 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)[0]


# The worst real offenders sampled from the imported decks, by both mechanisms.
INVISIBLE = [
    "#ffffff",  # white text -> 1.00:1, fully invisible
    "#ffff0a",  # yellow -> 1.07:1
    "#eaf000",  # yellow-green -> 1.24:1
    "#00ffff",  # cyan -> 1.25:1
    "#21ff06",  # green -> 1.37:1
    "#ffc0fe",  # light pink -> 1.48:1
    "#fa8277",  # salmon -> 2.46:1
    "#ff0004",  # red -> 4.00:1 (just under AA)
    "rgb(0, 255, 255)",  # cyan via inline style
    "rgb(223, 216, 9)",  # yellow via inline style
    "rgb(250, 130, 119)",  # salmon via inline style
]

# Colors that already clear AA on white and must be preserved unchanged.
LEGIBLE = [
    "#132aff",  # blue -> 7.49:1
    "#090000",  # near-black -> ~20:1
    "rgb(128, 0, 128)",  # purple -> 9.42:1
    "#195ab3",  # blue -> 6.66:1 (the one operon color)
]


def test_contrast_helper_matches_wcag_anchors():
    assert round(isd._contrast_on_white((0, 0, 0)), 1) == 21.0
    assert round(isd._contrast_on_white((255, 255, 255)), 2) == 1.0


def test_invisible_colors_are_darkened_to_aa():
    for tok in INVISIBLE:
        rgb = isd._parse_color(tok)
        darker = isd._darken_for_white(rgb)
        c = isd._contrast_on_white(darker)
        assert c >= TARGET, f"{tok} -> {darker} only {c:.2f}:1"


def test_darkening_preserves_hue_for_chromatic_colors():
    for tok in INVISIBLE:
        rgb = isd._parse_color(tok)
        # skip achromatic (white/gray): hue is meaningless there
        _, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        if s < 0.15:
            continue
        darker = isd._darken_for_white(rgb)
        dh = abs(_hue(rgb) - _hue(darker))
        dh = min(dh, 1 - dh)  # hue is circular
        assert dh < 0.04, f"{tok}: hue drifted {dh:.3f}"


def test_overrides_target_invisible_and_skip_legible():
    fonts = {"#ffffff", "#ffff0a", "#00ffff", "#ffc0fe", "#132aff", "#195ab3"}
    styles = {"rgb(0, 255, 255)", "rgb(223, 216, 9)", "rgb(128, 0, 128)"}
    css = isd._overrides_for_tokens(fonts, styles)
    # low-contrast font colors get a scoped, !important, hue-darkened rule
    assert '[color="#00ffff"' in css
    assert '[color="#ffffff"' in css
    assert '[color="#ffff0a"' in css
    assert "!important" in css
    # low-contrast inline-style colors get a rule too
    assert 'color: rgb(223, 216, 9)' in css or 'rgb(223, 216, 9)' in css
    # already-legible colors are NOT touched (no rule emitted)
    assert "#132aff" not in css
    assert "#195ab3" not in css
    assert "rgb(128, 0, 128)" not in css


def test_overrides_scope_to_card_and_mobile():
    css = isd._overrides_for_tokens({"#00ffff"}, set())
    assert ".card " in css
    assert ".mobile .card " in css


def test_full_restyle_block_is_idempotent_and_marked():
    block = isd.RESTYLE_CSS + isd._overrides_for_tokens({"#00ffff"}, set())
    assert isd.RESTYLE_MARKER in block


# The imported decks' OWN note-type CSS (sampled verbatim from the collection).
DECK_CSS = (
    ".card { color: #D7DEE9; background-color: #333B45; }\n"
    ".cloze, .cloze b, .cloze u, .cloze i { font-weight: bold; color: #00F6D1 !important;}\n"
    "#extra, #extra i { font-size: 15px; color:#D7DEE9; }\n"
    "b { color: #ffc9ff !important; }\n"
    "u { text-decoration: none; color: #7EF7F1;}\n"
    "i  { color: lightsalmon; }\n"
    "a { color: LightGray !important; }\n"
    ".card2 { color: white; }\n"
    "--active-shape-color: #ff8e8e;\n"
)


def test_deck_css_low_contrast_colors_are_darkened():
    out = isd._darken_css_colors(DECK_CSS)
    # every remaining `color:` VALUE (not background/custom-prop) clears the floor
    for m in re.finditer(r"(?<![-\w])color\s*:\s*([^;}{]+)", out):
        val = re.sub(r"!\s*important", "", m.group(1)).strip()
        rgb = isd._parse_color(val)
        assert rgb is not None, f"unparsed after darkening: {val!r}"
        c = isd._contrast_on_white(rgb)
        assert c >= isd.CONTRAST_TARGET, f"{val} only {c:.2f}:1"


def test_deck_css_transform_preserves_important_and_background():
    out = isd._darken_css_colors(DECK_CSS)
    # !important flags survive so the darkened value keeps its precedence
    assert out.count("!important") == DECK_CSS.count("!important")
    # background-color and custom properties are never rewritten
    assert "background-color: #333B45" in out
    assert "--active-shape-color: #ff8e8e" in out


def test_deck_css_transform_is_idempotent():
    once = isd._darken_css_colors(DECK_CSS)
    twice = isd._darken_css_colors(once)
    assert once == twice


# --- gray DEFAULT body text (the "All electrons are paired..." report) ---------
# The decks color their whole surface's default text a light gray/blue-gray
# (#D7DEE9, #A6ABB9, LightGray, even white) for the dark theme. On the white card
# that text is near-invisible. It carries no color coding, so it must read the same
# near-black body color as the rest of the sentence -- NOT a hue-darkened slate.
BODY = (17, 24, 39)  # #111827, the .card body color


def _css_color_value(css_out: str) -> str:
    return re.search(r"(?<![-\w])color:\s*([^;}{]+)", css_out).group(1).strip()


def test_neutral_gray_default_snaps_to_body_color():
    for gray in ["#D7DEE9", "#A6ABB9", "LightGray", "#FFFFFF", "white", "silver",
                 "gainsboro", "rgb(215, 222, 233)", "hsl(210, 28%, 88%)"]:
        out = isd._darken_css_colors(f".x {{ color: {gray}; }}")
        rgb = isd._parse_color(_css_color_value(out))
        assert rgb == BODY, f"{gray} -> {rgb}, expected body {BODY}"


def test_electron_extra_gray_becomes_body_color():
    # The exact rule that made "All electrons are paired..." invisible.
    out = isd._darken_css_colors("#extra, #extra i { font-size: 15px; color:#D7DEE9; }")
    rgb = isd._parse_color(_css_color_value(out))
    assert rgb == BODY
    assert isd._contrast_on_white(rgb) >= isd.CONTRAST_TARGET


def test_chromatic_accents_are_not_flattened_to_body():
    # Real color coding must keep its own (darkened) hue, never collapse to the body.
    for accent in ["#6fbbbb", "#C695C6", "IndianRed", "MediumSeaGreen", "#00ffff"]:
        out = isd._darken_css_colors(f".x {{ color: {accent}; }}")
        rgb = isd._parse_color(_css_color_value(out))
        assert rgb != BODY, f"{accent} was flattened to body"
        assert isd._contrast_on_white(rgb) >= isd.CONTRAST_TARGET
        assert isd._chroma(rgb) > isd.NEUTRAL_MAX_CHROMA


def test_parse_color_handles_hsl_rgba_and_any_case():
    assert isd._parse_color("hsl(0, 100%, 50%)") == (255, 0, 0)
    assert isd._parse_color("HSL(120, 100%, 50%)") == (0, 255, 0)
    assert isd._parse_color("rgba(0, 255, 255, 0.5)") == (0, 255, 255)
    assert isd._parse_color("#D7DEE9") == isd._parse_color("#d7dee9")


def test_named_and_hsl_inline_colors_are_covered():
    # A named font color and an hsl() inline style both get a scoped rule.
    css = isd._overrides_for_tokens({"silver"}, {"hsl(180, 100%, 50%)"})
    assert '[color="silver" i]' in css
    assert 'hsl(180, 100%, 50%)' in css
    assert "!important" in css


# --- clear question/answer separator (hr#answer divider) ----------------------
# Anki separates the front (question) from the back (answer) with the template's
# <hr id="answer">. On the clean white card that default divider is faint, so the
# question and answer run together. RESTYLE_CSS must restyle it into an obvious
# line that hits BOTH desktop native review (.card) and AnkiDroid (.mobile .card),
# using !important so it beats the imported decks' own hr/.card rules. Scoped to
# hr#answer (the front/back divider) only, never a bare .card hr, so a note's own
# <hr> content is left alone.
def test_answer_separator_scoped_to_both_surfaces():
    css = isd.RESTYLE_CSS
    # a single rule covering desktop + AnkiDroid, matching the file's existing
    # ".card X,.mobile .card X" parity pattern (e.g. the .cloze rule)
    assert ".card hr#answer,.mobile .card hr#answer" in css
    # explicit per-surface checks for clearer failures
    assert ".mobile .card hr#answer" in css
    # scoped to the divider only, never a bare `.card hr` that would hit note content
    assert ".card hr{" not in css and ".card hr {" not in css


def test_answer_separator_draws_visible_important_line():
    css = isd.RESTYLE_CSS
    idx = css.find("hr#answer")
    assert idx != -1
    decl = css[css.find("{", idx) + 1 : css.find("}", idx)]
    # resets the default border and draws a distinct horizontal rule with generous
    # spacing, all forced over the decks' own hr styling
    assert "border-top" in decl, decl
    assert "margin" in decl, decl
    assert "!important" in decl, decl


def test_answer_separator_in_marked_idempotent_block():
    # the divider lives in the vantage-clean marked block, so restyle_notetypes
    # truncates + reappends it on re-run (stays idempotent).
    assert isd.RESTYLE_MARKER in isd.RESTYLE_CSS
    assert "hr#answer" in isd.RESTYLE_CSS
