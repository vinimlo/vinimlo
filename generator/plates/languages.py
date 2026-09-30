"""Languages: the code of the public repositories as one band of light, split like a spectrum.

Under the band comes the stack the profile declares in its focus areas,
which is not measured from anything and is written as plain text.

Text is set in two styles only (regular and italic): each style in use brings
its own glyph outlines, and they are most of the file.
"""

from __future__ import annotations

import logging

from generator.motion import Motion
from generator.svg import clean, frame, num
from generator.typeset import ELLIPSIS, Typesetter, measure, wrap

HEADING = "Languages across public repositories, by bytes of code"
EMPTY = "No language data yet"
GAP = 2                           # pixels between segments
BAND_Y, BAND_H, LIGHT_H = 56, 24, 16
SWEEP, SWEEP_STARTS = 1.5, 0.25   # seconds the entrance sweep takes, and when it starts
COLUMNS = 3                       # focus areas per row on desktop
LIST_LINES = 2                    # lines a focus area's items may take, while the file fits its budget
BYTE_BUDGET = 48_000              # the file's ceiling (spec, section 5)

logger = logging.getLogger(__name__)


def sweep_time(x: float) -> float:
    """When, from 0 to 1, a sweep that decelerates as a cubic ease-out reaches fraction x of the width."""
    return 1 - (1 - min(max(x, 0.0), 1.0)) ** (1 / 3)


def _percent(value: float) -> str:
    return f"{value:g}%"


def _band(shares: list, theme, x0: float, x1: float) -> list:
    """[(name or None, percent, x, width, colour, ramp step or None)]; the unnamed last one is what the list leaves out."""
    shown = sum(percent for _name, percent in shares)
    parts = [(name, percent, min(k, len(theme.ramp) - 1)) for k, (name, percent) in enumerate(shares)]
    if shown < 99.5:
        parts.append((None, 100 - shown, None))
    whole = sum(percent for _name, percent, _step in parts)
    span = x1 - x0 - GAP * (len(parts) - 1)
    out, x = [], x0
    for name, percent, step in parts:
        width = span * percent / whole
        out.append((name, percent, x, width, theme.faint if step is None else theme.ramp[step], step))
        x += width + GAP
    return out


def _items(items) -> list:
    """A focus area's items as text, without the empty ones."""
    if not isinstance(items, (list, tuple)):
        return []
    return [text for text in (clean(item).strip() for item in items if item is not None) if text]


def _list_lines(items: list, size: float, limit: float, most: int = LIST_LINES) -> list:
    """A focus area's items as running text in up to `most` lines, broken between items, never inside one."""
    lines, current = [], ""
    for item in _items(items):
        candidate = f"{current}, {item}" if current else item
        if not current or measure(candidate + ",", size) <= limit:
            current = candidate
        else:
            lines.append(current + ",")
            current = item
    if current:
        lines.append(current)
    if len(lines) > most:
        # what does not fit is cut where the last line ends, with an ellipsis
        lines[most - 1:] = wrap(" ".join(lines[most - 1:]), size, "regular", limit, max_lines=1)
    fitted = [cut[0] for cut in (wrap(line, size, "regular", limit, max_lines=1) for line in lines) if cut]
    return [line[:-2] + ELLIPSIS if line.endswith("," + ELLIPSIS) else line for line in fitted]


def _stack(arms: list, theme, mobile: bool, x0: float, x1: float, top: float, ts: Typesetter,
           list_lines: int = LIST_LINES) -> tuple:
    """(body, baseline of the last line) of the declared stack, its first area name set at `top`."""
    name_size, item_size = (14.5, 13.5) if mobile else (16, 14)
    to_items, line_step, to_next = (18, 17, 22) if mobile else (22, 19, 36)
    per_row = 1 if mobile else COLUMNS
    column = (x1 - x0) / per_row
    limit = column - (0 if mobile else 24)
    body, y, last = [], top, top
    for start in range(0, len(arms), per_row):
        bottom = y
        for k, arm in enumerate(arms[start:start + per_row]):
            x = x0 + k * column
            name = wrap(str(arm.get("name") or ""), name_size, "italic", limit, max_lines=1)
            if name:
                body.append(ts.line(x, y, name[0], name_size, theme.ink, "italic"))
            for j, line in enumerate(_list_lines(arm.get("items") or [], item_size, limit, list_lines)):
                body.append(ts.line(x, y + to_items + j * line_step, line, item_size, theme.mute))
                bottom = max(bottom, y + to_items + j * line_step)
        last, y = bottom, bottom + to_next
    return "".join(body), last


def _summary(shares: list, arms: list) -> str:
    measured = ", ".join(f"{name} {_percent(percent)}" for name, percent in shares) or EMPTY
    declared = "; ".join(
        ": ".join(part for part in (clean(arm.get("name") or "").strip(), ", ".join(_items(arm.get("items")))) if part)
        for arm in arms)
    return f"{measured}." + (f" Declared stack: {declared}." if declared else "")


def render(shares: list, arms: list, theme, mobile: bool = False, motion: bool = True) -> str:
    """shares is what model.language_shares returns; arms is the config's galaxy_arms.

    Every character of the declared stack is a glyph in the file, so the lists
    are what decides its size. Each focus area's list gets two lines; if that
    puts the file over BYTE_BUDGET, each gets one. Nothing else is given up:
    a file that is still over is drawn anyway, with a warning.
    """
    drawn = []
    for list_lines in range(LIST_LINES, 0, -1):
        drawn.append(_compose(shares, arms, theme, mobile, motion, list_lines))
        if len(drawn[-1].encode("utf-8")) <= BYTE_BUDGET:
            return drawn[-1]
    svg = min(drawn, key=lambda candidate: len(candidate.encode("utf-8")))
    logger.warning("tech-stack%s is %d bytes, over the %d budget: the focus areas hold a lot of text.",
                   "-mobile" if mobile else "", len(svg.encode("utf-8")), BYTE_BUDGET)
    return svg


