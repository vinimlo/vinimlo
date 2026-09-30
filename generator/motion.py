"""The motion switch.

Every plate builds its markup through a Motion object. Switched on, it hands
out animation classes and collects the CSS they need, all inside a
prefers-reduced-motion guard. Switched off, it hands out nothing, so the SVG
has no animation at all.

Two rules make that safe:

- An animated element's resting state is its final frame. Animations only
  describe where an element comes from, never where it ends up.
- An element that exists only for motion (a travelling light, a sweep edge)
  carries the class "mo" and opacity="0": invisible at rest, absent when
  motion is off.

Only CSS animation is used. SMIL cannot be switched by a media query.
"""

from __future__ import annotations

from typing import Optional

from generator.svg import num

GUARD = "@media (prefers-reduced-motion: no-preference)"

# name -> CSS for the class and its keyframes. A plate's CSS only includes the ones it uses.
CATALOG = {
    # a halo that breathes: the star was pushed to this month
    "tw": ".tw{animation:tw 3.2s ease-in-out infinite}@keyframes tw{50%{opacity:.4}}",
    # diffraction spikes shimmering
    "spk": ".spk{animation:spk 5s ease-in-out infinite}@keyframes spk{50%{opacity:.3}}",
    # a star igniting; the element must sit at the origin of a translated group
    "pop": ".pop{animation:pop .75s cubic-bezier(.2,1.5,.4,1) both}"
           "@keyframes pop{from{transform:scale(0);opacity:0}}",
    # text and washes fading in
    "soft": ".soft{animation:soft 1.2s ease-out both}@keyframes soft{from{opacity:0}}",
    # a line drawing itself; the path needs pathLength="1"
    "ldraw": ".ldraw{stroke-dasharray:1;animation:ldraw 2s cubic-bezier(.5,0,.2,1) both}"
             "@keyframes ldraw{from{stroke-dashoffset:1}}",
    # the dense core of the galaxy turning slowly
    "swirl": ".swirl{animation:swirl 60s linear infinite}@keyframes swirl{to{transform:rotate(360deg)}}",
    # a light running along a path once per cycle, idle for the rest of it
    "comet": ".comet{animation:comet var(--cy) linear var(--st) infinite}"
             "@keyframes comet{0%{stroke-dashoffset:var(--a);opacity:0}5%{opacity:var(--o)}"
             "40%{opacity:var(--o)}46%,100%{stroke-dashoffset:var(--b);opacity:0}}",
    # a weekly observation rising into place from --d below
    "rise": ".rise{animation:rise .95s cubic-bezier(.2,.9,.3,1.1) both}"
            "@keyframes rise{from{transform:translateY(var(--d));opacity:0}}",
    # a segment opening from its left edge; give it a duration, and keep it in a translated group
    "grow": ".grow{animation:grow linear both}@keyframes grow{from{transform:scaleX(0)}}",
    # light that dims and comes back slowly
    "breathe": ".breathe{animation:breathe 6s ease-in-out infinite}@keyframes breathe{50%{opacity:.5}}",
}


class Motion:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._used: dict[str, str] = {}
        self._defined: dict[str, str] = {}
        self._extra: list[str] = []

    def cls(self, name: str, delay: Optional[float] = None, duration: Optional[float] = None,
            vars: Optional[dict] = None, only: bool = False) -> str:
        """Attributes that attach animation `name` to an element; empty when motion is off.

        only=True marks an element that exists just for motion.
        """
        if not self.enabled:
            return ""
        self._used[name] = self._defined[name] if name in self._defined else CATALOG[name]
        style = []
        if delay is not None:
            style.append(f"animation-delay:{num(delay, 2)}s")
        if duration is not None:
            style.append(f"animation-duration:{num(duration, 2)}s")
        for key, value in (vars or {}).items():
            style.append(f"--{key}:{value}")
        return (f' class="{name}{" mo" if only else ""}"' + (' opacity="0"' if only else "")
                + (f' style="{";".join(style)}"' if style else ""))

    def only(self, svg: str) -> str:
        """Markup that exists just for motion."""
        return svg if self.enabled else ""

    def define(self, name: str, css: str) -> None:
        """An animation class of the plate's own; its CSS is only emitted if cls() uses it."""
        if self.enabled:
            self._defined[name] = css

    def add(self, css: str) -> None:
        """Plate-specific rules and keyframes."""
        if self.enabled:
            self._extra.append(css)

    def css(self) -> str:
        """Everything collected, inside the reduced-motion guard; empty if there is nothing to animate."""
        body = "".join(self._used.values()) + "".join(self._extra)
        return f"{GUARD}{{{body}}}" if self.enabled and body else ""
