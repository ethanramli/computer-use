"""macOS adapter. Real OS input via the bundled cghelper binary.

No third-party deps: Python side is stdlib subprocess only. The helper
is tiny C against system frameworks (see csrc/cghelper.c). Needs
Accessibility permission at runtime; without it posts are dropped.

Every action takes an optional post hook. Tests pass a fake recorder
so nothing moves during verification.
"""

import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

Point = Tuple[int, int]

FLAG_CMD = 1 << 20
FLAG_SHIFT = 1 << 17
FLAG_OPTION = 1 << 19
FLAG_CTRL = 1 << 18

KEYCODES = {
    "return": 36, "enter": 36, "escape": 53, "esc": 53, "tab": 48,
    "space": 49, "delete": 51, "backspace": 51,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4,
    "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31,
    "p": 35, "q": 12, "r": 15, "s": 1, "t": 17, "u": 32, "v": 9,
    "w": 13, "x": 7, "y": 16, "z": 26,
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25, "0": 29,
}

MOD_FLAGS = {
    "cmd": FLAG_CMD, "command": FLAG_CMD,
    "shift": FLAG_SHIFT, "option": FLAG_OPTION, "alt": FLAG_OPTION,
    "ctrl": FLAG_CTRL, "control": FLAG_CTRL,
}


def helper_path() -> Path:
    p = Path(__file__).resolve().parent.parent.parent / "bin" / "cghelper"
    if not p.exists():
        raise RuntimeError("cghelper missing: build with clang (see csrc/cghelper.c)")
    return p


def _run(args: List[str], stdin_text: Optional[str] = None) -> str:
    try:
        r = subprocess.run(
            [str(helper_path())] + args,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise RuntimeError("cghelper missing: build with clang (see csrc/cghelper.c)")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or f"cghelper exit {r.returncode}").strip())
    return (r.stdout or "").strip()


def trusted() -> bool:
    """Read-only Accessibility trust check for `desktop doctor`."""
    try:
        return _run(["trusted"]) == "1"
    except Exception:
        return False


def cursor_position() -> Point:
    """Read-only cursor read. Safe to call any time."""
    x, y = _run(["pos"]).split()
    return (int(x), int(y))


def replay(points: List[Point], total_secs: float, post: Optional[Callable] = None) -> None:
    """Post MouseMoved for each point, spread over total_secs."""
    if post is not None:
        for x, y in points:
            post(("move", x, y))
        return
    gap_us = int(total_secs * 1_000_000 / max(1, len(points)))
    body = "".join(f"{x} {y}\n" for x, y in points)
    _run(["movebatch", str(gap_us)], stdin_text=body)


def click(x: int, y: int, button: str = "left", double: bool = False, post: Optional[Callable] = None) -> None:
    if post is not None:
        post(("click", x, y, button, double))
        return
    _run(["click", str(x), str(y), "1" if button == "right" else "0", "2" if double else "1"])


def drag(frm: Point, to: Point, path: List[Point], post: Optional[Callable] = None) -> None:
    if post is not None:
        post(("drag", frm, to, len(path)))
        return
    body = "".join(f"{x} {y}\n" for x, y in path)
    _run(["drag", str(frm[0]), str(frm[1]), str(to[0]), str(to[1])], stdin_text=body)


def scroll(direction: str, amount: int, post: Optional[Callable] = None) -> None:
    if post is not None:
        post(("scroll", direction, amount))
        return
    sign = -1 if direction in ("down", "right") else 1
    # ponytail ultra: one spawn, ticks loop in C
    _run(["scroll", str(sign * 3), "0", str(max(1, amount))])


def type_text(text: str, gaps, post: Optional[Callable] = None) -> int:
    """Type via Unicode key events. Returns chars posted."""
    if post is not None:
        n = 0
        for ch in text:
            post(("type", ch, next(gaps)))
            n += 1
        return n
    sampled = [next(gaps) for _ in text]
    mean_us = int(sum(sampled) / len(sampled) * 1_000_000) if sampled else 0
    out = _run(["type", str(mean_us)], stdin_text=text)
    return int(out) if out else 0


def hotkey(keys: str, post: Optional[Callable] = None) -> None:
    """Press combos like cmd,s or ctrl+alt+t."""
    parts = [p.strip().lower() for p in keys.replace("+", ",").split(",") if p.strip()]
    flags = 0
    key = ""
    for p in parts:
        if p in MOD_FLAGS:
            flags |= MOD_FLAGS[p]
        else:
            key = p
    if not key or key not in KEYCODES:
        raise ValueError(f"unknown key: {key or keys}")
    if post is not None:
        post(("hotkey", KEYCODES[key], flags))
        return
    _run(["key", str(KEYCODES[key]), str(flags)])
