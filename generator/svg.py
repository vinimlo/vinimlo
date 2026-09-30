"""SVG primitives shared by every plate."""

from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape as _xml_escape

# characters XML 1.0 cannot carry; tabs and line breaks become a space
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_BREAKS = re.compile(r"[\t\r\n]+")


def num(value: float, places: int = 1) -> str:
    """Format a number for SVG: rounded, no trailing zeros, no leading zero, never "-0"."""
    text = f"{round(value, places):.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", "-", ""):
        return "0"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def clean(text) -> str:
    """Text without the control characters that would make the SVG malformed."""
    return _CONTROL.sub("", _BREAKS.sub(" ", str(text)))


def esc(text) -> str:
    """Escape text for an SVG text node or a double-quoted attribute."""
    return _xml_escape(clean(text), {'"': "&quot;"})


# ── particles ────────────────────────────────────────────────────────────────

# A particle is a subpath so short it is only its round cap. Truly zero-length
# subpaths are drawn inconsistently across renderers; a hundredth of a pixel is not.
_DOT = "h.01"
_DOT_LENGTH = 0.01


def dots_d(points, places: int = 1) -> str:
    """Path data for one dot per point, in relative moves so the numbers stay short."""
    out, cx, cy = [], None, None
    for x, y in points:
        if cx is None:
            sx, sy = num(x, places), num(y, places)
            out.append(f"M{sx} {sy}{_DOT}")
            cx, cy = float(sx), float(sy)
        else:
            dx, dy = num(x - cx, places), num(y - cy, places)
            out.append(f"m{dx} {dy}{_DOT}")
            cx, cy = cx + float(dx), cy + float(dy)
        cx += _DOT_LENGTH
    return "".join(out)


PARTICLE_GROUP = 'stroke-linecap="round" fill="none"'    # what a group of bare dots() must carry


def dots(points, width: float, color: str, opacity: float = 1.0, standalone: bool = True,
         places: int = 1) -> str:
    """Round particles of one size and colour as a single stroked path.

    Transparency is stroke-opacity, never opacity: group opacity forces an
    offscreen layer per path and drops the frame rate by two thirds.
    standalone=False leaves out the cap and fill attributes, for paths inside
    a group that already carries PARTICLE_GROUP. places is the number of
    decimals kept in the coordinates.
    """
    if not points:
        return ""
    alpha = "" if opacity >= 1 else f' stroke-opacity="{num(opacity, 2)}"'
    own = f" {PARTICLE_GROUP}" if standalone else ""
    return f'<path d="{dots_d(points, places)}" stroke="{color}" stroke-width="{num(width, 2)}"{alpha}{own}/>'


# ── the repository star ──────────────────────────────────────────────────────

# Past a few thousand stargazers the glyph stops growing, so it always fits its plate.
MAX_MAG = 3.5


def mag(stars: int) -> float:
    return min(math.log10(1 + max(stars, 0)), MAX_MAG)


def spike_half(stars: int) -> float:
    """Half the length of a star's diffraction spikes."""
    return 7 + 8.5 * mag(stars)


def star_defs(theme) -> str:
    """The gradients star() refers to. One set per SVG."""
    out = []
    strength = 1.0 if theme.dark else 0.5
    for key, colour in (("n", theme.now), ("y", theme.year)):
        hot = "#ffffff" if theme.dark else colour
        out.append(
            f'<radialGradient id="h{key}"><stop offset="0" stop-color="{colour}" stop-opacity="{num(.7 * strength, 2)}"/>'
            f'<stop offset=".16" stop-color="{colour}" stop-opacity="{num(.36 * strength, 2)}"/>'
            f'<stop offset=".42" stop-color="{colour}" stop-opacity="{num(.11 * strength, 2)}"/>'
            f'<stop offset="1" stop-color="{colour}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="c{key}"><stop offset=".5" stop-color="{hot}"/>'
            f'<stop offset="1" stop-color="{colour}"/></radialGradient>')
        for gid, vector in ((f"s{key}", 'x2="1" y2="0"'), (f"v{key}", 'x2="0" y2="1"')):
            out.append(
                f'<linearGradient id="{gid}" x1="0" y1="0" {vector}><stop offset="0" stop-color="{colour}" stop-opacity="0"/>'
                f'<stop offset=".5" stop-color="{hot}" stop-opacity=".95"/>'
                f'<stop offset="1" stop-color="{colour}" stop-opacity="0"/></linearGradient>')
    return "".join(out)


