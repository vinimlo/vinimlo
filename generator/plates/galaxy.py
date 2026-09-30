"""The galaxy: a face-on logarithmic spiral drawn from the profile's repositories.

The arms are made of loose particles that stream along them while the shape
of the spiral stays still. That works because a logarithmic spiral maps onto
itself under a rotation by phi combined with a scale of e^(b*phi): each layer
of particles is one 60-degree tile repeated in rotated, scaled copies, and
animating the group through one step of that transform moves every copy onto
the next. One animated element moves thousands of particles, and the loop has
no seam.

A particle's size is proportional to its distance from the core. The same
symmetry requires it, and it keeps the image coherent under any zoom.
"""

from __future__ import annotations

import math
import random

from generator.model import recency
from generator.motion import Motion
from generator.svg import PARTICLE_GROUP, clean, dots, dots_d, frame, num, spike_half, star, star_defs
from generator.typeset import Typesetter, covers, font, measure, wrap

PHI = math.pi / 3                 # tile step along an arm
R0 = 20.0                         # radius where the spiral starts
TURNS = 1.5                       # turns from R0 to the rim
FLOW_STEPS = 4                    # keyframes per loop; keeps the scale close to exponential

# particles per tile, seconds per loop, inner cut, outer cut (fractions of the radius), size multiplier
LAYERS = ((95, 22, 0.0, 1.0, 1.0), (75, 29, 0.0, 0.6, 1.8), (75, 25, 0.4, 1.0, 1.0))
# diameter as a fraction of the tile's radius, share of the particles, opacity, bloom
SIZES = ((0.0085, 0.55, 0.9, False), (0.014, 0.28, 1.0, False), (0.022, 0.13, 1.0, True), (0.034, 0.04, 1.0, True))
BULGE_SIZES = (1.0, 1.7, 2.5, 3.6)                     # pixels; the bulge does not flow, so it has no tile
BULGE = 320                       # particles in the bulge
BLOOM = ((3.3, 0.035), (2.6, 0.07), (2.0, 0.13), (1.5, 0.26))   # width multiplier, opacity
OFF_AXIS = 0.085                  # further than this from the arm's axis, a particle is always small
CLUSTERS = 8
TILE_VARIANTS = 3                 # distinct particle patterns; further arms reuse them, out of step
MAX_FLOWING = 18                  # flowing layers in the whole galaxy; with many arms, each gets fewer
FULL_ARMS = 4                     # a galaxy holds the dust of this many whole arms; more arms share it


class Geometry:
    """Where things are: the frame, the core, the spiral."""

    def __init__(self, mobile: bool, arms: int) -> None:
        self.width, self.height = (390, 478) if mobile else (850, 430)
        self.cx, self.cy, self.radius = (195, 282, 172) if mobile else (630, 215, 196)
        self.arms = max(arms, 1)
        self.b = math.log(self.radius / R0) / (TURNS * 2 * math.pi)
        self.k = math.exp(self.b * PHI)

    def angle(self, arm: int) -> float:
        """The direction in which an arm leaves the core, in radians."""
        return math.radians(35) + arm * 2 * math.pi / self.arms

    def plane(self, arm: int, r: float, stretch: float = 1.0) -> tuple:
        """The point of an arm at distance r from the core, relative to the core."""
        a = self.angle(arm) + math.log(r / R0) / self.b
        return r * stretch * math.cos(a), r * stretch * math.sin(a)

    def point(self, arm: int, r: float, stretch: float = 1.0) -> tuple:
        """The same point in the frame's coordinates."""
        x, y = self.plane(arm, r, stretch)
        return self.cx + x, self.cy + y

    def copy(self, j: int) -> tuple:
        """(degrees, scale) that place the j-th copy of the rim tile; j is 0 at the rim and negative inward."""
        return math.degrees(j * PHI), self.k ** j

    def flow(self, q: float) -> tuple:
        """(degrees, scale) of the flow transform at fraction q of a loop."""
        return math.degrees(PHI * q), math.exp(self.b * PHI * q)


def _pick(rng, table):
    roll, acc = rng.random(), 0.0
    for item, share in table:
        acc += share
        if roll <= acc:
            return item
    return table[-1][0]


