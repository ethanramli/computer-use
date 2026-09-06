"""macOS adapter. Real OS input via the bundled cghelper binary.

Native input uses a tiny C helper against system frameworks (see
native/cghelper.c); screen capture uses MSS. The helper needs
Accessibility permission at runtime; without it posts are dropped.

Every action takes an optional post hook. Tests pass a fake recorder
so nothing moves during verification.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .base import Backend, CapabilityError, FocusError, InputCancelled

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
    "w": 13, "x": 7, "y": 16, "z": 6,
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25, "0": 29,
}

MOD_FLAGS = {
    "cmd": FLAG_CMD, "command": FLAG_CMD,
    "shift": FLAG_SHIFT, "option": FLAG_OPTION, "alt": FLAG_OPTION,
    "ctrl": FLAG_CTRL, "control": FLAG_CTRL,
}


def helper_path() -> Path:
    """Resolve the cghelper binary.

    Search order (first existing wins):
    1. Bundled copy inside the installed package (desktop/_bin/cghelper)
       — present after `pip install .` / pipx.
    2. Dev-tree path (build/cghelper) for development checkouts.
    Raises with build instructions when neither exists.
    """
    candidates = [
        Path(__file__).resolve().parent.parent / "_bin" / "cghelper",
        Path(__file__).resolve().parent.parent.parent / "build" / "cghelper",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise CapabilityError(
        "helper",
        "cghelper missing: run ./install (builds it with clang) or build "
        "manually: clang -O2 -o build/cghelper native/cghelper.c -framework "
        "CoreGraphics -framework ApplicationServices")


def _run(
    args: List[str],
    stdin_text: Optional[str] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    total_primitives: int = 1,
) -> str:
    if cancelled is not None and cancelled():
        raise InputCancelled(args[0], 0, total_primitives)
    try:
        process = subprocess.Popen(
            [str(helper_path())] + args,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("cghelper missing: build with clang (see native/cghelper.c)")
    pending_input = stdin_text
    stop_sent = False
    deadline = time.monotonic() + 120.0
    stop_deadline = None
    while True:
        try:
            stdout, stderr = process.communicate(input=pending_input, timeout=0.01)
            break
        except subprocess.TimeoutExpired:
            pending_input = None
            if cancelled is not None and cancelled() and not stop_sent:
                process.terminate()
                stop_sent = True
                stop_deadline = time.monotonic() + 1.0
            if stop_deadline is not None and time.monotonic() >= stop_deadline:
                process.kill()
            if time.monotonic() >= deadline:
                process.kill()
                stdout, stderr = process.communicate()
                raise RuntimeError("cghelper timed out after 120 seconds")
    output = (stdout or "").strip()
    if process.returncode == 130 or stop_sent:
        try:
            completed = int(output.splitlines()[-1]) if output else 0
        except ValueError:
            completed = 0
        raise InputCancelled(args[0], completed, total_primitives)
    if process.returncode == 5 and "Accessibility trust" in (stderr or ""):
        raise CapabilityError("accessibility", (stderr or "").strip())
    if process.returncode != 0:
        raise RuntimeError((stderr or f"cghelper exit {process.returncode}").strip())
    return output


def trusted() -> bool:
    """Read-only Accessibility trust check for `desktop doctor`."""
    try:
        return _run(["trusted"]) == "1"
    except CapabilityError:
        raise
    except Exception:
        return False


def _element_metadata(args: List[str]) -> dict:
    try:
        state = json.loads(_run(args))
    except RuntimeError as exc:
        capability = (
            "accessibility" if "Accessibility trust" in str(exc)
            else args[0]
        )
        raise CapabilityError(capability, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise CapabilityError(
            args[0], "cghelper returned invalid accessibility metadata"
        ) from exc
    if not isinstance(state, dict):
        raise CapabilityError(
            args[0], "cghelper returned invalid accessibility metadata"
        )
    return state


def display_layout() -> dict:
    try:
        layout = json.loads(_run(["displays"]))
    except RuntimeError as exc:
        raise CapabilityError("display_layout", str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise CapabilityError(
            "display_layout", "cghelper returned invalid display metadata"
        ) from exc
    if not isinstance(layout, dict) or not isinstance(layout.get("displays"), list):
        raise CapabilityError(
            "display_layout", "cghelper returned invalid display metadata"
        )
    return layout


def cursor_position() -> Point:
    """Read-only cursor read. Safe to call any time."""
    x, y = _run(["pos"]).split()
    return (int(x), int(y))


def active_window() -> str:
    """Return macOS's focused application, ignoring transparent overlay windows."""
    script = (
        'ObjC.import("AppKit"); '
        "const app = $.NSWorkspace.sharedWorkspace.frontmostApplication; "
        'app ? ObjC.unwrap(app.localizedName) : ""'
    )
    r = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    name = (r.stdout or "").strip()
    if r.returncode == 0 and name:
        return name
    # Window ordering remains a useful fallback on systems without AppKit/JXA.
    try:
        return _run(["frontmost"])
    except RuntimeError as exc:
        raise CapabilityError("active_window", str(exc)) from exc


