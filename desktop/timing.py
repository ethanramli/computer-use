"""Timing modes. Native is the no-delay default; human pacing is explicit;
compatibility uses one fixed
measured interval for targets that drop fast events.

Wiki research part (2026-09-04): trailing sleeps after the last event
cannot aid delivery, so gaps apply BETWEEN events only — n chars get
n-1 gaps, and movement duration 0 means post all points immediately.
"""

import math
import random
from typing import Iterator, List

MODES = ("human", "compatibility", "native")

TYPE_GAPS = (
    ((0.0, 0.1), 0.377),
    ((0.1, 0.2), 0.5492),
    ((0.2, 0.4), 0.0738),
)

# compatibility interval: measured minimum for event-dropping targets;
# tuned per target later with evidence (wiki open question 3)
COMPAT_GAP_S = 0.01


class TimingMode:
    COMPAT_GAP_S = COMPAT_GAP_S


def _validate(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown timing mode: {mode} (use {', '.join(MODES)})")
    return mode


def next_type_gap(rng: random.Random) -> float:
    draw = rng.uniform(0, 1)
    cumulative = 0.0
    for (low, high), probability in TYPE_GAPS:
        cumulative += probability
        if draw <= cumulative:
            return rng.uniform(low, high)
    low, high = TYPE_GAPS[-1][0]
    return rng.uniform(low, high)


def gaps_for(mode: str, text: str) -> List[float]:
    """One gap per character. Trailing gap after the last char is dropped
    by the caller; native yields all zeros."""
    _validate(mode)
    if mode == "native":
        return [0.0] * len(text)
    if mode == "compatibility":
        return [COMPAT_GAP_S] * len(text)
    rng = random.Random()  # human mode is explicitly not deterministic
    return [next_type_gap(rng) for _ in text]


def movement_seconds(mode: str, x0: int, y0: int, x1: int, y1: int,
                     target_size: float = 80.0) -> float:
    """Total move duration in seconds. Native = 0 (post immediately).
    Negative results clamp to 0.0."""
    _validate(mode)
    if mode == "native":
        return 0.0
    from .move import duration

    d = duration(x0, y0, x1, y1, target_size)
    return max(0.0, d)