def _compose(shares: list, arms: list, theme, mobile: bool, motion: bool, list_lines: int) -> str:
    mo, ts = Motion(motion), Typesetter()
    shares = [(name, percent) for name, percent in shares if percent > 0]      # nothing to draw for a zero share
    width = 390 if mobile else 850
    x0, x1 = (24, width - 24) if mobile else (44, width - 44)
    heading_size = 13 if mobile else 14
    heading = wrap(HEADING, heading_size, "italic", x1 - x0, max_lines=1)[0]
    body = [ts.line(x0, 38, heading, heading_size, theme.mute, "italic")]
    defs, gradients, tail, edge = [], set(), [], []

    for k, (name, percent, x, w, colour, step) in enumerate(_band(shares, theme, x0, x1) if shares else []):
        begins = sweep_time((x - x0) / (x1 - x0))
        ends = sweep_time(min((x + w - x0) / (x1 - x0), 1))
        light = ""
        if step is not None:
            if step not in gradients:
                gradients.add(step)
                defs.append(f'<linearGradient id="sg{step}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" '
                            f'stop-color="{colour}" stop-opacity="{".42" if theme.dark else ".3"}"/>'
                            f'<stop offset="1" stop-color="{colour}" stop-opacity="0"/></linearGradient>')
            # the light the segment casts below itself, breathing slowly
            light = (f'<rect y="{BAND_H}" width="{num(w)}" height="{LIGHT_H}" fill="url(#sg{step})"'
                     f'{mo.cls("breathe", delay=-k * 1.1 or None)}/>')
        # the segment opens from its own left edge, timed so the whole band reads as one sweep
        opening = mo.cls("grow", delay=SWEEP_STARTS + begins * SWEEP, duration=max(ends - begins, 0.01) * SWEEP)
        body.append(f'<g transform="translate({num(x)} {BAND_Y})"><g{opening}><rect width="{num(w)}" height="{BAND_H}" '
                    f'rx="2.5" fill="{colour}"/>{light}</g></g>')
        edge.append((ends, x + w))
        if name is None:
            continue
        # the name goes under the segment when it fits there; the others are told in a closing phrase
        figure = _percent(percent)
        for name_size, figure_size in ((15.5, 13), (13, 12)) if w >= 60 else ((13, 12),):
            if max(measure(name, name_size), measure(figure, figure_size)) <= w - 4:
                body.append(f'<g{mo.cls("soft", delay=SWEEP_STARTS + begins * SWEEP + 0.15)}>'
                            f'{ts.line(x, BAND_Y + BAND_H + 27, name, name_size, theme.ink)}'
                            f'{ts.line(x, BAND_Y + BAND_H + 44, figure, figure_size, theme.mute)}</g>')
                break
        else:
            tail.append(f"{name} {figure}")

    if not shares:
        body.append(ts.line(x0, BAND_Y + 17, EMPTY, 16, theme.mute, "italic"))
    if tail:
        phrase, arrives = "and " + ", ".join(tail), mo.cls("soft", delay=SWEEP_STARTS + SWEEP)
        if mobile:
            body.append(ts.line(x0, BAND_Y + BAND_H + 64, wrap(phrase, 12.5, "regular", x1 - x0, max_lines=1)[0],
                                12.5, theme.mute, attrs=arrives))
        else:
            room = x1 - (x0 + measure(heading, heading_size, "italic") + 24)
            if room > 60:
                body.append(ts.line(x1, 38, wrap(phrase, 12.5, "regular", room, max_lines=1)[0], 12.5, theme.mute,
                                    anchor="end", attrs=arrives))

    if edge:
        # the bright leading edge of the sweep: it reaches the end of each segment as that segment finishes opening
        stops = "".join(f"{num(when * 100)}%{{transform:translateX({num(where)}px);opacity:1}}"
                        for when, where in edge[:-1])
        mo.define("edge", f".edge{{animation:edge {SWEEP}s linear {SWEEP_STARTS}s both}}@keyframes edge{{"
                          f"0%{{transform:translateX({num(x0)}px);opacity:0}}3%{{opacity:1}}{stops}96%{{opacity:1}}"
                          f"100%{{transform:translateX({num(edge[-1][1])}px);opacity:0}}}}")
        head = "#ffffff" if theme.dark else theme.now
        body.append(mo.only(
            f'<g{mo.cls("edge", only=True)} stroke-linecap="round">'
            f'<path d="M0 {BAND_Y - 5}V{BAND_Y + BAND_H + 5}" stroke="{theme.now}" stroke-width="9" stroke-opacity=".22"/>'
            f'<path d="M0 {BAND_Y - 4}V{BAND_Y + BAND_H + 4}" stroke="{head}" stroke-width="1.6"/></g>'))

    rule_y = BAND_Y + BAND_H + (84 if mobile else 62)
    body.append(f'<path d="M{x0} {rule_y}H{x1}" stroke="{theme.faint}"/>')
    stack, last = _stack(arms, theme, mobile, x0, x1, rule_y + 30, ts, list_lines)
    body.append(stack)
    height = round(last + (34 if mobile else 32))
    defs.append(ts.defs())
    return frame(theme, width, height, "".join(body), "Languages and declared stack", _summary(shares, arms),
                 "".join(defs), mo)
