"""Platform-neutral controller. Policy layer: validation, focus verification,
frame freshness, cancellation, batch receipts. All OS work goes through the
Backend adapter. No network. No model calls. No app-specific branches.
"""

import copy
import json
import threading
import time
from typing import Any, Dict, Optional

from . import protocol, safety, timing
from ._version import __version__
from .frames import FrameStore, FrameTooLarge, validate_layout
from .move import points
from .platforms.base import Backend, CapabilityError, FocusError, InputCancelled

EXIT_CODES = {
    "ok": 0,
    "bad_arg": 2,
    "needs_attention": 3,
    "blocked": 4,
    "unsupported": 4,
    "unimplemented": 4,
    "focus_required": 3,
    "focus_failed": 5,
    "stale_frame": 5,
    "exec_failed": 5,
    "cancelled": 0,
    "deadline_exceeded": 5,
}

MAX_WAIT_SECONDS = 60.0
MAX_ACTIVE_WINDOW_BYTES = 16 * 1024


INTERNAL_PARAMS = ("_in_batch", "_batch_app", "_deadline")

def _strip_internal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal controller params (underscore-prefixed) from
    untrusted input. Underscore-prefixed keys are reserved for the
    controller's own cross-command context (_in_batch, _batch_app)."""
    return {k: v for k, v in params.items()
            if not str(k).startswith("_")}


def _proves_text_insertion(before: str, after: str, text: str) -> bool:
    """Prove that ``after`` is ``before`` plus one exact insertion."""
    if len(after) != len(before) + len(text):
        return False
    index = 0
    while index < len(before) and before[index] == after[index]:
        index += 1
    return (
        after[index:index + len(text)] == text
        and after[index + len(text):] == before[index:]
    )


def _validated_typed_count(value: Any, requested: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > requested
    ):
        raise RuntimeError("backend returned an invalid typed-character count")
    return value


