"""Safety validation. Single source of truth for every argument gate.

Rules:
- Coordinates must be ints; display layouts may use negative origins.
- Regions must be "x,y,w,h" with signed origins and positive width/height.
- Unknown keys are rejected before any input path.
- Challenge/password/payment text stops with needs_attention upstream.
- Batches are validated whole, before the first action runs.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .timing import MODES as TIMING_MODES

BLOCKED_KEYS = {
    ("cmd", "shift", "q"),  # logout
    ("win", "l"),           # lock screen
    ("ctrl", "alt", "delete"),
    ("alt", "f4"),          # close window
}

CHALLENGE_HINTS = (
    "password", "permission", "payment", "captcha", "turnstile",
    "verify you are human",
)

RISK_HINTS = (
    "delete", "remove", "purchase", "buy", "checkout", "pay",
    "send", "publish", "post", "submit", "confirm",
)

RISK_CATEGORIES = {
    "none",
    "deletion",
    "purchase",
    "message",
    "publishing",
    "permission",
    "account_security",
}
CONSEQUENTIAL_RISKS = RISK_CATEGORIES - {"none"}

MAX_TEXT = 100_000
MAX_BATCH_ACTIONS = 500
MAX_DEADLINE_MS = 600_000
MAX_COMMAND_BYTES = 4 * 1024 * 1024

KNOWN_OPS = {
    "observe", "list_apps", "list_windows", "active-window",
    "focus_app", "launch", "move", "click", "double-click", "right_click",
    "drag", "scroll", "type", "press", "hotkey", "wait",
    "click_type", "batch", "stop", "doctor",
}

ALLOWED_PARAMS = {
    "observe": {"region", "metadata_only", "path_mode"},
    "list_apps": set(),
    "list_windows": {"app"},
    "active-window": set(),
    "focus_app": {"app"},
    "launch": {"app"},
    "move": {"x", "y", "frame_id", "seed", "timing", "risk", "confirm"},
    "click": {"x", "y", "frame_id", "risk", "confirm"},
    "double-click": {"x", "y", "frame_id", "risk", "confirm"},
    "right_click": {"x", "y", "frame_id", "risk", "confirm"},
    "drag": {
        "from_x", "from_y", "to_x", "to_y", "frame_id", "seed", "risk", "confirm",
    },
    "scroll": {"direction", "amount", "risk", "confirm"},
    "type": {"text", "app", "timing", "verify", "risk", "confirm"},
    "click_type": {
        "text", "app", "x", "y", "frame_id", "timing", "verify", "risk", "confirm",
    },
    "press": {"keys", "app", "verify", "risk", "confirm"},
    "hotkey": {"keys", "app", "verify", "risk", "confirm"},
    "wait": {"seconds"},
    "batch": {"actions", "deadline_ms", "app", "risk", "confirm"},
    "stop": set(),
    "doctor": set(),
}

KEY_NAMES = {
    "return", "enter", "escape", "esc", "tab", "space", "delete",
    "backspace", "up", "down", "left", "right",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
}

MODIFIERS = {
    "cmd", "command", "shift", "option", "alt", "ctrl", "control", "win",
}
MODIFIER_ALIASES = {
    "command": "cmd",
    "control": "ctrl",
    "option": "alt",
}
MODIFIER_ORDER = ("cmd", "ctrl", "alt", "shift", "win")

_REGION_RE = re.compile(
    r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$"
)


def validate_coordinates(x: Any, y: Any) -> bool:
    return isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool) \
        and not isinstance(y, bool)


def validate_region(region: str) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) or None for empty. Raise ValueError otherwise."""
    if not region or not region.strip():
        return None
    m = _REGION_RE.match(region)
    if not m:
        raise ValueError("region must be x,y,w,h integers")
    x, y, w, h = (int(v) for v in m.groups())
    if w <= 0 or h <= 0:
        raise ValueError("region width/height must be positive")
    return (x, y, w, h)


def is_blocked_keys(keys: str) -> bool:
    parts = tuple(key_parts(keys))
    return parts in BLOCKED_KEYS


