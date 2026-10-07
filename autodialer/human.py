"""Human-like timing and touch-position generation.

Real people do not tap the exact centre of a key at a fixed rhythm. Taps land
somewhere around the middle of the key, each press lasts a slightly different
time, the gap between presses varies, and people pause briefly between digit
groups (e.g. after the area code).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .ui import Bounds


@dataclass
class HumanProfile:
    # Gap between key presses (log-normal, seconds).
    key_gap_median: float = 0.32
    key_gap_sigma: float = 0.35
    key_gap_min: float = 0.12
    key_gap_max: float = 1.2
    # Extra "chunking" pause every few digits, like reading a number in groups.
    group_pause_chance: float = 0.35
    group_pause: tuple[float, float] = (0.35, 0.9)
    # How long a finger stays on the glass (milliseconds).
    press_ms: tuple[int, int] = (55, 130)
    long_press_ms: tuple[int, int] = (750, 1000)
    # Spread of the touch point around the key centre, as a fraction of the
    # key size (standard deviation). Clamped to the inner part of the key.
    spread: float = 0.12
    safe_fraction: float = 0.35
    # Tiny finger roll while pressed, in pixels.
    drift_px: int = 3
    # "Think" time before starting to dial and before pressing call.
    before_dial: tuple[float, float] = (0.8, 1.8)
    before_call: tuple[float, float] = (0.7, 1.6)


class Humanizer:
    def __init__(self, profile: HumanProfile | None = None, rng: random.Random | None = None):
        self.p = profile or HumanProfile()
        self.rng = rng or random.Random()

    def point_in(self, b: Bounds) -> tuple[int, int]:
        """A plausible touch point inside ``b``, biased toward its centre."""
        cx, cy = b.center
        max_dx = max(1.0, b.width * self.p.safe_fraction)
        max_dy = max(1.0, b.height * self.p.safe_fraction)
        dx = self.rng.gauss(0, b.width * self.p.spread)
        dy = self.rng.gauss(0, b.height * self.p.spread)
        dx = max(-max_dx, min(max_dx, dx))
        dy = max(-max_dy, min(max_dy, dy))
        x = min(b.right - 1, max(b.left, int(round(cx + dx))))
        y = min(b.bottom - 1, max(b.top, int(round(cy + dy))))
        return x, y

    def drift(self, x: int, y: int, b: Bounds) -> tuple[int, int]:
        d = self.p.drift_px
        x2 = min(b.right - 1, max(b.left, x + self.rng.randint(-d, d)))
        y2 = min(b.bottom - 1, max(b.top, y + self.rng.randint(-d, d)))
        return x2, y2

    def press_duration_ms(self, long: bool = False) -> int:
        lo, hi = self.p.long_press_ms if long else self.p.press_ms
        return self.rng.randint(lo, hi)

    def key_gap(self, index: int) -> float:
        """Seconds to wait before pressing the key at position ``index``."""
        gap = self.rng.lognormvariate(math.log(self.p.key_gap_median), self.p.key_gap_sigma)
        gap = min(self.p.key_gap_max, max(self.p.key_gap_min, gap))
        if index > 0 and index % self.rng.choice((3, 4, 5)) == 0 \
                and self.rng.random() < self.p.group_pause_chance:
            gap += self.rng.uniform(*self.p.group_pause)
        return gap

    def pause(self, span: tuple[float, float]) -> float:
        return self.rng.uniform(*span)