class Controller:
    """Owns one backend, one frame store, one ordered input path, one
    request-scoped cancellation token. All commands enter through command()."""

    def __init__(self, backend: Backend, dry_run: bool = True,
                 frame_bytes: int = 64 * 1024 * 1024):
        self.backend = backend
        self.dry_run = dry_run
        self.frames = FrameStore(max_bytes=frame_bytes)
        self._command_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_request_id: Any = None
        self._active_generation = 0
        self._active_cancel: Optional[threading.Event] = None

    def close(self) -> None:
        self.frames.close()

    # -- cancellation -----------------------------------------------------

    def request_cancel(self, request_id: Any = None,
                       generation: Optional[int] = None) -> bool:
        """Cancel only the matching active request; idle signals are ignored."""
        with self._state_lock:
            if self._active_cancel is None:
                return False
            if request_id is not None and request_id != self._active_request_id:
                return False
            if generation is not None and generation != self._active_generation:
                return False
            self._active_cancel.set()
            return True

    def stop(self) -> bool:
        return self.request_cancel()

    def _cancelled(self) -> bool:
        with self._state_lock:
            token = self._active_cancel
        return bool(token and token.is_set())

    def _check_cancel(self) -> Optional[Dict[str, Any]]:
        if self._cancelled():
            return protocol.fail(
                "cancelled", "operation cancelled by stop",
                "issue a new request; cancellation is request-scoped",
            )
        return None

    @staticmethod
    def _deadline_expired(params: Dict[str, Any]) -> bool:
        deadline = params.get("_deadline")
        return isinstance(deadline, (int, float)) and time.monotonic() >= deadline

    def _check_abort(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        cancelled = self._check_cancel()
        if cancelled:
            return cancelled
        if self._deadline_expired(params):
            return protocol.fail(
                "deadline_exceeded",
                "batch deadline exceeded",
                "inspect partial progress before issuing a new request",
            )
        return None

    def _cancel_probe(self, params: Dict[str, Any]):
        return lambda: self._cancelled() or self._deadline_expired(params)

    # -- entry point --------------------------------------------------------

    def command(self, name: str, params: Dict[str, Any],
                request_id: Any = None) -> Dict[str, Any]:
        """Run one command. Returns protocol envelope dict."""
        if name == "stop":
            try:
                if params is not None and not isinstance(params, dict):
                    raise TypeError("command params must be an object")
                stop_params = {} if params is None else dict(params)
                for key in INTERNAL_PARAMS:
                    stop_params.pop(key, None)
                issue = safety.preflight_command(name, stop_params)
            except (TypeError, ValueError, RecursionError):
                issue = safety.PreflightIssue(
                    "bad_arg", "command params must be an object"
                )
            if issue:
                return protocol.fail(issue.code, issue.message,
                                     "fix the command and retry")
            return protocol.ok({"stopped": self.stop()})
        with self._command_lock:
            with self._state_lock:
                self._active_generation += 1
                generation = self._active_generation
                self._active_request_id = (
                    request_id if request_id is not None else f"local-{generation}"
                )
                self._active_cancel = threading.Event()
            try:
                if params is None:
                    params = {}
                elif not isinstance(params, dict):
                    return protocol.fail(
                        "bad_arg", "command params must be an object",
                        "pass a JSON object",
                    )
                else:
                    params = copy.deepcopy(dict(params))
                for k in INTERNAL_PARAMS:
                    params.pop(k, None)
                issue = safety.preflight_command(name, params)
                if issue:
                    return protocol.fail(issue.code, issue.message,
                                         "fix the command and retry")
                preflight_error = self._preflight_dynamic(name, params)
                if preflight_error:
                    return preflight_error
                return self._dispatch_caught(name, params or {})
            except (TypeError, ValueError, RecursionError) as e:
                return protocol.fail("bad_arg", str(e), "fix the argument and retry")
            finally:
                with self._state_lock:
                    if self._active_generation == generation:
                        self._active_request_id = None
                        self._active_cancel = None

    def _dispatch_caught(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch one operation and preserve a structured failure envelope.

        Batch actions use this same path so a backend exception cannot escape
        and discard receipts already earned by earlier actions.
        """
        try:
            return self._dispatch(name, params)
        except CapabilityError as e:
            return protocol.fail("unsupported", str(e),
                                 f"'{e.capability}' is unavailable on "
                                 f"{self.backend.backend_name()}")
        except FocusError as e:
            return protocol.fail("focus_failed", str(e),
                                 "focus the target app and retry; check active-window")
        except InputCancelled as e:
            self._safe_release()
            deadline_expired = (
                not self._cancelled() and self._deadline_expired(params)
            )
            code = "deadline_exceeded" if deadline_expired else "cancelled"
            return protocol.partial(
                {
                    "operation": e.operation,
                    "completed_primitives": e.completed,
                    "total_primitives": e.total,
                },
                code,
                "batch deadline exceeded" if deadline_expired else str(e),
                "inspect partial progress before issuing a new request",
            )
        except FrameTooLarge:
            return protocol.fail("exec_failed", "frame too_large",
                                 "capture a smaller region")
        except ValueError as e:
            return protocol.fail("bad_arg", str(e), "fix the argument and retry")
        except Exception as e:  # backend failure
            if name in {
                "move", "click", "double-click", "right_click", "drag",
                "scroll", "type", "click_type", "press", "hotkey", "batch",
            }:
                self._safe_release()
            return protocol.fail("exec_failed", str(e),
                                 "grant OS permissions or check doctor output")

    def _safe_release(self) -> None:
        try:
            self.backend.release_all()
        except Exception:
            pass

    def _unknown_input_failure(self, operation: str) -> Dict[str, Any]:
        """Preserve uncertainty when a backend call may have posted input."""
        self._safe_release()
        return protocol.partial(
            {
                "executed": False,
                "last_completed": None,
                "receipts": [{"step": operation, "status": "unknown"}],
            },
            "exec_failed",
            f"{operation} failed after input dispatch began; completion is unknown",
            "inspect the target before retrying; input cannot be undone",
        )

    def _active_window_name(self) -> str:
        value = self.backend.active_window()
        if not isinstance(value, str):
            raise RuntimeError("backend returned a non-string active window")
        if len(value.encode("utf-8")) > MAX_ACTIVE_WINDOW_BYTES:
            raise RuntimeError("backend returned an oversized active window name")
        return value

    def _preflight_frames(self, name: str, params: Dict[str, Any]):
        """Authorize every coordinate action before any batch dispatch.

        This path is shared by individual commands and recursively by batch
        commands.  Dry runs intentionally do not require live frame state.
        """
        if self.dry_run:
            return None
        if name == "batch":
            actions = params.get("actions")
            if not isinstance(actions, list):
                return None  # structural preflight reports the argument error
            for index, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                error = self._preflight_frames(action.get("op"), action)
                if error:
                    error["error"]["message"] = (
                        f"action {index}: {error['error']['message']}"
                    )
                    return error
            return None
        if name in {
            "move", "click", "double-click", "right_click", "drag", "click_type"
        }:
            return self._validate_frame(params, name)
        return None

    def _preflight_dynamic(self, name: str, params: Dict[str, Any]):
        """Apply all state-dependent guards through one shared path."""
        frame_error = self._preflight_frames(name, params)
        if frame_error:
            return frame_error
        return self._preflight_input_state(name, params)

    def _preflight_input_state(self, name: str, params: Dict[str, Any]):
        """Inspect focus and UI safety metadata before any keyboard dispatch."""
        if self.dry_run:
            return None
        if name == "batch":
            batch_app = params.get("app") or params.get("_batch_app") or ""
            for index, action in enumerate(params.get("actions") or []):
                action_params = {
                    key: value for key, value in action.items() if key != "op"
                }
                if not action_params.get("app") and batch_app:
                    action_params["app"] = batch_app
                error = self._preflight_input_state(action["op"], action_params)
                if error:
                    error["error"]["message"] = (
                        f"action {index}: {error['error']['message']}"
                    )
                    return error
            return None
        if name not in {"type", "click_type", "press", "hotkey"}:
            return None
        app = (params.get("app") or params.get("_batch_app") or "").strip()
        try:
            actual = self._active_window_name()
            matcher = getattr(self.backend, "app_matches", None)
            if not (matcher(app, actual) if matcher else app.casefold() == actual.casefold()):
                return protocol.fail(
                    "focus_failed",
                    f"refusing input: expected '{app}', frontmost is '{actual}'",
                    "focus the target app and retry",
                )
            state = (
                self.backend.element_at(params["x"], params["y"])
                if name == "click_type"
                else self.backend.focused_element()
            )
        except CapabilityError:
            state = None
        except Exception as exc:
            return protocol.fail(
                "needs_attention",
                f"input safety state could not be inspected: {exc}",
                "inspect the target UI manually before retrying",
            )
        issue = safety.input_state_issue(state)
        if issue:
            return protocol.fail(
                issue.code, issue.message,
                "inspect the target UI manually before retrying",
            )
        return None

    def _dispatch(self, name: str, p: Dict[str, Any]) -> Dict[str, Any]:
        if name == "stop":
            return protocol.ok({"stopped": self.stop()})
        err = self._check_abort(p)
        if err:
            return err
        handler = {
            "observe": self._observe,
            "list_apps": self._list_apps,
            "list_windows": self._list_windows,
            "active-window": self._active_window,
            "focus_app": self._focus_app,
            "launch": self._launch,
            "move": self._move,
            "click": self._click,
            "double-click": self._double_click,
            "right_click": self._right_click,
            "drag": self._drag,
            "scroll": self._scroll,
            "type": self._type,
            "click_type": self._click_type,
            "press": self._press,
            "hotkey": self._hotkey,
            "wait": self._wait,
            "batch": self._batch,
            "doctor": self._doctor,
        }.get(name)
        if handler is None:
            return protocol.fail("bad_arg", f"unknown command: {name}",
                                 "run desktop --help for the command list")
        return handler(p)

    # -- observation --------------------------------------------------------

    def _observe(self, p: Dict[str, Any]) -> Dict[str, Any]:
        layout = self.backend.display_layout()
        try:
            validate_layout(layout)
        except ValueError as exc:
            raise RuntimeError(f"backend returned invalid display layout: {exc}") from exc
        origin = layout.get("origin")
        if not isinstance(origin, (list, tuple)) or len(origin) != 2:
            raise ValueError("backend returned an invalid display layout origin")
        layout_x, layout_y = origin
        layout_width = layout.get("width")
        layout_height = layout.get("height")
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (layout_x, layout_y, layout_width, layout_height)
        ) or layout_width <= 0 or layout_height <= 0:
            raise ValueError("backend returned invalid display layout bounds")
        region = safety.validate_region(p.get("region", ""))
        if region:
            x, y, w, h = region
        else:
            x, y, w, h = layout_x, layout_y, layout_width, layout_height
        if not (
            layout_x <= x
            and layout_y <= y
            and x + w <= layout_x + layout_width
            and y + h <= layout_y + layout_height
        ):
            return protocol.fail(
                "bad_arg",
                "capture region is outside the current display layout",
                "choose a region inside the reported layout bounds",
            )
        if self.dry_run:
            return protocol.ok(
                {"region": [x, y, w, h], "layout": layout, "dry_run": True}
            )
        delivery = (
            "path" if p.get("path_mode")
            else "metadata" if p.get("metadata_only")
            else "base64"
        )
        active_window = self._active_window_name()
        result_metadata = {
            "frame_id": "frame-00000000000000000000",
            "region": [x, y, w, h],
            "screen": {
                "width": layout_width,
                "height": layout_height,
                "origin": [layout_x, layout_y],
            },
            "layout": layout,
            "active_window": active_window,
        }
        result_metadata_bytes = len(
            json.dumps(
                {"ok": True, "data": result_metadata},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ) + 128
        self.frames.preflight_capture(
            w, h, delivery, result_metadata_bytes
        )
        raw, meta = self.backend.capture_region(x, y, w, h)
        active_window_after = self._active_window_name()
        if active_window_after != active_window:
            self.frames.clear()
            return protocol.fail(
                "stale_frame",
                "foreground application changed during screen capture",
                "observe again after focus settles",
            )
        if not isinstance(meta, dict) or meta.get("width") != w \
                or meta.get("height") != h or meta.get("pixel_format") != "rgb":
            raise RuntimeError("backend returned invalid RGB capture metadata")
        frame = self.frames.store_rgb(
            raw, w, h, layout, (x, y, w, h), delivery,
            result_metadata_bytes, active_window,
        )
        data = {
            "frame_id": frame["id"],
            "region": [x, y, w, h],
            "screen": {
                "width": layout_width,
                "height": layout_height,
                "origin": [layout_x, layout_y],
            },
            "layout": layout,
            "active_window": active_window,
        }
        if "image_b64" in frame:
            data["image_b64"] = frame["image_b64"]
        if "path" in frame:
            data["path"] = frame["path"]
        return protocol.ok(data)

    # -- read-only info -------------------------------------------------------

    def _list_apps(self, p):
        return protocol.ok({"apps": self.backend.list_apps()})

    def _list_windows(self, p):
        return protocol.ok({"windows": self.backend.list_windows(p.get("app", ""))})

    def _active_window(self, p):
        return protocol.ok({"active_window": self._active_window_name()})

    # -- focus / launch ---------------------------------------------------------

    def _focus_app(self, p):
        app = (p.get("app") or "").strip()
        if not app:
            return protocol.fail("bad_arg", "app must be a non-empty application name",
                                 "pass --app 'Application Name'")
        if self.dry_run:
            return protocol.ok({"app": app, "dry_run": True})
        active = self.backend.focus_app(app)
        return protocol.ok({"executed": True, "app": app, "active_window": active,
                            "effect_verified": self._app_is(active, app)})

    def _launch(self, p):
        app = (p.get("app") or "").strip()
        if not app:
            return protocol.fail("bad_arg", "app must be a non-empty application name",
                                 "pass --app 'Application Name'")
        if self.dry_run:
            return protocol.ok({"app": app, "dry_run": True})
        active = self.backend.launch(app)
        return protocol.ok({"executed": True, "app": app, "active_window": active,
                            "effect_verified": self._app_is(active, app)})

    def _app_is(self, actual: str, requested: str) -> bool:
        matcher = getattr(self.backend, "app_matches", None)
        if matcher:
            return bool(matcher(requested, actual))
        return requested.strip().casefold() == actual.strip().casefold()

    # -- pointer -----------------------------------------------------------------

    def _validate_frame(self, p, name="") -> Optional[Dict[str, Any]]:
        frame_id = p.get("frame_id")
        if not frame_id:
            return protocol.fail(
                "stale_frame", "coordinates require a fresh frame_id",
                "call observe first, then pass its frame_id")
        layout = self.backend.display_layout()
        try:
            validate_layout(layout)
        except ValueError as exc:
            raise RuntimeError(f"backend returned invalid display layout: {exc}") from exc
        targets = (
            [(p.get("from_x"), p.get("from_y")),
             (p.get("to_x"), p.get("to_y"))]
            if name == "drag"
            else [(p.get("x"), p.get("y"))]
        )
        frame = self.frames.get(frame_id)
        active_window = self._active_window_name()
        if (
            not frame
            or frame.get("active_window") != active_window
            or not self.frames.authorizes(frame_id, layout, targets)
        ):
            return protocol.fail(
                "stale_frame",
                f"frame {frame_id} is stale, geometry changed, or target is outside its region",
                "observe again and retry with the new frame_id")
        return None

    def _pointer_common(self, p, op):
        if not safety.validate_coordinates(p.get("x"), p.get("y")):
            return protocol.fail("bad_arg", "x/y must be integers",
                                 "pass valid coordinates")
        if self.dry_run:
            return protocol.ok({"x": p["x"], "y": p["y"], "op": op, "dry_run": True})
        err = self._check_abort(p)
        if err:
            return err
        return None

    def _click(self, p):
        return self._click_impl(p, button="left", double=False)

    def _double_click(self, p):
        return self._click_impl(p, button="left", double=True)

    def _right_click(self, p):
        return self._click_impl(p, button="right", double=False)

    def _click_impl(self, p, button, double):
        err = self._pointer_common(p, "click")
        if err:
            return err
        try:
            self._travel(p, (p["x"], p["y"]))
            self.backend.click(
                p["x"], p["y"], button=button, double=double,
                cancelled=self._cancel_probe(p),
            )
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure(
                "double-click" if double else "right_click" if button == "right" else "click"
            )
        return protocol.ok({"executed": True, "x": p["x"], "y": p["y"],
                            "button": button, "double": double})

    def _travel(self, p: Dict[str, Any], target=None) -> None:
        """Visible Bezier travel; untargeted input returns to its start."""
        start = self.backend.cursor_position()
        target = start if target is None else target
        path = points(*start, *target, seed=p.get("seed", 0))
        distance = sum(
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip([start] + path, path)
        )
        duration = timing.movement_seconds("human", 0, 0, distance, 0)
        self.backend.move_path(path, duration, cancelled=self._cancel_probe(p))
        if self._cancel_probe(p)():
            raise InputCancelled("move", len(path), len(path))

    def _move(self, p):
        if not safety.validate_coordinates(p.get("x"), p.get("y")):
            return protocol.fail("bad_arg", "x/y must be integers",
                                 "pass valid coordinates")
        if self.dry_run:
            pts = points(0, 0, p["x"], p["y"], seed=p.get("seed", 0))
            return protocol.ok({"x": p["x"], "y": p["y"], "points": len(pts),
                                "dry_run": True})
        err = self._check_abort(p)
        if err:
            return err
        try:
            self._travel(p, (p["x"], p["y"]))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure("move")
        return protocol.ok({"executed": True, "x": p["x"], "y": p["y"]})

    def _drag(self, p):
        for k in ("from_x", "from_y", "to_x", "to_y"):
            if not safety.validate_coordinates(p.get(k), 0):
                return protocol.fail("bad_arg", f"{k} must be nonnegative",
                                     "pass valid drag coordinates")
        if self.dry_run:
            return protocol.ok({"op": "drag", "dry_run": True})
        err = self._check_abort(p)
        if err:
            return err
        frm = (p["from_x"], p["from_y"])
        to = (p["to_x"], p["to_y"])
        path = points(frm[0], frm[1], to[0], to[1], seed=p.get("seed", 0))
        try:
            self._travel(p, frm)
            self.backend.drag(frm, to, path, cancelled=self._cancel_probe(p))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure("drag")
        return protocol.ok({"executed": True})

    def _scroll(self, p):
        direction = p.get("direction", "down")
        amount = p.get("amount", 3)
        if direction not in ("up", "down", "left", "right"):
            return protocol.fail("bad_arg", "direction must be up/down/left/right",
                                 "pick one of the four directions")
        if not isinstance(amount, int) or not 1 <= amount <= 100:
            return protocol.fail("bad_arg", "amount must be 1-100", "pass a tick count")
        if self.dry_run:
            return protocol.ok({"op": "scroll", "direction": direction,
                                "amount": amount, "dry_run": True})
        err = self._check_abort(p)
        if err:
            return err
        try:
            self._travel(p)
            self.backend.scroll(direction, amount, cancelled=self._cancel_probe(p))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure("scroll")
        return protocol.ok({"executed": True, "direction": direction,
                            "amount": amount})

    # -- keyboard -------------------------------------------------------------------

    def _keyboard_guard(self, p, app_required=True, inspect_element=True):
        """Mandatory pre-input checks. Returns error envelope or None.

        Focus is ALWAYS verified: against the explicit app, or — inside a
        batch or when app_required is waived — against the current
        frontmost app (which must exist; typing into nothing is refused).
        """
        err = self._check_abort(p)
        if err:
            return err, None
        app = (p.get("app") or "").strip()
        # batch-level app context: set only by _batch(), overriding any
        # caller-supplied _batch_app (internal params are not trusted input)
        if not app and p.get("_in_batch") and p.get("_batch_app"):
            app = str(p["_batch_app"]).strip()
        if app_required and not app:
            return (
                protocol.fail(
                    "focus_required",
                    "--app is required before keyboard input",
                    "pass --app 'Application Name'",
                ),
                None,
            )
        if app:
            actual = self._active_window_name()
            matcher = getattr(self.backend, "app_matches", None)
            if not (matcher(app, actual) if matcher else app.casefold() == actual.casefold()):
                raise FocusError(
                    f"refusing input: expected '{app}', frontmost is '{actual}'")
        if inspect_element:
            try:
                state = self.backend.focused_element()
            except CapabilityError:
                state = None
            except Exception as exc:
                return (
                    protocol.fail(
                        "needs_attention",
                        f"input safety state could not be inspected: {exc}",
                        "inspect the target UI manually before retrying",
                    ),
                    None,
                )
            issue = safety.input_state_issue(state)
            if issue:
                return (
                    protocol.fail(
                        issue.code,
                        issue.message,
                        "inspect the target UI manually before retrying",
                    ),
                    state,
                )
            return None, state
        return None, None

    def _effect_check(
        self, p: Dict[str, Any], operation: str,
        text: str = "", before_state: Any = None,
    ) -> Dict[str, Any]:
        """Post-input effect verification. 'effect': read focused element value
        if the OS exposes it and report honestly; 'focus': re-check foreground.
        Never fails the command — dispatch already happened; we only report."""
        out: Dict[str, Any] = {}
        mode = p.get("verify")
        if mode:
            out["effect_verified"] = None
        if mode == "focus":
            # re-check foreground app still matches after the event
            app = (p.get("app") or "").strip() or str(p.get("_batch_app") or "").strip()
            if app:
                try:
                    actual = self._active_window_name()
                    matcher = getattr(self.backend, "app_matches", None)
                    out["effect_verified"] = (
                        matcher(app, actual)
                        if matcher else app.strip().casefold() == actual.strip().casefold()
                    )
                except Exception:
                    pass
        elif mode == "effect" and operation in {"type", "click_type"}:
            before = (
                before_state.get("value")
                if isinstance(before_state, dict) else None
            )
            try:
                state = self.backend.focused_element()
                value = state.get("value") if isinstance(state, dict) else None
                if isinstance(before, str) and isinstance(value, str):
                    out["effect_verified"] = _proves_text_insertion(
                        before, value, text
                    )
            except Exception:
                pass
        return out

    def _unknown_typing_failure(
        self,
        requested: int,
        *,
        clicked: bool = False,
    ) -> Dict[str, Any]:
        """Report conservatively once a backend typing call has begun.

        A backend exception or invalid completion count cannot prove how many
        characters reached the OS. Never erase an already-completed click and
        never include the text payload in the error envelope.
        """
        receipts = []
        if clicked:
            receipts.append({"step": "click", "status": "ok"})
        receipts.append({"step": "type", "status": "unknown"})
        data: Dict[str, Any] = {
            "executed": False,
            "typed": False,
            "chars": None,
            "requested_chars": requested,
            "last_completed": "click" if clicked else None,
            "receipts": receipts,
        }
        if clicked:
            data["clicked"] = True
        self._safe_release()
        return protocol.partial(
            data,
            "exec_failed",
            "typing failed after input dispatch began; completion is unknown",
            "inspect the target before retrying; typed input cannot be undone",
        )

    def _type(self, p):
        try:
            text = safety.validate_text(p.get("text", ""))
        except ValueError as e:
            return protocol.fail("bad_arg", str(e), "pass non-empty text")
        if safety.looks_like_challenge(text):
            return protocol.fail("needs_attention",
                                 "text mentions password/permission/payment/challenge UI",
                                 "stop and ask the user; never auto-fill secrets")
        if self.dry_run:
            return protocol.ok({"typed": len(text), "dry_run": True})
        if safety.needs_confirmation(text) and not p.get("confirm"):
            return protocol.fail(
                "needs_attention",
                "text looks like a consequential action (send/publish/delete/"
                "purchase); fresh user confirmation required",
                "ask the user, then resend with confirm: true")
        err, before_state = self._keyboard_guard(p)
        if err:
            return err
        try:
            self._travel(p)
            err, before_state = self._keyboard_guard(p)
            if err:
                return err
            n = _validated_typed_count(self.backend.type_text(
                text,
                iter(timing.gaps_for(p.get("timing", "native"), text)),
                cancelled=self._cancel_probe(p),
            ), len(text))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_typing_failure(len(text))
        if n != len(text):
            return protocol.partial(
                {
                    "executed": False,
                    "chars": n,
                    "requested_chars": len(text),
                    "last_completed": n - 1,
                    "receipts": [{
                        "step": "type",
                        "status": "partial",
                        "completed_chars": n,
                    }],
                },
                "exec_failed",
                f"backend typed {n} of {len(text)} characters",
                "inspect the target before retrying; typed input cannot be undone",
            )
        result = protocol.ok({"executed": True, "chars": n})
        result["data"].update(
            self._effect_check(p, "type", text, before_state)
        )
        return result

    def _click_type(self, p):
        try:
            text = safety.validate_text(p.get("text", ""))
        except ValueError as e:
            return protocol.fail("bad_arg", str(e), "pass non-empty text")
        if safety.looks_like_challenge(text):
            return protocol.fail("needs_attention", "challenge text", "stop and ask the user")
        if not safety.validate_coordinates(p.get("x"), p.get("y")):
            return protocol.fail("bad_arg", "x/y must be nonnegative integers",
                                 "pass valid coordinates")
        if self.dry_run:
            return protocol.ok({"typed": len(text), "x": p["x"], "y": p["y"],
                                "app": p.get("app"), "dry_run": True})
        if safety.needs_confirmation(text) and not p.get("confirm"):
            return protocol.fail(
                "needs_attention",
                "text looks like a consequential action (send/publish/delete/"
                "purchase); fresh user confirmation required",
                "ask the user, then resend with confirm: true")
        err, _ = self._keyboard_guard(p, inspect_element=False)
        if err:
            return err
        try:
            self._travel(p, (p["x"], p["y"]))
            self.backend.click(p["x"], p["y"], cancelled=self._cancel_probe(p))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure("click")
        err, before_state = self._keyboard_guard(p)
        if err:
            return protocol.partial(
                {
                    "executed": False,
                    "clicked": True,
                    "typed": False,
                    "last_completed": "click",
                    "receipts": [{"step": "click", "status": "ok"}],
                },
                err["error"]["code"],
                err["error"]["message"],
                err["error"].get("recover", ""),
            )
        try:
            n = _validated_typed_count(self.backend.type_text(
                text,
                iter(timing.gaps_for(p.get("timing", "native"), text)),
                cancelled=self._cancel_probe(p),
            ), len(text))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_typing_failure(len(text), clicked=True)
        if n != len(text):
            return protocol.partial(
                {
                    "executed": False,
                    "clicked": True,
                    "typed": False,
                    "chars": n,
                    "requested_chars": len(text),
                    "last_completed": "click",
                    "receipts": [
                        {"step": "click", "status": "ok"},
                        {
                            "step": "type",
                            "status": "partial",
                            "completed_chars": n,
                        },
                    ],
                },
                "exec_failed",
                f"backend typed {n} of {len(text)} characters after clicking",
                "inspect the target before retrying; executed input cannot be undone",
            )
        result = protocol.ok({"executed": True, "chars": n})
        result["data"].update(
            self._effect_check(p, "click_type", text, before_state)
        )
        return result

    def _press(self, p):
        keys = p.get("keys", "")
        return self._keys_impl(p, keys, press=True)

    def _hotkey(self, p):
        keys = p.get("keys", "")
        return self._keys_impl(p, keys, press=False)

    def _keys_impl(self, p, keys, press):
        keys = ",".join(safety.key_parts(keys))
        if safety.is_blocked_keys(keys):
            return protocol.fail("blocked", "key combo blocked for safety",
                                 "use a safe key combination")
        try:
            safety.validate_keys(keys)
        except ValueError as e:
            return protocol.fail("bad_arg", str(e), "use known key names")
        if self.dry_run:
            return protocol.ok({"keys": keys, "dry_run": True})
        err, _ = self._keyboard_guard(p)
        if err:
            return err
        try:
            if press:
                self._travel(p)
                err, _ = self._keyboard_guard(p)
                if err:
                    return err
                self.backend.press(keys, cancelled=self._cancel_probe(p))
            else:
                self._travel(p)
                err, _ = self._keyboard_guard(p)
                if err:
                    return err
                self.backend.hotkey(keys, cancelled=self._cancel_probe(p))
        except (CapabilityError, InputCancelled):
            raise
        except Exception:
            return self._unknown_input_failure("press" if press else "hotkey")
        result = protocol.ok({"executed": True, "keys": keys})
        if p.get("verify"):
            result["data"].update(
                self._effect_check(p, "press" if press else "hotkey")
            )
        return result

    def _wait(self, p):
        s = p.get("seconds", 1.0)
        if not isinstance(s, (int, float)) or s < 0 or s > MAX_WAIT_SECONDS:
            return protocol.fail("bad_arg", f"seconds must be 0-{MAX_WAIT_SECONDS}",
                                 "pass a bounded wait")
        if self.dry_run:
            return protocol.ok({"seconds": s, "dry_run": True})
        err = self._check_abort(p)
        if err:
            return err
        deadline = time.monotonic() + s
        while time.monotonic() < deadline:
            err = self._check_abort(p)
            if err:
                return err
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        return protocol.ok({"executed": True, "seconds": s})

    # -- batch ------------------------------------------------------------------------

    def _batch(self, p):
        actions = p.get("actions") or []
        deadline_ms = p.get("deadline_ms")
        parent_deadline = p.get("_deadline")
        deadline = parent_deadline if isinstance(parent_deadline, (int, float)) else None
        MAX_DEADLINE_MS = 600_000  # 10 minutes; batches are short by contract
        if deadline_ms is not None:
            if not isinstance(deadline_ms, (int, float)) or deadline_ms <= 0 \
                    or deadline_ms > MAX_DEADLINE_MS:
                return protocol.fail(
                    "bad_arg", f"deadline_ms must be 0-{MAX_DEADLINE_MS}",
                    "pass a bounded deadline")
            own_deadline = time.monotonic() + deadline_ms / 1000.0
            deadline = min(deadline, own_deadline) if deadline is not None else own_deadline
        # batch-level app context (trusted: came through command()'s strip)
        batch_app = (p.get("app") or p.get("_batch_app") or "").strip()
        receipts = []
        last_completed = -1
        status = "completed"
        failure_code = "exec_failed"
        for i, action in enumerate(actions):
            if deadline is not None and time.monotonic() > deadline:
                status = "deadline_exceeded"
                failure_code = "deadline_exceeded"
                break
            err = self._check_abort(p)
            if err:
                failure_code = err["error"]["code"]
                status = failure_code
                break
            action_params = {
                key: value for key, value in _strip_internal(action).items()
                if key != "op"
            }
            runtime_params = {
                **action_params, "_in_batch": True,
                **({"_batch_app": batch_app} if batch_app else {}),
                **({"_deadline": deadline} if deadline is not None else {}),
            }
            sub = self._preflight_dynamic(action["op"], runtime_params)
            if sub is None:
                sub = self._dispatch_caught(action["op"], runtime_params)
            if sub["ok"]:
                receipts.append({"index": i, "status": "ok",
                                 "data": sub["data"]})
                last_completed = i
            else:
                code = sub["error"]["code"]
                receipt = {"index": i, "status": "failed",
                           "error": sub["error"]}
                if "data" in sub:
                    receipt["data"] = sub["data"]
                receipts.append(receipt)
                failure_code = code
                status = code if code in {"cancelled", "deadline_exceeded"} else "failed"
                break
        # never claim rollback; report honestly. A requested terminal
        # observation runs after the action loop and any failure cleanup.
        data = {
            "status": status,
            "last_completed": last_completed,
            "receipts": receipts,
        }
        if status == "completed":
            result = protocol.ok(data)
        else:
            result = protocol.partial(
                data,
                failure_code,
                f"batch {status} at action {last_completed + 1}",
                "inspect receipts; executed events cannot be undone")
        final_request = p.get("final_observe")
        if isinstance(final_request, dict):
            wants_image = final_request.get("image", False)
            observation_params = {} if wants_image else {"metadata_only": True}
            try:
                observed = self._observe(observation_params)
                if observed.get("ok"):
                    observation_data = dict(observed.get("data") or {})
                    image_b64 = observation_data.pop("image_b64", None)
                    data["final_observation"] = {
                        "ok": True,
                        "data": observation_data,
                    }
                    if isinstance(image_b64, str):
                        data["image_b64"] = image_b64
                else:
                    data["final_observation"] = {
                        "ok": False,
                        "error": observed.get("error", {
                            "code": "exec_failed",
                            "message": "final observation failed",
                        }),
                    }
            except Exception as exc:
                data["final_observation"] = {
                    "ok": False,
                    "error": {
                        "code": "exec_failed",
                        "message": str(exc),
                        "recover": "inspect the target and retry observation",
                    },
                }
        return result

    # -- doctor -------------------------------------------------------------------------

    def _doctor(self, p):
        b = self.backend
        checks = {}

        def probe(name, check, recover):
            try:
                available = bool(check())
                message = "available" if available else "missing or not authorized"
            except CapabilityError as exc:
                available = None
                message = str(exc)[:200]
                if exc.capability == "helper" and name != "helper":
                    message = f"not checked because the native helper is missing: {message}"
                    recover = (
                        "restore the native helper with ./install, then " + recover
                    )
            except Exception as exc:
                available = None
                message = str(exc)[:200]
            checks[name] = {
                "ok": available,
                "message": message,
                "recover": recover,
            }

        probe(
            "helper",
            b.helper_available,
            "reinstall the package or build native/cghelper.c with ./install",
        )
        probe(
            "accessibility",
            b.trusted,
            "grant Accessibility permission to the installed controller, then retry",
        )
        probe(
            "screen_recording",
            b.screen_recording_authorized,
            "grant Screen Recording permission to the installed controller, then retry",
        )
        try:
            import mss  # noqa: F401
            mss_available = True
        except ImportError:
            mss_available = False
        checks["mss"] = {
            "ok": mss_available,
            "message": "available" if mss_available else "Python package is missing",
            "recover": "install the project dependencies with ./install",
        }
        return protocol.ok({
            "platform": b.backend_name(),
            "version": __version__,
            "ready": all(check["ok"] is True for check in checks.values()),
            "checks": checks,
        })
