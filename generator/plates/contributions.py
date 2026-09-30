"""Contributions: a year of weekly totals, drawn the way a variable star's brightness is charted.

Each week is an observation, the curve through them is a moving average, and
the brightest week is marked with a star. Without a contribution calendar
(a run without a token) the plate shrinks to the counters alone.

Text is set in three styles only (light, regular, italic): each style in use
brings its own glyph outlines, and they are most of the file.
"""

from __future__ import annotations

from generator.motion import Motion
from generator.svg import comet, frame, num, path_def, star, star_defs
from generator.typeset import Typesetter, measure, wrap

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CAPTION = "contributions in the last year"
EMPTY = "No contribution data yet"
# config key -> (singular, plural); "commits" is the title itself and is never listed
LABELS = {"stars": ("star", "stars"), "prs": ("pull request", "pull requests"),
          "issues": ("issue", "issues"), "repos": ("repository", "repositories")}
MAX_NUMBERS = 3
PEAK_STAR = 6                     # the peak is drawn as bright as a repository with this many stargazers
PEAK_REACH = 12                   # pixels around the peak's star that other text keeps off
STAGGER = 0.022                   # seconds between one week rising and the next
LEVEL_SIZE, PEAK_SIZE, MONTH_SIZE = 11.5, 12.5, 11.5


def moving_average(values, window: int = 5) -> list:
    """Centred moving average; near either end the window shrinks to the weeks that exist."""
    half = window // 2
    out = []
    for i in range(len(values)):
        span = values[max(0, i - half):i + half + 1]
        out.append(sum(span) / len(span))
    return out


def smooth_path(points, low: float = float("-inf"), high: float = float("inf")) -> str:
    """Path data for a Catmull-Rom spline through the points, as cubic Béziers.

    A spline overshoots where the points turn sharply. With low and high given,
    the handles are kept between those two heights, and so is the whole curve.
    """
    def held(y: float) -> float:
        return min(max(y, low), high)

    d = [f"M{num(points[0][0])} {num(points[0][1])}"]
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, len(points) - 1)]
        d.append(f"C{num(p1[0] + (p2[0] - p0[0]) / 6)} {num(held(p1[1] + (p2[1] - p0[1]) / 6))} "
                 f"{num(p2[0] - (p3[0] - p1[0]) / 6)} {num(held(p2[1] - (p3[1] - p1[1]) / 6))} "
                 f"{num(p2[0])} {num(p2[1])}")
    return "".join(d)


