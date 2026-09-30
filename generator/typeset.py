"""Text as outlines, measured exactly.

The plates never emit <text>. Each string becomes a run of <use> elements
pointing at glyph outlines defined once per SVG, so the result looks the same
in every browser and rasteriser, and the generator knows how wide it is.

Outlines, advances and kerning come from generator/fonts/*.json (built by
tools/build_font_atlas.py). A string with a character outside that coverage
falls back, whole, to a <text> element in a system serif, and its width is
estimated.
"""

from __future__ import annotations

import json
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

from generator.svg import clean, esc, num

FONTS = Path(__file__).resolve().parent / "fonts"
STYLES = ("light", "regular", "medium", "italic")
FALLBACK_FAMILY = "Georgia, 'Times New Roman', serif"
ELLIPSIS = "…"
CUT_FILL = 2 / 3          # a cut line shorter than this share of the width is filled through the next word

# A fallback string is drawn in a system serif, which runs wider than Spectral.
FALLBACK_MARGIN = 1.15

_PREFIX = {"light": "l", "regular": "r", "medium": "m", "italic": "i"}
_FALLBACK_WEIGHT = {"light": ' font-weight="300"', "medium": ' font-weight="500"'}


@lru_cache(maxsize=None)
def font(style: str) -> dict:
    """The atlas for one style, with the average advance used to estimate uncovered text."""
    if style not in STYLES:
        raise ValueError(f"unknown text style '{style}'")
    atlas = json.loads((FONTS / f"spectral-{style}.json").read_text(encoding="utf-8"))
    lower = [atlas["glyphs"][c][0] for c in "abcdefghijklmnopqrstuvwxyz"]
    atlas["avg"] = sum(lower) / len(lower)
    return atlas


def covers(text: str, style: str = "regular") -> bool:
    glyphs = font(style)["glyphs"]
    return all(ch in glyphs for ch in text)


def _layout(text: str, atlas: dict) -> tuple[list[tuple[str, int]], int]:
    """Pen position of every character, and the total advance, in font units."""
    glyphs, kern = atlas["glyphs"], atlas["kern"]
    pens, pen, prev = [], 0, None
    for ch in text:
        if prev is not None:
            pen += kern.get(prev + ch, 0)
        pens.append((ch, pen))
        pen += glyphs[ch][0]
        prev = ch
    return pens, pen


def _is_wide(ch: str) -> bool:
    """CJK, fullwidth forms and emoji take a whole em."""
    code = ord(ch)
    return unicodedata.east_asian_width(ch) in ("W", "F") or code >= 0x1F000 or 0x2600 <= code <= 0x27BF


def measure(text: str, size: float, style: str = "regular") -> float:
    """Width of text in pixels at the given size.

    Exact when the font covers the text. Otherwise an estimate of how the
    fallback serif will set it: a full em for wide characters, and the known
    advances (or the average one) with a margin for the rest.
    """
    atlas, text = font(style), clean(text)
    if covers(text, style):
        units = _layout(text, atlas)[1]
    else:
        glyphs = atlas["glyphs"]
        units = sum(atlas["upm"] if _is_wide(ch)
                    else (glyphs[ch][0] if ch in glyphs else atlas["avg"]) * FALLBACK_MARGIN
                    for ch in text)
    return units * size / atlas["upm"]


def _ellipsize(line: str, size: float, style: str, max_width: float) -> str:
    line = line.rstrip()
    while line and measure(line + ELLIPSIS, size, style) > max_width:
        line = line[:-1].rstrip()
    return line + ELLIPSIS


def _balanced(words: list, size: float, style: str, max_width: float) -> list:
    """The two-line break that leaves the lines closest in width, preferring to break after punctuation."""
    best = None
    for cut in range(1, len(words)):
        first, second = " ".join(words[:cut]), " ".join(words[cut:])
        w1, w2 = measure(first, size, style), measure(second, size, style)
        if w1 > max_width or w2 > max_width:
            continue
        score = abs(w1 - w2) - (max_width * 0.25 if first[-1] in ",;:.!?" else 0)
        if best is None or score < best[0]:
            best = (score, [first, second])
    return best[1] if best else []


def wrap(text: str, size: float, style: str, max_width: float, max_lines: int = 2,
         balance: bool = False) -> list[str]:
    """Break text into lines no wider than max_width; the last line ends in an ellipsis if text was cut.

    A cut falls between words, unless that would leave the line less than
    two thirds full: then it goes on into the next word, so a long name keeps
    as many of its letters as fit. balance=True evens out a two-line result
    instead of leaving a lone word on the second line.
    """
    words = clean(text).split()
    if not words:
        return []

    def pieces(word: str) -> list[str]:
        """A word wider than the line is broken by characters (text without spaces, long names)."""
        if measure(word, size, style) <= max_width:
            return [word]
        out, piece = [], ""
        for ch in word:
            if piece and measure(piece + ch, size, style) > max_width:
                out.append(piece)
                piece = ch
            else:
                piece += ch
        return out + [piece]

    lines, current = [], ""
    for word in (piece for w in words for piece in pieces(w)):
        candidate = f"{current} {word}" if current else word
        if not current or measure(candidate, size, style) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if balance and len(lines) == 2 and max_lines >= 2:
        lines = _balanced(words, size, style, max_width) or lines
    if len(lines) > max_lines:
        between_words = _ellipsize(lines[max_lines - 1], size, style, max_width)
        if measure(between_words, size, style) >= max_width * CUT_FILL:
            lines[max_lines - 1:] = [between_words]
        else:
            lines[max_lines - 1:] = [_ellipsize(" ".join(lines[max_lines - 1:]), size, style, max_width)]
    return [line if measure(line, size, style) <= max_width else _ellipsize(line, size, style, max_width)
            for line in lines]