def key_parts(keys: str) -> List[str]:
    """Canonicalize aliases, separators, and modifier ordering."""
    raw = [
        p.strip().lower()
        for p in keys.replace("-", "+").replace(",", "+").split("+")
        if p.strip()
    ]
    parts = [MODIFIER_ALIASES.get(part, part) for part in raw]
    modifiers = set(parts) & set(MODIFIER_ORDER)
    return [modifier for modifier in MODIFIER_ORDER if modifier in modifiers] + [
        part for part in parts if part not in modifiers
    ]


def validate_keys(keys: str) -> List[str]:
    parts = key_parts(keys)
    if not parts:
        raise ValueError("keys required")
    for p in parts:
        if p not in KEY_NAMES and p not in MODIFIERS:
            raise ValueError(f"unknown key: {p}")
    return parts


def looks_like_challenge(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in CHALLENGE_HINTS)


def needs_confirmation(text: str) -> bool:
    """Heuristic intent check for the agent-facing confirmation gate."""
    low = text.lower()
    return any(h in low for h in RISK_HINTS)


@dataclass(frozen=True)
class PreflightIssue:
    """Pure validation result consumed by every transport/controller caller."""

    code: str
    message: str


def confirmation_issue(params: dict, text: str = "") -> Optional[PreflightIssue]:
    """Validate explicit risk and require the literal boolean ``True``.

    Text matching is deliberately only an additional signal.  The explicit
    risk field is what lets non-text actions declare consequential intent.
    """
    if "risk" not in params:
        return PreflightIssue("bad_arg", "input requires an explicit risk classification")
    risk = params.get("risk")
    if risk not in RISK_CATEGORIES:
        return PreflightIssue(
            "bad_arg",
            "risk must be one of: " + ", ".join(sorted(RISK_CATEGORIES)),
        )
    consequential = risk in CONSEQUENTIAL_RISKS or needs_confirmation(text)
    if consequential and params.get("confirm") is not True:
        return PreflightIssue(
            "needs_attention",
            "consequential input requires fresh confirmation with confirm: true",
        )
    if "confirm" in params and not isinstance(params["confirm"], bool):
        return PreflightIssue("bad_arg", "confirm must be a boolean")
    return None


def input_state_issue(state: Any) -> Optional[PreflightIssue]:
    """Fail closed when focused-element/window safety metadata is unavailable.

    None means the element metadata is genuinely unavailable (e.g. Chrome's
    address bar doesn't expose it to accessibility).  The app-focus check
    already verified the correct frontmost application, so we allow typing
    to proceed — but only when state is None (unavailable), not when it is
    an empty dict (something is wrong).
    """
    if state is None:
        return None
    if not isinstance(state, dict) or not state:
        return PreflightIssue(
            "needs_attention", "input safety state could not be inspected"
        )
    if any(state.get(flag) is True for flag in ("secure", "payment", "permission", "challenge")):
        return PreflightIssue("needs_attention", "secure or challenge UI is focused")
    searchable = " ".join(
        value for value in state.values() if isinstance(value, str)
    ).casefold()
    has_explicit_flags = any(
        isinstance(state.get(flag), bool)
        for flag in ("secure", "payment", "permission", "challenge")
    )
    if not searchable.strip() and not has_explicit_flags:
        return PreflightIssue(
            "needs_attention", "input safety state could not be inspected"
        )
    hints = CHALLENGE_HINTS + (
        "securetextfield", "credit card", "card number", "security code",
        "passcode", "two-factor", "two factor", "authentication",
        "axdialog", "axsystemdialog",
    )
    if any(hint in searchable for hint in hints):
        return PreflightIssue("needs_attention", "secure or challenge UI is focused")
    return None