def replay(
    points: List[Point], total_secs: float, post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    """Post MouseMoved for each point, spread over total_secs.

    Measured delivery floor: a 0-gap stream of distinct moves is coalesced
    and distorted by the macOS window server (cursor lands short of target);
    a >=2ms inter-event gap lands exactly (verified live 2026-09-04). This
    is the documented compatibility interval, not human pacing.
    """
    MIN_GAP_US = 2000  # measured window-server coalescing floor
    if post is not None:
        for index, (x, y) in enumerate(points):
            if cancelled is not None and cancelled():
                raise InputCancelled("move", index, len(points))
            post(("move", x, y))
        return
    gap_us = int(total_secs * 1_000_000 / max(1, len(points)))
    if len(points) > 1 and gap_us < MIN_GAP_US:
        gap_us = MIN_GAP_US
    body = "".join(f"{x} {y}\n" for x, y in points)
    _run(
        ["movebatch", str(gap_us)], stdin_text=body,
        cancelled=cancelled, total_primitives=len(points),
    )


def click(
    x: int, y: int, button: str = "left", double: bool = False,
    post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    total = 2 if double else 1
    if cancelled is not None and cancelled():
        raise InputCancelled("click", 0, total)
    if post is not None:
        post(("click", x, y, button, double))
        return
    _run(
        ["click", str(x), str(y), "1" if button == "right" else "0", str(total)],
        cancelled=cancelled, total_primitives=total,
    )


def drag(
    frm: Point, to: Point, path: List[Point], post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    if post is not None:
        completed = 0
        for point in path:
            if cancelled is not None and cancelled():
                raise InputCancelled("drag", completed, len(path))
            post(("drag-point", point))
            completed += 1
        return
    body = "".join(f"{x} {y}\n" for x, y in path)
    _run(
        ["drag", str(frm[0]), str(frm[1]), str(to[0]), str(to[1])],
        stdin_text=body, cancelled=cancelled, total_primitives=len(path),
    )


def scroll(
    direction: str, amount: int, post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    if post is not None:
        for completed in range(amount):
            if cancelled is not None and cancelled():
                raise InputCancelled("scroll", completed, amount)
            post(("scroll", direction, 1))
        return
    delta = -3 if direction in ("down", "right") else 3
    dy = delta if direction in ("up", "down") else 0
    dx = delta if direction in ("left", "right") else 0
    # ponytail ultra: one spawn, ticks loop in C
    _run(
        ["scroll", str(dy), str(dx), str(max(1, amount))],
        cancelled=cancelled, total_primitives=amount,
    )


def type_text(
    text: str, gaps, post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> int:
    """Type via Unicode key events. Returns chars posted."""
    if post is not None:
        n = 0
        for ch in text:
            if cancelled is not None and cancelled():
                raise InputCancelled("type", n, len(text))
            post(("type", ch, next(gaps)))
            n += 1
        return n
    sampled = [next(gaps) for _ in text]
    mean_us = int(sum(sampled) / len(sampled) * 1_000_000) if sampled else 0
    out = _run(
        ["type", str(mean_us)], stdin_text=text,
        cancelled=cancelled, total_primitives=len(text),
    )
    return int(out) if out else 0


def _clean_app(app: str) -> str:
    if not isinstance(app, str) or not app.strip():
        raise ValueError("app must be a non-empty application name or path")
    return app.strip()


def _expected_app_name(app: str) -> str:
    name = Path(app).name if "/" in app else app
    return name[:-4] if name.casefold().endswith(".app") else name


def _app_matches(requested: str, actual: str) -> bool:
    return _expected_app_name(requested).casefold() == actual.strip().casefold()


def _open_app(app: str) -> None:
    # Activate through Launch Services/JXA first. On automation hosts, `open -a`
    # can consult the wrong bootstrap namespace even though the app is running.
    # The app is argv, not script text, so application names cannot become code.
    script = "function run(argv) { Application(argv[0]).activate(); }"
    activate_args = ["/usr/bin/osascript", "-l", "JavaScript", "-e", script, app]
    r = subprocess.run(
        activate_args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode == 0:
        return
    opened = subprocess.run(["open", "-a", app], capture_output=True, text=True, timeout=60)
    if opened.returncode != 0:
        raise RuntimeError((opened.stderr or r.stderr or f"cannot open {app}").strip())
    r = subprocess.run(activate_args, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or f"cannot activate {app}").strip())


def focus_app(
    app: str,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
    post: Optional[Callable] = None,
) -> str:
    """Activate an installed app and wait until its window is provably frontmost."""
    app = _clean_app(app)
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if post is not None:
        post(("focus", app))
        return app
    # Do not re-activate an app that is already foreground: activation can reset
    # its focused control (for example, Chrome's address bar after Cmd+L).
    try:
        current = active_window()
    except (CapabilityError, RuntimeError):
        current = ""
    if _app_matches(app, current):
        return current
    _open_app(app)
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            last = active_window()
        except (CapabilityError, RuntimeError):
            last = ""
        if _app_matches(app, last):
            return last
        time.sleep(poll_interval)
    actual = last or "unknown"
    raise FocusError(
        f"cannot verify focus for '{_expected_app_name(app)}'; frontmost app is '{actual}'"
    )


def launch(app: str, post: Optional[Callable] = None) -> str:
    """Open any installed macOS application and verify it is foreground.

    ``app`` is intentionally not an allow-list: Launch Services resolves
    application names and paths, so this works for every installed app.
    """
    app = _clean_app(app)
    if post is not None:
        post(("launch", app))
        return app
    return focus_app(app)


def hotkey(
    keys: str, post: Optional[Callable] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    """Press combos like cmd,s or ctrl+alt+t."""
    parts = [p.strip().lower() for p in keys.replace("+", ",").split(",") if p.strip()]
    if "win" in parts:
        raise ValueError("win modifier is not supported on macOS")
    flags = 0
    key = ""
    for p in parts:
        if p in MOD_FLAGS:
            flags |= MOD_FLAGS[p]
        else:
            key = p
    if not key or key not in KEYCODES:
        raise ValueError(f"unknown key: {key or keys}")
    if cancelled is not None and cancelled():
        raise InputCancelled("key", 0, 1)
    if post is not None:
        post(("hotkey", KEYCODES[key], flags))
        return
    _run(
        ["key", str(KEYCODES[key]), str(flags)],
        cancelled=cancelled, total_primitives=1,
    )


class MacosBackend(Backend):
    """Backend adapter over the cghelper functions above."""

    def backend_name(self) -> str:
        return "macos"

    def app_matches(self, requested: str, actual: str) -> bool:
        return _app_matches(requested, actual)

    def trusted(self) -> bool:
        return trusted()

    def helper_available(self) -> bool:
        path = helper_path()
        return path.is_file() and os.access(str(path), os.X_OK)

    def screen_recording_authorized(self) -> bool:
        return _run(["screen-recording"]) == "1"

    def screen_size(self) -> dict:
        import mss  # type: ignore

        with mss.MSS() as sct:
            mon = sct.monitors[0]
            if mon["width"] <= 0 or mon["height"] <= 0:
                # Screen Recording permission missing/revoked: MSS reports a
                # 0x0 virtual monitor. Never fake success — fail honestly.
                from .base import CapabilityError

                raise CapabilityError(
                    "screen_size",
                    "screen capture unavailable: display reports 0x0 "
                    "(Screen Recording permission missing or revoked)")
            return {"width": mon["width"], "height": mon["height"]}

    def display_layout(self) -> dict:
        return display_layout()

    def active_window(self) -> str:
        return active_window()

    def focused_element(self):
        return _element_metadata(["focused"])

    def element_at(self, x: int, y: int):
        return _element_metadata(["element", str(x), str(y)])

    def cursor_position(self) -> Point:
        return cursor_position()

    def capture_region(self, x, y, w, h):
        if not self.screen_recording_authorized():
            raise CapabilityError(
                "screen_recording",
                "Screen Recording permission is missing or was revoked",
            )
        import mss  # type: ignore

        with mss.MSS() as sct:
            shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
            raw = bytes(shot.rgb)
        return raw, {"width": w, "height": h, "pixel_format": "rgb"}

    def move_path(self, points, total_secs: float, cancelled=None) -> None:
        replay(list(points), total_secs, cancelled=cancelled)

    def click(self, x, y, button="left", double=False, cancelled=None) -> None:
        click(x, y, button=button, double=double, cancelled=cancelled)

    def drag(self, frm, to, path, cancelled=None) -> None:
        drag(frm, to, list(path), cancelled=cancelled)

    def scroll(self, direction: str, amount: int, cancelled=None) -> None:
        scroll(direction, amount, cancelled=cancelled)

    def type_text(self, text: str, gaps, cancelled=None) -> int:
        return type_text(text, gaps, cancelled=cancelled)

    def press(self, key: str, cancelled=None) -> None:
        hotkey(key, cancelled=cancelled)

    def hotkey(self, keys: str, cancelled=None) -> None:
        hotkey(keys, cancelled=cancelled)

    def launch(self, app: str) -> str:
        return launch(app)

    def focus_app(self, app: str, timeout: float = 5.0) -> str:
        return focus_app(app, timeout=timeout)

    def release_all(self) -> None:
        _run(["release"])
