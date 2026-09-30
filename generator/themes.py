"""Colour themes: two palettes, each in a dark and a light mode.

deep-sky is a night sky with stars in their real colour sequence. cyanotype is
two inks, Prussian blue and paper white, plus one warm colour for what is
alive; in light mode the two inks swap.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

PALETTES = ("deep-sky", "cyanotype")
MODES = ("dark", "light")


def mix(a: str, b: str, t: float) -> str:
    """Blend hex colour a over hex colour b; t=1 gives a, t=0 gives b."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(pa, pb))


@dataclass(frozen=True)
class Theme:
    palette: str
    mode: str
    bg: str
    ink: str
    mute: str                              # secondary text
    faint: str                             # hairlines
    now: str                               # pushed within a month; also the travelling light
    year: str                              # pushed within a year
    dorm: str                              # dormant
    haze: str                              # core glow and the background star field
    dust: tuple[tuple[str, float], ...]    # particle colours and their shares
    glow: float                            # bloom strength around bright particles
    ramp: tuple[str, ...]                  # the eight steps of the language band
    chip: tuple[str, float]                # backdrop behind a star's name: colour, opacity

    @property
    def dark(self) -> bool:
        return self.mode == "dark"


def _derived(bg: str, ink: str, dark: bool) -> dict:
    return {
        "mute": mix(ink, bg, 0.64),
        "faint": mix(ink, bg, 0.22),
        "chip": (mix("#000000", bg, 0.3), 0.5) if dark else (bg, 0.8),
    }


def _ink_ramp(ink: str, bg: str) -> tuple[str, ...]:
    return tuple(mix(ink, bg, a) for a in (1, 0.8, 0.64, 0.5, 0.4, 0.32, 0.26, 0.2))


def _base(palette: str, mode: str, bg: str = "", ink: str = "") -> Theme:
    """The palette in one mode. bg and ink, when given, replace the palette's own before anything is derived."""
    dark = mode == "dark"
    own_bg, own_ink = {
        ("deep-sky", True): ("#0b1020", "#eef1f6"), ("deep-sky", False): ("#f6f7f9", "#151a24"),
        ("cyanotype", True): ("#11305a", "#f5f2e9"), ("cyanotype", False): ("#f1f4f9", "#11305a"),
    }[(palette, dark)]
    bg, ink = bg or own_bg, ink or own_ink
    if palette == "deep-sky" and dark:
        own = dict(now="#9fbcff", year="#fff3dc", dorm="#e0946a", haze="#b4c6f5",
                   dust=(("#a9c7ff", 0.5), ("#f3f6ff", 0.32), ("#ffb98a", 0.18)), glow=1.0,
                   ramp=("#9fbcff", "#c9d8ff", "#f4f2ec", "#ffe3b8", "#ffc584", "#f0a066", "#d18a5c", "#a86a4a"))
    elif palette == "deep-sky":
        own = dict(now="#2447b3", year=ink, dorm="#a3502a", haze=ink,
                   dust=(("#1b2233", 0.55), ("#3b5bc4", 0.28), ("#b5653a", 0.17)), glow=0.6,
                   ramp=("#2447b3", "#4f6fd0", "#8a96b8", "#b9a27e", "#c98a4a", "#b8692f", "#a3502a", "#7d3d20"))
    elif dark:
        own = dict(now="#ffb454", year=ink, dorm=ink, haze=ink,
                   dust=((ink, 0.8), ("#ffd9a0", 0.2)), glow=1.0, ramp=_ink_ramp(ink, bg))
    else:
        own = dict(now="#c9560b", year=ink, dorm=ink, haze=ink,
                   dust=((ink, 0.85), ("#c9560b", 0.15)), glow=0.6, ramp=_ink_ramp(ink, bg))
    return Theme(palette=palette, mode=mode, bg=bg, ink=ink, **_derived(bg, ink, dark), **own)


def _apply_legacy(theme: Theme, overrides: dict) -> Theme:
    """Map the nine colours of the old config onto the dark theme. nebula and star_dust have no meaning now."""
    # rebuild from the new background and ink, so everything the palette derives from them follows
    theme = _base(theme.palette, "dark", overrides.get("void", ""), overrides.get("text_bright", ""))
    changes = {}
    if "text_dim" in overrides:
        changes["mute"] = overrides["text_dim"]
    if "text_faint" in overrides:
        changes["faint"] = overrides["text_faint"]
    dust = list(theme.dust)
    for index, key in enumerate(("synapse_cyan", "dendrite_violet", "axon_amber")):
        if key in overrides and index < len(dust):
            dust[index] = (overrides[key], dust[index][1])
    changes["dust"] = tuple(dust)
    if "synapse_cyan" in overrides:
        changes["now"] = overrides["synapse_cyan"]
    if "axon_amber" in overrides:
        changes["dorm"] = overrides["axon_amber"]
    return replace(theme, **changes)


def get_theme(palette: str, mode: str, overrides: dict | None = None) -> Theme:
    """The theme for a palette and mode. Legacy hex overrides only adjust the dark mode."""
    if palette not in PALETTES:
        raise ValueError(f"unknown palette '{palette}' (expected one of {', '.join(PALETTES)})")
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}' (expected dark or light)")
    theme = _base(palette, mode)
    if overrides and mode == "dark":
        theme = _apply_legacy(theme, overrides)
    return theme