def reference_levels(peak: int) -> list:
    """Two round values to rule the chart with: the largest of 1, 2, 2.5 or 5 times a power of ten
    that stays under peak / 2.2, and its double. Whole numbers only; nothing for a peak under 4."""
    if peak < 4:
        return []
    best, scale = 1, 1
    while scale * 22 <= peak * 10:
        for value in (scale, 2 * scale, 5 * scale // 2, 5 * scale):
            if best < value and value * 22 <= peak * 10:          # value <= peak / 2.2, in whole numbers
                best = value
        scale *= 10
    return [best, best * 2]


def _numbers(counters: dict, metrics: list) -> list:
    """[(value, label)] for up to three counters the data has, in the order of the config."""
    out = []
    for key in metrics:
        value = counters.get(key)
        if key in LABELS and isinstance(value, int) and not isinstance(value, bool):
            out.append((f"{value:,}", LABELS[key][0 if value == 1 else 1]))
    return out[:MAX_NUMBERS]


def _summary(series, numbers: list) -> str:
    parts = []
    if series:
        values, dates, total, peak = series
        parts.append(f"{total:,} {CAPTION}")
        if values[peak]:
            parts.append(f"busiest week: {_peak_text(values[peak], dates[peak])}")
    parts += [f"{value} {label}" for value, label in numbers]
    return ("; ".join(parts) or EMPTY) + "."


def _peak_text(value: int, day) -> str:
    return f"{value:,} in the week of {MONTHS[day.month - 1]} {day.day}"


def _top_of_chart(px: float, py: float, span: float, levels: list, x0: float, x1: float) -> tuple:
    """Where the reference labels and the peak's name go so that neither lands on the other.

    levels is [(value, baseline, width of its label)]; span is the width of the
    peak's name (0 when there is no peak). Returns (the end of their lines the
    reference labels sit at, (x, anchor) of the peak's name, the levels whose
    label is written).

    The labels sit at the left end and the name to the left of the star when
    that is clear; otherwise the name goes to the right, or the labels move to
    the right end. A reference label is only in the way if it is at the peak's
    height. If no arrangement is clear, the label in the way is left out: its
    line stays.
    """
    values = [value for value, _baseline, _width in levels]
    if not span:
        return "left", (x0, "start"), values
    reach, gap = PEAK_REACH, 8
    in_the_way = [(value, width) for value, baseline, width in levels
                  if baseline - LEVEL_SIZE < py + reach and baseline + 3 > py - reach]
    wide = max((width for _value, width in in_the_way), default=0)
    left = (px - 16, "end") if px - 16 - span >= x0 else None        # the name left of the star
    right = (px + 16, "start") if px + 16 + span <= x1 else None     # or right of it
    if not in_the_way:
        return "left", left or right or (x0, "start"), values
    for side, name in (("left", left), ("left", right), ("right", right), ("right", left)):
        if name is None:
            continue
        begin = min(px - reach, name[0] - span if name[1] == "end" else name[0])
        end = max(px + reach, name[0] if name[1] == "end" else name[0] + span)
        if (begin >= x0 + wide + gap) if side == "left" else (end <= x1 - wide - gap):
            return side, name, values
    kept = [value for value in values if value not in {v for v, _w in in_the_way}]
    return "left", left or right or (x0, "start"), kept


def _numbers_only(numbers: list, theme, mobile: bool, ts: Typesetter) -> tuple:
    """(height, body) of the short plate: one column per counter."""
    width, margin = (390, 24) if mobile else (850, 44)
    height = 110 if mobile else 120
    if not numbers:
        return height, ts.line(margin, height / 2 + 6, EMPTY, 16, theme.mute, "italic")
    column = (width - 2 * margin) / MAX_NUMBERS
    size, label_size = (28, 13) if mobile else (36, 15)
    top = height / 2 + (2 if mobile else 4)
    body = []
    for k, (value, label) in enumerate(numbers):
        x = margin + k * column
        body.append(ts.line(x, top, wrap(value, size, "light", column - 12, max_lines=1)[0], size, theme.ink, "light"))
        body.append(ts.line(x + 1, top + (22 if mobile else 26), label, label_size, theme.mute, "italic"))
    return height, "".join(body)


def render(series, counters: dict, metrics: list, theme, mobile: bool = False, motion: bool = True) -> str:
    """series is what model.weekly_series returns, or None without a calendar."""
    mo, ts = Motion(motion), Typesetter()
    numbers = _numbers(counters, metrics)
    width = 390 if mobile else 850
    if not series:
        height, body = _numbers_only(numbers, theme, mobile, ts)
        return frame(theme, width, height, body, "Contributions", _summary(None, numbers), ts.defs(), mo)

    values, dates, total, peak = series
    height = 266 if mobile else 254
    x0, x1 = (24, width - 24) if mobile else (44, width - 44)
    base, top = height - 42, (116 if mobile else 100)
    most, weeks = max(values), len(values)

    def at_x(i: int) -> float:
        return x0 + (x1 - x0) * i / (weeks - 1) if weeks > 1 else x0

    def at_y(value: float) -> float:
        return base - (base - top) * value / most if most else base

    body = []

    # the total, as large as the line allows, and its caption right after it
    title_y, caption_size = (48, 14.5) if mobile else (52, 17)
    caption_width = measure(CAPTION, caption_size, "italic")
    size = 32 if mobile else 38
    while size > 22 and x0 + measure(f"{total:,}", size, "light") + 10 + caption_width > x1:
        size -= 2
    figure = wrap(f"{total:,}", size, "light", x1 - x0, max_lines=1)[0]
    caption_x = x0 + measure(figure, size, "light") + 10
    body.append(ts.line(x0, title_y, figure, size, theme.ink, "light"))
    caption = wrap(CAPTION, caption_size, "italic", x1 - caption_x, max_lines=1) if x1 - caption_x > 40 else []
    if caption:
        body.append(ts.line(caption_x, title_y, caption[0], caption_size, theme.mute, "italic"))
    title_end = caption_x + (measure(caption[0], caption_size, "italic") if caption else 0)

    # the other counters: a row under the title on mobile, a column each at the right on desktop
    if mobile:
        x = x0
        for value, label in numbers:
            value_width, label_width = measure(value, 17), measure(label, 13, "italic")
            if x + value_width + 5 + label_width > x1:
                break
            body.append(ts.line(x, 80, value, 17, theme.ink))
            body.append(ts.line(x + value_width + 5, 80, label, 13, theme.mute, "italic"))
            x += value_width + 5 + label_width + 14
    else:
        columns = [max(measure(value, 22, "regular"), measure(label, 13, "italic")) for value, label in numbers]
        while columns and x1 - sum(columns) - 30 * (len(columns) - 1) < title_end + 24:
            columns.pop()
        x = x1
        for (value, label), column in reversed(list(zip(numbers, columns))):
            body.append(ts.line(x, 42, value, 22, theme.ink, "regular", anchor="end"))
            body.append(ts.line(x, 60, label, 13, theme.mute, "italic", anchor="end"))
            x -= column + 30

    # reference levels and the baseline; the labels and the peak's name are placed together, further down
    levels = reference_levels(most)
    for level in levels:
        body.append(f'<path d="M{x0} {num(at_y(level))}H{x1}" stroke="{theme.faint}" stroke-dasharray="1 5"/>')
    body.append(f'<path d="M{x0} {num(base + 0.5)}H{x1}" stroke="{theme.faint}"/>')

    # the curve: written once, used for the glow, the line and the travelling light
    curve = smooth_path([(at_x(i), at_y(v)) for i, v in enumerate(moving_average(values))], top, base)
    defs = [star_defs(theme) if most else "", path_def("cv", curve),
            f'<linearGradient id="ws" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{theme.ink}" '
            f'stop-opacity=".2"/><stop offset="1" stop-color="{theme.ink}" stop-opacity="0"/></linearGradient>']
    body.append(f'<path d="{curve}L{x1} {base}L{x0} {base}Z" fill="url(#ws)"{mo.cls("soft", delay=1.5)}/>')
    drawing = mo.cls("ldraw", delay=0.45)
    body.append(f'<use href="#cv" stroke="{theme.ink}" stroke-width="6" stroke-opacity=".1" stroke-linecap="round"{drawing}/>')
    body.append(f'<use href="#cv" stroke="{theme.ink}" stroke-width="1.6" stroke-opacity=".8" stroke-linecap="round"{drawing}/>')

    # the weeks rise from the baseline, left to right
    radius = 1.7 if mobile else 2
    dots = []
    for i, value in enumerate(values):
        if most and i == peak:
            continue
        rising = mo.cls("rise", delay=i * STAGGER or None, vars={"d": f"{num(base - at_y(value))}px"})
        dots.append(f'<circle cx="{num(at_x(i))}" cy="{num(at_y(value))}" r="{radius}"{rising}/>')
    body.append(f'<g fill="{theme.ink}" fill-opacity=".9">{"".join(dots)}</g>')
    body.append(comet("cv", theme, mo, cycle=12, start=3.4))

    # the peak is a star, named beside it
    peak_text = _peak_text(most, dates[peak]) if most else ""
    side, (label_x, anchor), shown = _top_of_chart(
        at_x(peak), at_y(most), measure(peak_text, PEAK_SIZE) if most else 0,
        [(level, at_y(level) - 5, measure(f"{level:,} a week", LEVEL_SIZE)) for level in levels], x0, x1)
    for level in shown:
        body.append(ts.line(x0 if side == "left" else x1, at_y(level) - 5, f"{level:,} a week", LEVEL_SIZE, theme.mute,
                            anchor="start" if side == "left" else "end"))
    if most:
        px, py = at_x(peak), at_y(most)
        body.append(f'<g transform="translate({num(px)} {num(py)})"><g{mo.cls("pop", delay=peak * STAGGER + 0.2)}>'
                    f'{star(PEAK_STAR, "now", theme, mo)}</g></g>')
        body.append(ts.line(label_x, py + 4, peak_text, PEAK_SIZE, theme.ink, "regular", anchor,
                            mo.cls("soft", delay=peak * STAGGER + 0.5)))

    # month marks: three letters on desktop, the initial on mobile
    month = dates[0].month
    for i, day in enumerate(dates):
        if day.month != month:
            month = day.month
            name = MONTHS[month - 1]
            body.append(f'<path d="M{num(at_x(i))} {base}v5" stroke="{theme.mute}"/>')
            body.append(ts.line(at_x(i), base + 20, name[0] if mobile else name, MONTH_SIZE, theme.mute, anchor="middle"))

    defs.append(ts.defs())
    return frame(theme, width, height, "".join(body), "Contributions", _summary(series, numbers), "".join(defs), mo)
