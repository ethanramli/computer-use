"""Real OS input events for any OS. PyAutoGUI/pynput first, native adapters next."""

BLOCKED_KEYS = {
    ("cmd", "shift", "q"),
    ("win", "l"),
    ("ctrl", "alt", "delete"),
    ("alt", "f4"),
}

CHALLENGE_HINTS = ("password", "permission", "payment", "captcha", "turnstile", "verify you are human")


def validate_xy(x: int, y: int) -> bool:
    return isinstance(x, int) and isinstance(y, int) and x >= 0 and y >= 0


def is_blocked_keys(keys: str) -> bool:
    parts = tuple(p.strip().lower() for p in keys.replace("-", "+").split("+") if p.strip())
    return parts in BLOCKED_KEYS


def looks_like_challenge(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in CHALLENGE_HINTS)
