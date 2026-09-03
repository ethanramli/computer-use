"""Real OS input events for any OS. PyAutoGUI/pynput first, native adapters next."""

import random

BLOCKED_KEYS = {
    ("cmd", "shift", "q"),
    ("win", "l"),
    ("ctrl", "alt", "delete"),
    ("alt", "f4"),
}

CHALLENGE_HINTS = ("password", "permission", "payment", "captcha", "turnstile", "verify you are human")

# Keypress gap distribution measured from real typing (rewards-farmer,
# MIT): 0-0.1s at 37.7%, 0.1-0.2s at 54.9%, 0.2-0.4s at 7.4%.
TYPE_GAPS = (
    ((0.0, 0.1), 0.377),
    ((0.1, 0.2), 0.5492),
    ((0.2, 0.4), 0.0738),
)


def validate_xy(x: int, y: int) -> bool:
    return isinstance(x, int) and isinstance(y, int) and x >= 0 and y >= 0


def is_blocked_keys(keys: str) -> bool:
    parts = tuple(p.strip().lower() for p in keys.replace("-", "+").split("+") if p.strip())
    return parts in BLOCKED_KEYS


def looks_like_challenge(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in CHALLENGE_HINTS)


def next_type_gap(rng: random.Random) -> float:
    """Sample one inter-key delay in seconds from the measured distribution."""
    r = rng.uniform(0, 1)
    acc = 0.0
    for (lo, hi), p in TYPE_GAPS:
        acc += p
        if r <= acc:
            return rng.uniform(lo, hi)
    lo, hi = TYPE_GAPS[-1][0]
    return rng.uniform(lo, hi)
