"""Human-like move math. Pure functions. No I/O. No APIs. No browser.

Adapted from the trajectory model in User0332/rewards-farmer
(MIT, Copyright (c) 2026 Carl Furtado): cubic Bezier with near-endpoint
control points, distortion zones for micro-jitter, logistic time warp,
Fitts-law duration. Selenium driver, page scrolling, and rewards workflow
from that repo are NOT used here. OS delivery lives in platforms/.

CORE RULE: Every input action (click, type, press, hotkey, drag, scroll)
MUST move the cursor visibly along this path before executing. The cursor
never teleports. This is non-negotiable — the user must see where input
is going. See AGENTS.md for the full requirement.
"""

import math
import random
from typing import Callable, List, Tuple

Point = Tuple[int, int]

INTERVAL_RADIUS = (20, 40)
DEVIATION_INTERVAL = (1, 5)
ZONE_LENGTH = 0.05
ZONE_FREQUENCY = 0.15

FITTS_A = 0.5500
FITTS_B = 0.1276


def _bezier_1d(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    return (
        (1 - t) ** 3 * p0
        + 3 * t * (1 - t) ** 2 * p1
        + 3 * (1 - t) * t**2 * p2
        + t**3 * p3
    )


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    return (
        int(round(_bezier_1d(p0[0], p1[0], p2[0], p3[0], t))),
        int(round(_bezier_1d(p0[1], p1[1], p2[1], p3[1], t))),
    )


def _anysign(rng: random.Random, a: int, b: int) -> int:
    v = rng.randint(a, b)
    return -v if rng.randint(0, 1) else v


def _logistic(x: float) -> float:
    return 2.0 / (1.0 + math.exp(-x)) - 1.0


def _control_points(rng: random.Random, start: Point, end: Point) -> Tuple[Point, Point]:
    # ponytail: shrink offsets when start==end so keystroke cues pulse in
    # place instead of circling; long moves keep scale 1.0 (bit-identical).
    span = math.hypot(end[0] - start[0], end[1] - start[1])
    scale = min(1.0, max(span, 8.0) / 80.0)

    def off() -> int:
        return int(round(_anysign(rng, *INTERVAL_RADIUS) * scale))

    # Control points near endpoints keep path directed; a p2
    # behind the target yields a natural occasional overshoot
    p1 = (start[0] + off(), start[1] + off())
    p2 = (end[0] + off(), end[1] + off())
    return p1, p2


def path_function(
    start: Point, end: Point, seed: int = 0
) -> Callable[[float], Point]:
    """Return f(t) for t in [0, 4.5]. t maps through the logistic warp."""
    rng = random.Random(seed)
    p0, p3 = start, end
    p1, p2 = _control_points(rng, start, end)
    zones = [
        (i * ZONE_LENGTH, (i + 1) * ZONE_LENGTH)
        for i in range(int(1 / ZONE_LENGTH))
        if rng.uniform(0, 1) < ZONE_FREQUENCY
    ]
    offsets = [
        (_anysign(rng, *DEVIATION_INTERVAL), _anysign(rng, *DEVIATION_INTERVAL))
        for _ in zones
    ]

    def fn(t: float) -> Point:
        warped = _logistic(max(0.0, min(4.5, t)))
        # logistic(4.5) is ~0.978, so rescale to land exactly on end
        tn = warped / _logistic(4.5)
        x, y = _bezier(p0, p1, p2, p3, tn)
        for (z0, z1), (ox, oy) in zip(zones, offsets):
            if z0 <= tn <= z1:
                prog = (tn - z0) / (z1 - z0)
                k = prog * 2 if prog < 0.5 else (1 - (prog - 0.5) * 2)
                return (x + int(round(ox * k)), y + int(round(oy * k)))
        return (x, y)

    return fn


def movement_time(distance: float, target_size: float = 80.0) -> float:
    """Fitts law: MT = a + b * log2(2D / W). W defaults to 80px."""
    w = max(1.0, target_size)
    d = max(1.0, distance)
    return FITTS_A + FITTS_B * math.log2((2.0 * d) / w)


def points(
    x0: int, y0: int, x1: int, y1: int, seed: int = 0, steps: int = 50
) -> List[Point]:
    """Seeded distorted-Bezier points from (x0,y0) to (x1,y1). Exact land."""
    fn = path_function((x0, y0), (x1, y1), seed=seed)
    out = [fn((i / steps) * 4.5) for i in range(1, steps + 1)]
    out[-1] = (x1, y1)
    return out


def duration(
    x0: int, y0: int, x1: int, y1: int, target_size: float = 80.0
) -> float:
    """Fitts-law duration for the move in seconds."""
    return movement_time(math.hypot(x1 - x0, y1 - y0), target_size)
