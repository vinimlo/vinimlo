"""Featured projects: a short catalogue of stars.

Each project is drawn with the same star the galaxy uses for it (brightness
from its stargazers, state from its last push), lettered α, β, γ from the
brightest, the way stars are designated within a constellation.
"""

from __future__ import annotations

from generator.motion import Motion
from generator.svg import comet, frame, num, path_def, spike_half, star, star_defs
from generator.typeset import Typesetter, measure, wrap

LETTERS = "αβγδε"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
EMPTY = "No featured projects yet"
META_SIZE = 13
MOBILE_STAR = 0.55      # bloom and spikes are drawn smaller in the narrow gutter


def _meta(item, limit: float = float("inf")) -> str:
    """The data line: language, stargazers and month of the last push. Zero stars go unmentioned.

    If it does not fit in `limit` pixels it loses the word "updated", then the
    date, and only then is cut.
    """
    lead = [item.language] if item.language else []
    if item.stars:
        lead.append(f"{item.stars} star{'' if item.stars == 1 else 's'}")
    month = f"{MONTHS[item.pushed.month - 1]} {item.pushed.year}"
    for parts in (lead + [f"updated {month}"], lead + [month], lead or [month]):
        line = ", ".join(parts)
        if measure(line, META_SIZE, "regular") <= limit:
            return line
    return wrap(line, META_SIZE, "regular", limit, max_lines=1)[0]


def render(items: list, theme, mobile: bool = False, motion: bool = True) -> str:
    """items are model.Featured, already ordered brightest first."""
    mo, ts = Motion(motion), Typesetter()
    width = 390 if mobile else 850
    margin = 24 if mobile else 44
    if not items:
        body = ts.line(margin, 62, EMPTY, 16, theme.mute, "italic")
        return frame(theme, width, 110, body, "Featured projects", EMPTY, ts.defs(), mo)

    step = 142
    height = 26 + step * len(items) if mobile else 214
    column = (width - 2 * margin) / max(len(items), 2)
    glyphs, text = [], []
    for k, item in enumerate(items):
        ignite = 0.25 + k * 0.45
        if mobile:
            # stars live in a gutter on the left, so the line joining them never crosses text
            top = 18 + k * step
            gx, gy, tx = margin + 12, top + 40, margin + 44
            limit = width - margin - tx
            reach = spike_half(item.stars) * MOBILE_STAR
            letter_at, name_y, first_line_y, meta_gap, letter_size = (tx, top + 18), top + 48, top + 71, 6, 15
        else:
            tx = margin + k * column
            gx, gy = tx + 14, 42 + (k % 2) * 4
            limit = column - 24
            reach = spike_half(item.stars)
            # the letter sits just past the star's spikes, however bright the star
            letter_at, name_y, first_line_y, meta_gap, letter_size = (gx + reach + 8, gy + 5), 100, 124, 8, 16
        lines = wrap(item.description, 14.5, "italic", limit, max_lines=2)
        rows = [(letter_at[0], letter_at[1], LETTERS[k], letter_size, theme.mute, "italic"),
                (tx, name_y, wrap(item.name, 23, "medium", limit, max_lines=1)[0], 23, theme.ink, "medium")]
        rows += [(tx, first_line_y + j * 19, line, 14.5, theme.mute, "italic") for j, line in enumerate(lines)]
        rows.append((tx, first_line_y + len(lines) * 19 + meta_gap, _meta(item, limit), META_SIZE, theme.mute,
                     "regular"))
        for j, (x, y, string, size, fill, style) in enumerate(rows):
            text.append(ts.line(x, y, string, size, fill, style,
                                attrs=mo.cls("soft", delay=ignite + 0.12 + j * 0.09)))
        glyphs.append((gx, gy, item, ignite, reach))

    defs, links = [star_defs(theme)], []
    for q, ((ax, ay, _a, lit, reach_a), (bx, by, _b, _lit, reach_b)) in enumerate(zip(glyphs, glyphs[1:])):
        # the line runs from clear of one star (and its letter) to clear of the next
        if mobile:
            d = f"M{num(ax)} {num(ay + reach_a + 4)}L{num(bx)} {num(by - reach_b - 4)}"
        else:
            slope = (by - ay) / (bx - ax)
            lead, trail = reach_a + 26, reach_b + 6
            d = f"M{num(ax + lead)} {num(ay + slope * lead)}L{num(bx - trail)} {num(by - slope * trail)}"
        defs.append(path_def(f"p{q}", d))
        links.append(f'<use href="#p{q}" stroke="{theme.ink}" stroke-width=".9" stroke-opacity=".38"'
                     f'{mo.cls("ldraw", delay=lit + 0.3, duration=1.1)}/>')
        links.append(comet(f"p{q}", theme, mo, cycle=8, start=3 + q * 1.3, tail=0.12, scale=0.8))
    stars = [f'<g transform="translate({num(gx)} {num(gy)})"><g{mo.cls("pop", delay=lit)}>'
             f'{star(item.stars, item.state, theme, mo, phase=k * 0.9, scale=MOBILE_STAR if mobile else 1.0)}</g></g>'
             for k, (gx, gy, item, lit, _reach) in enumerate(glyphs)]
    desc = ". ".join(f"{item.name}: {_meta(item)}" for item in items) + "."
    defs.append(ts.defs())
    return frame(theme, width, height, "".join(links + stars + text), "Featured projects", desc,
                 "".join(defs), mo)
