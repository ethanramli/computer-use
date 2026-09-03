"""Human-like move math. Pure function. No I/O. No APIs."""

import random
from typing import List, Tuple


def points(
    x0: int, y0: int, x1: int, y1: int, seed: int = 0, steps: int = 50
) -> List[Tuple[int, int]]:
    """Seeded cubic Bezier from (x0,y0) to (x1,y1). Exact land on target."""
    rng = random.Random(seed)
    dx = x1 - x0
    dy = y1 - y0
    dist = (dx * dx + dy * dy) ** 0.5 or 1.0
    dev = max(5.0, min(30.0, dist * 0.15))
    # ponytail: one control point pair, mirrored for curve without loops
    cx = (x0 + x1) / 2.0 + rng.uniform(-dev, dev)
    cy = (y0 + y1) / 2.0 + rng.uniform(-dev, dev)
    out: List[Tuple[int, int]] = []
    for i in range(1, steps + 1):
        t = i / steps
        # minimum-jerk easing: 10t^3 - 15t^4 + 6t^5
        e = 10 * t**3 - 15 * t**4 + 6 * t**5
        qx = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * cx + e**2 * x1
        qy = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * cy + e**2 * y1
        out.append((int(round(qx)), int(round(qy))))
    out[-1] = (x1, y1)
    return out