def _field(buckets: dict, glow: float, ids: list, bloom_on: bool = True, places: int = 1) -> str:
    """Particles grouped by colour and size, to go inside a group that carries svg.PARTICLE_GROUP.

    Bright ones of one size are defined once, in all their colours, and drawn
    five times: four widening, fading layers of bloom and the particle itself.
    The width and the opacity of each layer are set on its <use> and inherited
    by the paths. bloom_on=False draws every particle plain; places is the
    number of decimals kept in the coordinates.
    """
    out, bright = [], {}
    for (colour, width, opacity, bloom), points in sorted(buckets.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if bloom and bloom_on:
            bright.setdefault(width, []).append(f'<path d="{dots_d(points, places)}" stroke="{colour}"/>')
        else:
            out.append(dots(points, width, colour, opacity, standalone=False, places=places))
    for width, paths in sorted(bright.items()):
        ids[0] += 1
        layer = f'<use href="#d{ids[0]}" stroke-width='
        out.append(f'<defs><g id="d{ids[0]}">{"".join(paths)}</g></defs>'
                   + "".join(f'{layer}"{num(width * m, 2)}" stroke-opacity="{num(a * glow, 3)}"/>' for m, a in BLOOM)
                   + f'{layer}"{num(width, 2)}"/>')
    return "".join(out)


def _tile(geo: Geometry, count: int, multiplier: float, theme, rng) -> dict:
    """One 60-degree stretch at the rim of an arm that leaves the core at angle 0.

    Returns {(colour, width, opacity, bloom): [points]}.
    """
    start = TURNS * 2 * math.pi - PHI                       # the tile covers the last PHI of the arm
    mid_radius = geo.radius * math.exp(-geo.b * PHI / 2)
    clusters = [(rng.uniform(0, PHI), rng.gauss(0, 0.05)) for _ in range(CLUSTERS)]
    sizes = [(size, size[1]) for size in SIZES]
    buckets = {}
    for _ in range(count):
        if rng.random() < 0.45:
            centre, offset = rng.choice(clusters)
            s, delta = centre + rng.gauss(0, 0.05), offset + rng.gauss(0, 0.03)
        else:
            s, delta = rng.uniform(0, PHI), rng.gauss(0, 0.16 if rng.random() < 0.2 else 0.055)
        s %= PHI
        size, _share, opacity, bloom = _pick(rng, sizes)
        if abs(delta) > OFF_AXIS:
            size, _share, opacity, bloom = SIZES[0] if rng.random() < 0.7 else SIZES[1]
        r = R0 * math.exp(geo.b * (start + s)) * (1 + delta)
        a = start + s
        key = (_pick(rng, theme.dust), round(size * multiplier * mid_radius, 2), opacity, bloom)
        buckets.setdefault(key, []).append((r * math.cos(a), r * math.sin(a)))
    return buckets


def _copies(geo: Geometry, r_lo: float, r_hi: float) -> list:
    """Which copies of the rim tile can show between two radii at some point of a loop (0 is the rim's own)."""
    out, j = [], 0
    while geo.radius * geo.k ** j >= R0 * 0.7:
        if geo.radius * geo.k ** (j + 1) > r_lo * 0.85 and geo.radius * geo.k ** (j - 1) < r_hi:
            out.append(j)
        j -= 1
    return out


def dust(geo: Geometry, cuts: list, theme, rng, motion, keep: float = 1.0) -> tuple:
    """(defs, body) of the particle field, in coordinates relative to the core.

    cuts is the radius where each arm ends. Each arm has up to three layers
    of particles flowing at different speeds, each layer behind a radial mask
    that fades it in and out; then comes the dense bulge at the core.

    The cost is bounded whatever the number of arms. There are TILE_VARIANTS
    particle patterns per layer, which further arms reuse at another point of
    the loop; at most MAX_FLOWING layers flow, while each arm keeps one; and
    past FULL_ARMS whole arms the same amount of dust is spread thinner.
    keep is the fraction of the particles that is drawn at all.
    """
    frames = "".join(
        f"{num(100 * q / FLOW_STEPS)}%{{transform:rotate({num(geo.flow(q / FLOW_STEPS)[0], 2)}deg) "
        f"scale({num(geo.flow(q / FLOW_STEPS)[1], 4)})}}" for q in range(FLOW_STEPS + 1))
    motion.define("flow", f".flow{{animation:flow 22s linear infinite}}@keyframes flow{{{frames}}}")

    R = geo.radius
    layers = LAYERS[:max(1, min(len(LAYERS), MAX_FLOWING // max(len(cuts), 1)))]
    bands = []                                              # (arm, layer, inner radius, outer radius, copies)
    for arm, cut in enumerate(cuts):
        for layer, (_count, _seconds, inner, outer, _multiplier) in enumerate(layers):
            r_lo, r_hi = inner * R, min(outer * R, cut) * 1.04
            if r_lo < r_hi * 0.9:
                bands.append((arm, layer, r_lo, r_hi, _copies(geo, r_lo, r_hi)))
    whole = FULL_ARMS * sum(count * len(_copies(geo, inner * R, outer * R * 1.04))
                            for count, _seconds, inner, outer, _multiplier in LAYERS)
    asked = sum(layers[layer][0] * len(copies) for _arm, layer, _lo, _hi, copies in bands)
    density = keep * (min(1.0, whole / asked) if asked else 1.0)

    defs, body, ids, tiles, masks = [], [], [0], set(), {}
    for arm, layer, r_lo, r_hi, copies in bands:
        count, seconds, _inner, _outer, multiplier = layers[layer]
        tile = f"t{arm % TILE_VARIANTS}{layer}"
        if tile not in tiles:
            tiles.add(tile)
            field = _field(_tile(geo, max(round(count * density), 1), multiplier, theme, rng), theme.glow, ids)
            defs.append(f'<g id="{tile}">{field}</g>')
        reach = (num(r_lo), num(r_hi))
        if reach not in masks:
            masks[reach] = len(masks)
            fade_in = "" if not r_lo else (
                f'<stop offset="{num(max(r_lo - R * 0.1, 0) / r_hi, 3)}" stop-color="#fff" stop-opacity="0"/>'
                f'<stop offset="{num(r_lo / r_hi, 3)}" stop-color="#fff"/>')
            side = num(r_hi)
            defs.append(
                f'<radialGradient id="g{masks[reach]}">{fade_in}<stop offset=".8" stop-color="#fff"/>'
                f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                f'<mask id="k{masks[reach]}" maskUnits="userSpaceOnUse" x="-{side}" y="-{side}" '
                f'width="{num(r_hi * 2)}" height="{num(r_hi * 2)}"><circle r="{side}" fill="url(#g{masks[reach]})"/></mask>')
        leaves = math.degrees(geo.angle(arm))
        placed = "".join(f'<use href="#{tile}" transform="rotate({num(leaves + geo.copy(j)[0], 2)}) '
                         f'scale({num(geo.copy(j)[1], 4)})"/>' for j in copies)
        phase = rng.uniform(0, seconds)                     # drawn whether or not motion is on
        body.append(f'<g mask="url(#k{masks[reach]})"><g{motion.cls("flow", delay=-phase, duration=seconds)}>'
                    f'{placed}</g></g>')

    sizes = [(index, size[1]) for index, size in enumerate(SIZES)]
    bulge = {}
    for _ in range(round(BULGE * keep)):
        a, r = rng.uniform(0, 2 * math.pi), abs(rng.gauss(0, R * 0.095))
        index = _pick(rng, sizes)
        key = (_pick(rng, theme.dust), BULGE_SIZES[index], SIZES[index][2], SIZES[index][3])
        bulge.setdefault(key, []).append((r * math.cos(a), r * math.sin(a)))
    body.append(f'<g{motion.cls("swirl")}>{_field(bulge, theme.glow, ids)}</g>')
    return "".join(defs), "".join(body)


# ── repository stars ─────────────────────────────────────────────────────────

INNER_EDGE = 0.26                 # stars start this far out (fraction of the radius), clear of the bulge
OUTER_EDGE = 0.95                 # and end this close to their arm's cut
LOOSE_BAND = (0.3, 0.8)           # where repositories without an arm float
MIN_GAP = 14                      # pixels between a loose star and any other
UNNAMED_CUT = 0.8


def arm_cuts(model, geo: Geometry) -> list:
    """The radius where each arm ends: longer for the focus areas with more repositories."""
    most = max((len(arm.repos) for arm in model.arms), default=0)
    if not most:
        return [geo.radius * UNNAMED_CUT for _ in model.arms]
    return [geo.radius * (0.5 + 0.5 * len(arm.repos) / most) for arm in model.arms]


def place_stars(model, geo: Geometry, seed: str) -> dict:
    """{repository key: (x, y)} in the frame's coordinates.

    On an arm, repositories run from the oldest near the core to the newest
    near the arm's end, evenly spaced in radius. Those without an arm float
    between the arms, each tried a dozen times for a spot clear of the others.
    A loose star's spot is drawn from its own name and the seed, so it does
    not move when something else in the galaxy changes.
    """
    positions = {}
    for index, (arm, cut) in enumerate(zip(model.arms, arm_cuts(model, geo))):
        inner, outer = geo.radius * INNER_EDGE, cut * OUTER_EDGE
        for q, repo in enumerate(arm.repos):
            positions[repo.key] = geo.point(index, inner + (outer - inner) * (q + 0.5) / len(arm.repos))
    for repo in model.loose:
        spot, rng = None, random.Random(f"star:{seed}:{repo.key}")
        for _ in range(12):
            a, r = rng.uniform(0, 2 * math.pi), geo.radius * rng.uniform(*LOOSE_BAND)
            spot = (geo.cx + r * math.cos(a), geo.cy + r * math.sin(a))
            if all(math.hypot(spot[0] - x, spot[1] - y) >= MIN_GAP for x, y in positions.values()):
                break
        positions[repo.key] = spot
    return positions


# ── labels and arm names ─────────────────────────────────────────────────────

LABEL_MAX_WIDTH = 170             # a longer repository name is cut with an ellipsis
LABEL_STYLE = "medium"
ARM_NAME_AT = 0.82                # where along an arm (fraction of its cut) its name is centred
ARM_NAME_MAX_WIDTH = 180          # a longer focus-area name is cut with an ellipsis
ARM_NAME_FALLBACK_WIDTH = 110     # outside the font a name cannot bend along the arm, so it is kept shorter


def label_size(geo: Geometry) -> float:
    return 12.5 if geo.width < 500 else 13.5


def label_text(name: str, geo: Geometry) -> str:
    return wrap(name, label_size(geo), LABEL_STYLE, LABEL_MAX_WIDTH, max_lines=1)[0]


def _overlap(a: tuple, b: tuple, gap: float = 0.0) -> bool:
    return (a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap
            and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap)


def place_labels(names: list, positions: dict, stars: dict, geo: Geometry, obstacles: list = (),
                 texts: dict = None, avoid: list = ()) -> dict:
    """{name: (x, baseline, anchor, box)} for the stars that get their name written.

    obstacles are boxes of text a label must not sit on (the identity column);
    avoid are boxes it should stay off if it can (the stretches of the arms'
    names, which a label is drawn over when it cannot). texts maps a name to
    what is written for it, when that is not the name itself.

    Each label tries a ring of spots around its star: to the right and to the
    left, level with it or up to seven lines above or below, and centred over
    or under it. The far lines are only reached when the near ones are taken:
    that is what lets four named neighbours each find a place. A spot that would leave the frame is moved inside first.
    The label takes the spot that sits on no other label and no obstacle;
    among those, the one that crosses least of what it should avoid and
    covers the fewest stars; among those, the one nearest the star's right.
    Brighter stars choose first. box is (left, top, width, height) of the
    backdrop behind the text.
    """
    size = label_size(geo)
    atlas = font(LABEL_STYLE)
    ascent = size * atlas["ascent"] / atlas["upm"]
    box_height = size * (atlas["ascent"] + atlas["descent"]) / atlas["upm"] - 2
    placed, taken = {}, list(obstacles)
    for name in sorted(names, key=lambda n: (-stars.get(n, 0), n)):
        x, y = positions[name]
        width = measure(label_text((texts or {}).get(name, name), geo), size, LABEL_STYLE)
        reach = spike_half(stars.get(name, 0)) + 5
        spots = [(side, y + 4.5 + dy, abs(dy) / 15 + (0 if side == "start" else 0.5))
                 for dy in (0, -15, 15, -30, 30, -45, 45, -60, 60, -75, 75, -90, 90, -105, 105) for side in ("start", "end")]
        spots += [("middle", y - reach - 1, 4.0), ("middle", y + reach + ascent - 3, 4.5)]
        best = None
        for anchor, baseline, liking in spots:
            left = {"start": x + reach - 4, "end": x - reach - width - 4, "middle": x - width / 2 - 4}[anchor]
            top = baseline - ascent + 1
            # a star near the edge may have no spot inside the frame: move the label back in
            dx = min(max(left, 2), max(geo.width - 2 - (width + 8), 2)) - left
            dy = min(max(top, 2), max(geo.height - 2 - box_height, 2)) - top
            box = (left + dx, top + dy, width + 8, box_height)
            sitting = sum(1 for other in taken if _overlap(box, other, 2))
            crossing = sum(1 for other in avoid if _overlap(box, other))
            on_itself = box[0] - 3 < x < box[0] + box[2] + 3 and box[1] - 3 < y < box[1] + box[3] + 3
            covered = sum(1 for other, (ox, oy) in positions.items()
                          if other != name and box[0] - 6 < ox < box[0] + box[2] + 6
                          and box[1] - 6 < oy < box[1] + box[3] + 6)
            score = (sitting * 1000 + on_itself * 300 + min(crossing, 4) * 60 + covered * 10
                     + (abs(dx) + abs(dy)) * 0.5 + liking)
            if best is None or score < best[0]:
                text_x = {"start": box[0] + 4, "end": box[0] + box[2] - 4, "middle": box[0] + box[2] / 2}[anchor]
                best = (score, text_x, baseline + dy, anchor, box)
        _score, text_x, baseline, anchor, box = best
        taken.append(box)
        placed[name] = (text_x, baseline, anchor, box)
    return placed


def arm_label(name: str, geo: Geometry) -> str:
    """A focus area's name as it is written along its arm: whole if it is short enough, cut otherwise."""
    limit = ARM_NAME_MAX_WIDTH if covers(clean(name), "italic") else ARM_NAME_FALLBACK_WIDTH
    return (wrap(name, label_size(geo), "italic", limit, max_lines=1) or [""])[0]


def arm_name_paths(model, geo: Geometry) -> list:
    """[(name as written, points)]: a short stretch of curve just outside each named arm, to set its name along.

    The points always run left to right so the name is never upside down. In
    the upper half the curve hugs the arm from outside; in the lower half it
    stands further out, because there the letters rise towards the arm.
    """
    size = label_size(geo)
    per_radius = math.sqrt(1 + geo.b ** 2) / geo.b          # arc length travelled per unit of radius
    paths = []
    for index, (arm, cut) in enumerate(zip(model.arms, arm_cuts(model, geo))):
        label = arm_label(arm.name, geo) if arm.name else ""
        if not label:
            continue
        centre = cut * ARM_NAME_AT
        stretch = 1.09 if geo.point(index, centre)[1] < geo.cy else 1.17
        half = (measure(label, size, "italic") / 2 + 14) / (per_radius * stretch)
        lo, hi = max(centre - half, R0 * 1.5), centre + half
        points = [geo.point(index, lo + (hi - lo) * q / 24, stretch) for q in range(25)]
        if points[-1][0] < points[0][0]:
            points.reverse()
        paths.append((label, points))
    return paths


# ── the whole plate ──────────────────────────────────────────────────────────

T_IN = 3.6                        # seconds from the scattered field to stars resting on the arms
ACTOR_GROUPS, ACTORS_PER_GROUP = 14, 48
ACTOR_SIZES = (0.8, 1.3, 1.3, 2.0)       # three sizes, plain: they live four seconds and need no bloom
FIELD_STARS = 80                  # the sparse background sky
TWINKLING = 8                     # of which this many twinkle
ENTRANCE_STEPS = 16               # more stars than this appear in groups instead of one by one
PULSING = 8                       # active stars, beyond the named ones, whose halo breathes
NAME_SIZES = ((48, 30), (36, 24))  # (largest, smallest) size of the name: desktop, mobile
BYTE_BUDGET = 110_000             # the file's ceiling (spec, section 5)
THINNING = (1.0, 0.75, 0.55, 0.4, 0.25)   # share of the dust kept, tried in order until the file fits


def _identity(profile: dict, theme, geo: Geometry, ts: Typesetter) -> tuple:
    """(markup, boxes) of the name, the tagline and (on desktop) the philosophy line.

    Never animated: readable from the first frame. The boxes are what each
    line occupies, for the star names to keep off.
    """
    mobile = geo.width < 500
    left = 24 if mobile else 44
    room = geo.width - 2 * left if mobile else geo.cx - geo.radius - 10 - left
    largest, smallest = NAME_SIZES[mobile]
    name = str(profile.get("name", ""))
    size = largest
    while size > smallest and measure(name, size, "light") > room:
        size -= 2
    y = 58 if mobile else 196
    lines = [(left, y, (wrap(name, size, "light", room, max_lines=1) or [""])[0], size, theme.ink, "light")]
    tagline = str(profile.get("tagline") or "")
    tag_size = 17 if mobile else 20
    lines.append((left + (0 if mobile else 1), y + (26 if mobile else 32),
                  (wrap(tagline, tag_size, "italic", room, max_lines=1) or [""])[0], tag_size, theme.mute, "italic"))
    if not mobile:
        for index, line in enumerate(wrap(str(profile.get("philosophy") or ""), 14.5, "italic", min(room, 320),
                                          balance=True)):
            lines.append((left + 1, y + 78 + index * 19, line, 14.5, theme.mute, "italic"))
    lines = [line for line in lines if line[2]]
    boxes = [(x, base - text_size * 0.85, measure(text, text_size, style), text_size * 1.15)
             for x, base, text, text_size, _fill, style in lines]
    return "".join(ts.line(x, base, text, text_size, fill, style)
                   for x, base, text, text_size, fill, style in lines), boxes


def _sky(geo: Geometry, theme, rng, motion) -> str:
    """A sparse field of faint stars behind everything; a few of them twinkle."""
    colour = theme.haze if theme.dark else theme.mute
    steady, twinkling = {}, []
    for index in range(FIELD_STARS if geo.width > 500 else FIELD_STARS * 5 // 8):
        x, y = rng.uniform(8, geo.width - 8), rng.uniform(8, geo.height - 8)
        width, opacity = rng.choice((0.8, 1.2, 1.7)), rng.choice((0.25, 0.4, 0.58))
        if index < TWINKLING:
            twinkling.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(width / 2, 2)}" fill="{colour}" '
                             f'fill-opacity="{opacity}"{motion.cls("tw", delay=-index * 0.7)}/>')
        else:
            steady.setdefault((width, opacity), []).append((x, y))
    steady_dots = "".join(dots(points, width, colour, opacity, standalone=False)
                          for (width, opacity), points in sorted(steady.items()))
    return f'<g {PARTICLE_GROUP}>{steady_dots}</g>' + "".join(twinkling)


def _actors(geo: Geometry, cuts: list, theme, rng, motion, ids: list, keep: float = 1.0) -> str:
    """The entrance: a scattered field whose stars swirl inward, bunch up and settle onto the arms.

    Each group is a sparse sample of the whole galaxy that starts rotated and
    enlarged by its own amount; together they read as a random field, and no
    two stars follow the same path. They live four seconds and never stand
    still, so their coordinates are whole pixels. Exists only when motion is on.
    """
    # one set of keyframes; each group brings its own turn (t, u, v) and spread (s, r)
    motion.define("act", (
        f".act{{animation:act {T_IN}s linear both}}"
        "@keyframes act{0%{opacity:0;transform:rotate(var(--t)) scale(var(--s))}12%{opacity:1}"
        "40%{transform:rotate(var(--u)) scale(var(--r));animation-timing-function:cubic-bezier(.55,.05,.85,.5)}"
        "78%{transform:rotate(var(--v)) scale(.5);animation-timing-function:cubic-bezier(.2,.6,.3,1)}"
        "100%{opacity:1;transform:rotate(0deg) scale(1)}}"))
    sizes = [(index, size[1]) for index, size in enumerate(SIZES)]
    groups = []
    for _ in range(ACTOR_GROUPS):
        buckets = {}
        for _ in range(round(ACTORS_PER_GROUP * keep)):
            if rng.random() < 0.22 or not cuts:
                a, r = rng.uniform(0, 2 * math.pi), abs(rng.gauss(0, geo.radius * 0.1))
                spot = (r * math.cos(a), r * math.sin(a))
            else:
                arm = rng.randrange(len(cuts))
                r = rng.uniform(geo.radius * 0.12, cuts[arm])
                x, y = geo.plane(arm, r)
                wobble = 1 + rng.gauss(0, 0.06)
                spot = (x * wobble, y * wobble)
            index = _pick(rng, sizes)
            buckets.setdefault((_pick(rng, theme.dust), ACTOR_SIZES[index], 1.0, False), []).append(spot)
        turn, spread, delay = rng.uniform(110, 290), rng.uniform(2.3, 3.4), rng.uniform(0, 0.3)
        start = {"t": f"{num(-turn)}deg", "u": f"{num(-turn * 0.93)}deg", "v": f"{num(-turn * 0.2)}deg",
                 "s": num(spread, 2), "r": num(spread * 0.97, 2)}
        groups.append(f'<g{motion.cls("act", delay=delay, vars=start)}>'
                      f'{_field(buckets, theme.glow, ids, bloom_on=False, places=0)}</g>')
    motion.define("leave", f".leave{{animation:leave 1s ease-in {num(T_IN + 0.35, 2)}s both}}"
                           "@keyframes leave{0%{opacity:1}100%{opacity:0}}")
    return f'<g{motion.cls("leave", only=True)}>{"".join(groups)}</g>'


def _summary(model) -> str:
    repos = [r for arm in model.arms for r in arm.repos] + list(model.loose)
    if not repos:
        return "No public repositories yet."
    arms = ", ".join(f"{arm.name} {len(arm.repos)}" for arm in model.arms if arm.name)
    brightest = max(repos, key=lambda r: r.stars)
    parts = [f"{len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}"]
    if arms:
        parts.append(f"by focus area: {arms}")
    if model.loose:
        parts.append(f"{len(model.loose)} outside any area")
    parts.append(f"brightest: {brightest.name} with {brightest.stars} star{'' if brightest.stars == 1 else 's'}")
    return "; ".join(parts) + "."


def render(model, profile: dict, theme, mobile: bool = False, motion: bool = True, seed: str = "") -> str:
    """The galaxy header. model is model.GalaxyModel; seed (the login) fixes every random choice.

    Stars and text are data and are always drawn in full. If that leaves the
    file over BYTE_BUDGET, the dust, which stands for nothing, is thinned.
    """
    svg = ""
    for keep in THINNING:
        svg = _compose(model, profile, theme, mobile, motion, seed, keep)
        if len(svg.encode("utf-8")) <= BYTE_BUDGET:
            break
    return svg


def _compose(model, profile: dict, theme, mobile: bool, motion: bool, seed: str, keep: float) -> str:
    geo = Geometry(mobile, len(model.arms))
    mo, ts = Motion(motion), Typesetter()
    rng = random.Random(f"galaxy:{seed}")
    cuts = arm_cuts(model, geo)
    repos = {r.key: r for arm in model.arms for r in arm.repos}
    repos.update({r.key: r for r in model.loose})

    sky = _sky(geo, theme, rng, mo)
    dust_defs, dust_body = dust(geo, cuts, theme, rng, mo, keep)
    positions = place_stars(model, geo, seed)
    ids = [1000]                                           # bloom path ids of the actors, clear of the dust's
    actors = _actors(geo, cuts, theme, rng, mo, ids, keep) if motion else ""

    mo.define("ignite", f".ignite{{animation:ignite 1.9s ease-out {num(T_IN * 0.7, 2)}s both}}"
                        "@keyframes ignite{0%{transform:scale(.08);opacity:0}38%{transform:scale(1.35);opacity:1}"
                        "100%{transform:scale(1)}}")
    mo.define("arrive", f".arrive{{animation:arrive 1.2s ease-out {num(T_IN + 0.1, 2)}s both}}"
                        "@keyframes arrive{from{opacity:0}}")
    hot = "#ffffff" if theme.dark else theme.haze
    k = (0.9, 0.42, 0.09) if theme.dark else (0.4, 0.2, 0.06)
    defs = [
        star_defs(theme),
        f'<radialGradient id="cg"><stop offset="0" stop-color="{hot}" stop-opacity="{k[0]}"/>'
        f'<stop offset=".14" stop-color="{theme.haze}" stop-opacity="{k[1]}"/>'
        f'<stop offset=".5" stop-color="{theme.haze}" stop-opacity="{k[2]}"/>'
        f'<stop offset="1" stop-color="{theme.haze}" stop-opacity="0"/></radialGradient>',
        '<filter id="lb" x="-40%" y="-80%" width="180%" height="260%"><feGaussianBlur stdDeviation="5.5"/></filter>',
        dust_defs,
    ]
    body = [sky,
            f'<g transform="translate({geo.cx} {geo.cy})" {PARTICLE_GROUP}><circle{mo.cls("ignite")} r="{num(geo.radius * 0.5)}" '
            f'fill="url(#cg)"/><g{mo.cls("arrive")}>{dust_body}</g>{actors}</g>']

    # stars appear in the order their repositories were created
    order = [name for name in model.order if name in positions]
    steps = min(len(order), ENTRANCE_STEPS)
    when = {name: T_IN + 0.9 + 1.9 * (index * steps // max(len(order), 1)) / max(steps - 1, 1)
            for index, name in enumerate(order)}
    today = model.today or max((r.pushed for r in repos.values()), default=None)
    state = {name: recency(r.pushed, today) for name, r in repos.items()}
    pulsing = set(model.labels) | set(sorted((n for n in order if state[n] == "now"),
                                             key=lambda n: -repos[n].stars)[:PULSING])

    def glyph(name: str, index: int) -> str:
        return star(repos[name].stars, state[name], theme, mo, phase=index * 0.37, shimmer=name in pulsing)

    def at(name: str, inner: str) -> str:
        x, y = positions[name]
        return f'<g transform="translate({num(x)} {num(y)})">{inner}</g>'

    names_at = len(body)                                   # the arms' names go in here, under the stars
    if len(order) <= ENTRANCE_STEPS:
        # few enough to ignite one by one
        body += [at(name, f'<g{mo.cls("pop", delay=when[name])}>{glyph(name, index)}</g>')
                 for index, name in enumerate(order)]
    else:
        batches = {}
        for index, name in enumerate(order):
            batches.setdefault(when[name], []).append(at(name, glyph(name, index)))
        body += [f'<g{mo.cls("soft", delay=delay)}>{"".join(glyphs)}</g>' for delay, glyphs in sorted(batches.items())]

    size = label_size(geo)
    identity, identity_boxes = _identity(profile, theme, geo, ts)
    arm_names = arm_name_paths(model, geo)
    # what a star's name should stay off if it can: every stretch of an arm's name
    half = size * 0.75
    stretches = [(px - half, py - half, 2 * half, 2 * half) for _name, points in arm_names for px, py in points]
    star_counts = {name: r.stars for name, r in repos.items()}
    written = {name: r.name for name, r in repos.items()}
    labels = []
    for name, (x, baseline, anchor, box) in place_labels(sorted(model.labels & set(positions)), positions,
                                                          star_counts, geo, identity_boxes, written,
                                                          stretches).items():
        labels.append(f'<g{mo.cls("soft", delay=when[name] + 0.35)}>'
                      f'<rect x="{num(box[0])}" y="{num(box[1])}" width="{num(box[2])}" height="{num(box[3])}" rx="8" '
                      f'fill="{theme.chip[0]}" fill-opacity="{theme.chip[1]}" filter="url(#lb)"/>'
                      f'{ts.line(x, baseline, label_text(written[name], geo), size, theme.ink, LABEL_STYLE, anchor, halo=(theme.bg, 2.4, 0.55))}</g>')
    # arm names go under the stars and their names, as in a chart where the grid is drawn first
    if arm_names:
        curved = "".join(ts.on_curve(points, name, size, theme.mute, "italic", halo=(theme.bg, 3.5, 1))
                         for name, points in arm_names)
        body.insert(names_at, f'<g{mo.cls("soft", delay=T_IN + 2.2)}>{curved}</g>')
    body += labels
    body.append(identity)
    defs.append(ts.defs())
    title = f"Galaxy of {profile.get('name', '')}".strip()
    return frame(theme, geo.width, geo.height, "".join(body), title, _summary(model), "".join(defs), mo)