def preflight_command(name: str, params: dict) -> Optional[PreflightIssue]:
    """Pure validation shared by individual commands and whole batches."""
    try:
        payload_bytes = len(
            json.dumps(params, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError, RecursionError):
        return PreflightIssue("bad_arg", "params must be JSON-compatible")
    if payload_bytes > MAX_COMMAND_BYTES:
        return PreflightIssue(
            "bad_arg", f"command payload exceeds {MAX_COMMAND_BYTES} UTF-8 bytes"
        )
    if name not in KNOWN_OPS:
        return PreflightIssue("bad_arg", f"unknown command: {name}")
    unknown = set(params) - ALLOWED_PARAMS[name]
    if unknown:
        return PreflightIssue(
            "bad_arg", f"unknown argument(s): {', '.join(sorted(map(str, unknown)))}"
        )
    if "app" in params and not isinstance(params["app"], str):
        return PreflightIssue("bad_arg", "app must be a string")
    if "frame_id" in params and (
        not isinstance(params["frame_id"], str) or not params["frame_id"]
    ):
        return PreflightIssue("bad_arg", "frame_id must be a non-empty string")
    if "seed" in params and (
        isinstance(params["seed"], bool) or not isinstance(params["seed"], int)
    ):
        return PreflightIssue("bad_arg", "seed must be an integer")
    if "verify" in params and params["verify"] not in {"focus", "effect"}:
        return PreflightIssue("bad_arg", "verify must be focus or effect")
    if name == "observe":
        try:
            validate_region(params.get("region", ""))
        except (AttributeError, TypeError, ValueError) as exc:
            return PreflightIssue("bad_arg", str(exc))
        for flag in ("metadata_only", "path_mode"):
            if flag in params and not isinstance(params[flag], bool):
                return PreflightIssue("bad_arg", f"{flag} must be a boolean")
        if params.get("metadata_only") and params.get("path_mode"):
            return PreflightIssue(
                "bad_arg", "metadata_only and path_mode cannot both be true"
            )
        return None
    if name in {"focus_app", "launch"} and not (params.get("app") or "").strip():
        return PreflightIssue("bad_arg", "app must be a non-empty application name")
    if name in {"move", "click", "double-click", "right_click", "click_type"}:
        if not validate_coordinates(params.get("x"), params.get("y")):
            return PreflightIssue("bad_arg", "x/y must be integers")
    if name == "drag":
        for key in ("from_x", "from_y", "to_x", "to_y"):
            if not validate_coordinates(params.get(key), 0):
                return PreflightIssue("bad_arg", f"{key} must be an integer")
    if name == "scroll":
        if params.get("direction", "down") not in {"up", "down", "left", "right"}:
            return PreflightIssue("bad_arg", "direction must be up/down/left/right")
        amount = params.get("amount", 3)
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 100:
            return PreflightIssue("bad_arg", "amount must be an integer from 1-100")
    if name in {"type", "click_type"}:
        try:
            text = validate_text(params.get("text", ""))
        except ValueError as exc:
            return PreflightIssue("bad_arg", str(exc))
        if looks_like_challenge(text):
            return PreflightIssue(
                "needs_attention",
                "text mentions password/permission/payment/challenge UI",
            )
    if name in {"press", "hotkey"}:
        keys = params.get("keys", "")
        try:
            parts = validate_keys(keys)
        except (AttributeError, TypeError, ValueError) as exc:
            return PreflightIssue("bad_arg", str(exc))
        if is_blocked_keys(keys):
            return PreflightIssue("blocked", "key combo blocked for safety")
        regular_keys = [part for part in parts if part not in MODIFIER_ORDER]
        if len(regular_keys) != 1:
            return PreflightIssue(
                "bad_arg", "key input requires exactly one non-modifier key"
            )
        if name == "press" and len(parts) != 1:
            return PreflightIssue(
                "bad_arg", "press accepts one non-modifier key; use hotkey for modifiers"
            )
    if name in {"type", "click_type", "press", "hotkey"}:
        if not (params.get("app") or "").strip():
            return PreflightIssue("focus_required", "keyboard input requires an app")
    if name == "wait":
        seconds = params.get("seconds", 1.0)
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not 0 <= seconds <= 60
        ):
            return PreflightIssue("bad_arg", "wait seconds must be 0-60")
    if name == "batch":
        deadline_ms = params.get("deadline_ms")
        if deadline_ms is not None and (
            isinstance(deadline_ms, bool)
            or not isinstance(deadline_ms, (int, float))
            or not 0 < deadline_ms <= MAX_DEADLINE_MS
        ):
            return PreflightIssue(
                "bad_arg", f"deadline_ms must be 0-{MAX_DEADLINE_MS}"
            )
        return preflight_batch(
            params.get("actions"),
            app=params.get("app"),
            risk=params.get("risk"),
            confirm=params.get("confirm"),
        )
    if name in {"move", "type", "click_type"}:
        mode = params.get("timing", "native")
        if mode not in TIMING_MODES:
            return PreflightIssue(
                "bad_arg",
                f"unknown timing mode: {mode} (use {', '.join(TIMING_MODES)})",
            )
    if name in {
        "move", "click", "double-click", "right_click", "drag", "scroll",
        "type", "click_type", "press", "hotkey",
    }:
        text = params.get("text", "") if name in {"type", "click_type"} else ""
        return confirmation_issue(params, text if isinstance(text, str) else "")
    return None