def star(stars: int, state: str, theme, motion, phase: float = 0.0, scale: float = 1.0,
         shimmer: bool = True) -> str:
    """A repository star drawn at the origin.

    scale shrinks the bloom and the spikes (not the core) where space is tight.
    shimmer=False leaves the halo and the spikes still, for crowded plates.

    Brighter means a wider bloom and longer spikes, not a bigger disc: the core
    stays small, as in a photograph of a real star. state is "now", "year" or
    "dorm"; a dormant star is a hollow ring with no spikes.
    """
    g = mag(stars)
    core = 1.5 + 0.7 * g
    if state == "dorm":
        return (f'<circle r="{num(core + 3.4)}" fill="{theme.dorm}" fill-opacity=".09"/>'
                f'<circle r="{num(core + .7)}" fill="none" stroke="{theme.dorm}" stroke-opacity=".8"/>')
    key = "n" if state == "now" else "y"
    glow, half, width = core * (4.4 + 1.3 * g) * scale, spike_half(stars) * scale, (1.1 + 0.45 * g) * scale
    delay = -phase if phase else None
    pulse = motion.cls("tw", delay=delay) if state == "now" and shimmer else ""
    return (f'<circle r="{num(glow)}" fill="url(#h{key})"{pulse}/>'
            f'<g{motion.cls("spk", delay=delay) if shimmer else ""}>'
            f'<path fill="url(#s{key})" d="M{num(-half)} 0Q0 {num(-width, 2)} {num(half)} 0Q0 {num(width, 2)} {num(-half)} 0Z"/>'
            f'<path fill="url(#v{key})" d="M0 {num(-half)}Q{num(width, 2)} 0 0 {num(half)}Q{num(-width, 2)} 0 0 {num(-half)}Z"/>'
            f'</g><circle r="{num(core)}" fill="url(#c{key})"/>')


# ── the travelling light ─────────────────────────────────────────────────────

def path_def(path_id: str, d: str) -> str:
    """A path for <defs> with its length normalised to 1, so dash lengths are fractions of it."""
    return f'<path id="{path_id}" d="{d}" pathLength="1" fill="none"/>'


def comet(path_id: str, theme, motion, cycle: float, start: float, tail: float = 0.06,
          scale: float = 1.0) -> str:
    """A point of light that runs along a path_def once per cycle; exists only when motion is on.

    It is the path itself, stroked with a dash so short it is just its round
    cap; animating the dash offset makes the point travel. Five copies make
    the head, two halos and two lengths of tail.
    """
    if not motion.enabled:
        return ""
    head = "#ffffff" if theme.dark else theme.now
    layers = (  # dash length, how far behind the head the dash starts, width, colour, peak opacity
        (tail, tail, 1.6, theme.now, .55),
        (tail * .45, tail * .45, 2.6, theme.now, .5),
        (.0005, 0, 15, theme.now, .16),
        (.0005, 0, 8, theme.now, .3),
        (.0005, 0, 3.6, head, 1),
    )
    out = []
    for length, behind, width, colour, peak in layers:
        # one whole dash period is added so the offsets stay positive (some engines mishandle negative ones)
        lead = behind + length + 2
        attrs = motion.cls("comet", only=True, vars={
            "a": num(lead, 4), "b": num(lead - 1, 4), "o": num(peak, 2),
            "cy": f"{num(cycle, 2)}s", "st": f"{num(start, 2)}s"})
        out.append(f'<use href="#{path_id}"{attrs} stroke="{colour}" stroke-width="{num(width * scale)}" '
                   f'stroke-linecap="round" stroke-dasharray="{num(length, 4)} 2"/>')
    return "".join(out)


# ── the frame ────────────────────────────────────────────────────────────────

def frame(theme, width: int, height: int, body: str, title: str, desc: str, defs: str = "",
          motion=None) -> str:
    """Wrap a plate's body into a complete, accessible SVG on the theme's background."""
    css = motion.css() if motion is not None else ""
    if css:
        defs += f"<style>{css}</style>"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-labelledby="t d">'
            f'<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>'
            + (f"<defs>{defs}</defs>" if defs else "")
            + f'<rect width="{width}" height="{height}" rx="10" fill="{theme.bg}"/>{body}</svg>')