def _halo(halo, scale: float = 1.0) -> str:
    """Attributes for an outline painted behind the letters. halo is (colour, width in pixels, opacity).

    Outlined text is drawn in font units and scaled down, so there the width
    is divided by the scale; fallback <text> is drawn in pixels (scale 1).
    """
    if not halo:
        return ""
    colour, width, opacity = halo
    alpha = "" if opacity >= 1 else f' stroke-opacity="{num(opacity, 2)}"'
    return (f' stroke="{colour}" stroke-width="{num(width / scale)}"{alpha} stroke-linejoin="round" '
            f'paint-order="stroke"')


def _fallback(x: float, y: float, text: str, size: float, fill: str, style: str, anchor: str,
              attrs: str, transform: str = "") -> str:
    anchor_attr = "" if anchor == "start" else f' text-anchor="{anchor}"'
    italic = ' font-style="italic"' if style == "italic" else ""
    position = f' transform="{transform}"' if transform else f' x="{num(x)}" y="{num(y)}"'
    return (f'<text{position} font-family="{FALLBACK_FAMILY}" font-size="{num(size)}"'
            f'{_FALLBACK_WEIGHT.get(style, "")}{italic} fill="{fill}"{anchor_attr}{attrs}>{esc(text)}</text>')


class Typesetter:
    """Sets text for one SVG and remembers which glyph outlines it used."""

    def __init__(self) -> None:
        self._defs: dict[str, str] = {}

    def _glyph(self, style: str, ch: str, outline: str) -> str:
        gid = f"{_PREFIX[style]}{ord(ch):x}"
        self._defs.setdefault(gid, outline)
        return gid

    def line(self, x: float, y: float, text: str, size: float, fill: str, style: str = "regular",
             anchor: str = "start", attrs: str = "", halo=None) -> str:
        """One line of text with its baseline at y. anchor is start, middle or end.

        halo is (colour, width in pixels, opacity) for an outline behind the letters.
        """
        text = clean(text)
        if not text:
            return ""
        if not covers(text, style):
            return _fallback(x, y, text, size, fill, style, anchor, _halo(halo) + attrs)
        atlas = font(style)
        pens, total = _layout(text, atlas)
        scale = size / atlas["upm"]
        width = total * scale
        origin = x - (width if anchor == "end" else width / 2 if anchor == "middle" else 0)
        uses = []
        for ch, pen in pens:
            outline = atlas["glyphs"][ch][1]
            if not outline:
                continue
            gid = self._glyph(style, ch, outline)
            uses.append(f'<use href="#{gid}" x="{num(pen)}"/>' if pen else f'<use href="#{gid}"/>')
        return (f'<g transform="translate({num(origin)} {num(y)}) scale({num(scale, 4)})" '
                f'fill="{fill}"{_halo(halo, scale)}{attrs}>{"".join(uses)}</g>')

    def on_curve(self, points: list[tuple[float, float]], text: str, size: float, fill: str,
                 style: str = "italic", attrs: str = "", halo=None) -> str:
        """Text set glyph by glyph along a polyline, centred on its length. halo as in line()."""
        text = clean(text)
        if not text or len(points) < 2:
            return ""
        lengths = [0.0]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            lengths.append(lengths[-1] + math.hypot(bx - ax, by - ay))

        def at(s: float) -> tuple[float, float, float]:
            """Point and tangent angle (degrees) at arc length s, extended straight past either end."""
            i = 1
            while i < len(lengths) - 1 and lengths[i] < s:
                i += 1
            (ax, ay), (bx, by) = points[i - 1], points[i]
            seg = lengths[i] - lengths[i - 1] or 1.0
            t = (s - lengths[i - 1]) / seg
            return ax + (bx - ax) * t, ay + (by - ay) * t, math.degrees(math.atan2(by - ay, bx - ax))

        if not covers(text, style):
            mx, my, angle = at(lengths[-1] / 2)
            transform = f"translate({num(mx)} {num(my)}) rotate({num(angle)})"
            return _fallback(0, 0, text, size, fill, style, "middle", _halo(halo) + attrs, transform)

        atlas = font(style)
        pens, total = _layout(text, atlas)
        scale = size / atlas["upm"]
        start = (lengths[-1] - total * scale) / 2
        uses = []
        for ch, pen in pens:
            advance, outline = atlas["glyphs"][ch]
            if not outline:
                continue
            px, py, angle = at(start + (pen + advance / 2) * scale)
            gid = self._glyph(style, ch, outline)
            uses.append(f'<use href="#{gid}" transform="translate({num(px)} {num(py)}) rotate({num(angle)}) '
                        f'scale({num(scale, 4)}) translate({num(-advance / 2)} 0)"/>')
        return f'<g fill="{fill}"{_halo(halo, scale)}{attrs}>{"".join(uses)}</g>'

    def defs(self) -> str:
        """The outlines of every glyph used so far; goes inside the SVG's <defs>."""
        return "".join(f'<path id="{gid}" d="{outline}"/>' for gid, outline in self._defs.items())