def validate_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        raise ValueError("text must be a non-empty string")
    if "\0" in text:
        raise ValueError("text must not contain NUL characters")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text exceeds {MAX_TEXT} characters")
    return text


def preflight_batch(
    actions: List[dict], app: Optional[str] = None,
    risk: Optional[str] = None, confirm: Any = None,
) -> Optional[PreflightIssue]:
    """Pure recursive batch validation performed before action zero."""
    if app is not None and (not isinstance(app, str) or not app.strip()):
        return PreflightIssue("bad_arg", "batch app must be a non-empty string")
    batch_app = app.strip() if isinstance(app, str) else ""
    if not actions:
        return PreflightIssue("bad_arg", "empty batch")
    if not isinstance(actions, list):
        return PreflightIssue("bad_arg", "actions must be a list")
    if _action_count(actions) > MAX_BATCH_ACTIONS:
        return PreflightIssue(
            "bad_arg", f"too many actions: maximum is {MAX_BATCH_ACTIONS}"
        )
    for i, a in enumerate(actions):
        if not isinstance(a, dict) or a.get("op") not in KNOWN_OPS:
            return PreflightIssue("bad_arg", f"action {i}: unknown op")
        op = a["op"]
        effective = {key: value for key, value in a.items() if key != "op"}
        if op == "stop":
            return PreflightIssue("bad_arg", f"action {i}: stop cannot be batched")
        if op == "observe" and effective.get("metadata_only") is not True:
            return PreflightIssue(
                "bad_arg",
                f"action {i}: batch observe requires metadata_only",
            )
        if "risk" not in effective and risk is not None:
            effective["risk"] = risk
        if "confirm" not in effective and confirm is not None:
            effective["confirm"] = confirm
        action_app = a.get("app")
        if op in ("type", "click_type", "press", "hotkey") \
                and "app" not in effective and batch_app:
            effective["app"] = batch_app
        if op != "batch":
            issue = preflight_command(op, effective)
            if issue:
                return PreflightIssue(issue.code, f"action {i}: {issue.message}")
        if op == "batch":
            nested = dict(effective)
            if "app" not in nested and batch_app:
                nested["app"] = batch_app
            issue = preflight_command(op, nested)
            if issue:
                return PreflightIssue(issue.code, f"action {i}: {issue.message}")
    return None


def _action_count(actions: List[dict]) -> int:
    """Count the complete nested action tree against one global limit."""
    total = len(actions)
    for action in actions:
        if isinstance(action, dict) and action.get("op") == "batch":
            nested = action.get("actions")
            if isinstance(nested, list):
                total += _action_count(nested)
    return total


def validate_batch(actions: List[dict]) -> Tuple[bool, Optional[str]]:
    """Compatibility wrapper around the shared pure batch preflight."""
    issue = preflight_batch(actions)
    return (issue is None, issue.message if issue else None)
