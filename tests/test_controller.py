"""Controller tests. Public seam: Controller.command(name, params) -> envelope.

Uses a FakeBackend that records every OS event so tests prove:
- focus mismatch sends zero input events
- stale frame sends zero coordinate events
- cancellation stops before the next primitive with last_completed
- held keys/buttons are released on failure
- stop is honored out-of-band
"""

import pytest

from desktop.controller import Controller
from desktop.platforms.base import CapabilityError, FocusError


class FakeBackend:
    """Records all posted events. Simulates focus and frame state."""

    def __init__(self):
        self.events = []
        self.frontmost = "Finder"
        self.screen = {"width": 1440, "height": 900}
        self.focused_element_state = {"role": "AXTextField"}
        self._held_keys = 0
        self._button_down = False
        self._trusted = True

    # -- observation ---------------------------------------------------
    def screen_size(self):
        return dict(self.screen)

    def display_layout(self):
        left = self.screen.get("left", 0)
        top = self.screen.get("top", 0)
        return {
            "origin": [left, top],
            "width": self.screen["width"],
            "height": self.screen["height"],
            "displays": [
                {
                    "id": "fake-display",
                    "origin": [left, top],
                    "width": self.screen["width"],
                    "height": self.screen["height"],
                    "scale": [1.0, 1.0],
                    "rotation": 0.0,
                }
            ],
        }

    def active_window(self):
        return self.frontmost

    def focused_element(self):
        return self.focused_element_state or None

    def element_at(self, x, y):
        return self.focused_element_state or None

    def cursor_position(self):
        return (0, 0)

    def backend_name(self):
        return "fake"

    def helper_available(self):
        return True

    def trusted(self):
        return self._trusted

    def screen_recording_authorized(self):
        return True

    def list_apps(self):
        raise CapabilityError("list_apps", "not supported by this backend")

    def list_windows(self, app=""):
        raise CapabilityError("list_windows", "not supported by this backend")

    def capture_region(self, x, y, w, h):
        self.events.append(("capture", x, y, w, h))
        return b"\0" * (w * h * 3), {
            "width": w,
            "height": h,
            "pixel_format": "rgb",
        }

    # -- input ---------------------------------------------------------
    def move_path(self, points, total_secs, cancelled=None):
        self.events.append(("move", points[-1], total_secs))

    def click(self, x, y, button="left", double=False, cancelled=None):
        if self._button_down:
            self.release_all()
        self.events.append(("click", x, y, button, double))

    def drag(self, frm, to, path, cancelled=None):
        self.events.append(("drag", frm, to, len(path)))

    def scroll(self, direction, amount, cancelled=None):
        self.events.append(("scroll", direction, amount))

    def type_text(self, text, gaps, cancelled=None):
        self._held_keys += 1
        self.events.append(("type", text))
        self._held_keys -= 1
        return len(text)

    def hotkey(self, keys, cancelled=None):
        self.events.append(("hotkey", keys))

    def press(self, key, cancelled=None):
        self.events.append(("press", key))

    def launch(self, app):
        self.frontmost = app
        self.events.append(("launch", app))
        return app

    def focus_app(self, app, timeout=5.0):
        return self.frontmost

    def release_all(self):
        # cleanup, not input: only posts when something was actually held
        if self._button_down or self._held_keys:
            self._button_down = False
            self._held_keys = 0
            self.events.append(("release_all",))


@pytest.fixture
def ctl():
    backend = FakeBackend()
    c = Controller(backend=backend, dry_run=False)
    c._backend_for_tests = backend
    return c


# -- focus verification ---------------------------------------------------

def test_type_without_matching_focus_sends_no_events(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    r = ctl.command("type", {"text": "hi", "app": "Chrome", "risk": "none"})
    assert r["ok"] is False
    assert r["error"]["code"] == "focus_failed"
    assert b.events == []  # zero input events


def test_type_with_matching_focus_types(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Chrome"
    r = ctl.command("type", {"text": "hi", "app": "Chrome", "risk": "none"})
    assert r["ok"] is True
    assert ("type", "hi") in b.events


def test_keyboard_input_requires_app(ctl):
    r = ctl.command("type", {"text": "hi"})
    assert r["ok"] is False
    assert r["error"]["code"] == "focus_required"


# -- frame freshness ------------------------------------------------------

def test_click_requires_fresh_frame_and_matching_geometry(ctl):
    b = ctl._backend_for_tests
    r = ctl.command("click", {"x": 10, "y": 20, "frame_id": "frame-999",
                              "risk": "none"})
    assert r["ok"] is False
    assert r["error"]["code"] == "stale_frame"
    assert b.events == []


def test_click_with_fresh_frame_clicks(ctl):
    b = ctl._backend_for_tests
    obs = ctl.command("observe", {})
    fid = obs["data"]["frame_id"]
    r = ctl.command("click", {"x": 10, "y": 20, "frame_id": fid,
                              "risk": "none"})
    assert r["ok"] is True
    assert ("click", 10, 20, "left", False) in b.events


def test_geometry_change_invalidates_frame(ctl):
    obs = ctl.command("observe", {})
    fid = obs["data"]["frame_id"]
    ctl._backend_for_tests.screen = {"width": 100, "height": 100}
    r = ctl.command("click", {"x": 10, "y": 20, "frame_id": fid,
                              "risk": "none"})
    assert r["ok"] is False
    assert r["error"]["code"] == "stale_frame"


def test_observe_without_pixels_returns_metadata_only(ctl):
    r = ctl.command("observe", {"metadata_only": True})
    assert r["ok"] is True
    assert "frame_id" in r["data"]
    assert r["data"].get("image_b64") is None


# -- cancellation and stop ------------------------------------------------

def test_idle_stop_does_not_cancel_next_action(ctl):
    stopped = ctl.command("stop", {})
    r = ctl.command("type", {"text": "hi", "app": "Finder", "risk": "none"})
    assert stopped["data"]["stopped"] is False
    assert r["ok"] is True
    assert [e for e in ctl._backend_for_tests.events if e[0] != "move"] == [("type", "hi")]


def test_batch_reports_last_completed_on_cancellation(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"

    def cancel_after_two():
        if sum(e[0] == "type" for e in b.events) >= 2:
            ctl.request_cancel()

    orig_type = b.type_text

    def type_and_cancel(text, gaps, cancelled=None):
        orig_type(text, gaps, cancelled=cancelled)
        cancel_after_two()
        return len(text)

    b.type_text = type_and_cancel
    r = ctl.command("batch", {
        "app": "Finder",
        "risk": "none",
        "actions": [
            {"op": "type", "text": "one"},
            {"op": "type", "text": "two"},
            {"op": "type", "text": "three"},
        ]
    })
    assert r["ok"] is False
    assert r["data"]["last_completed"] == 1
    assert r["data"]["status"] == "cancelled"


# -- batch receipts -------------------------------------------------------

def test_batch_fifo_receipts(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    r = ctl.command("batch", {
        "app": "Finder",
        "risk": "none",
        "actions": [
            {"op": "type", "text": "a"},
            {"op": "press", "keys": "return"},
        ]
    })
    assert r["ok"] is True
    assert r["data"]["status"] == "completed"
    assert r["data"]["last_completed"] == 1
    assert len(r["data"]["receipts"]) == 2


def test_batch_invalid_before_first_action(ctl):
    r = ctl.command("batch", {"actions": [{"op": "bogus"}]})
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"
    assert ctl._backend_for_tests.events == []


def test_batch_releases_held_keys_on_failure(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"

    def boom(text, gaps, cancelled=None):
        b._held_keys = 1  # simulates key held mid-delivery
        raise RuntimeError("backend died")

    b.type_text = boom
    r = ctl.command("batch", {"app": "Finder", "risk": "none",
                               "actions": [{"op": "type", "text": "a"}]})
    assert r["ok"] is False
    assert ("release_all",) in b.events


# -- unsupported capabilities ---------------------------------------------

def test_unsupported_capability_is_structured_error(ctl):
    r = ctl.command("list_apps", {})
    assert r["ok"] is False
    assert r["error"]["code"] == "unsupported"


# -- validation -----------------------------------------------------------

def test_bad_coordinates_rejected(ctl):
    r = ctl.command("click", {"x": -5, "y": 20})
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"


def test_unknown_command(ctl):
    r = ctl.command("nope", {})
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"


def test_dry_run_default_has_no_events(ctl):
    backend = FakeBackend()
    c = Controller(backend=backend)  # dry_run defaults True
    r = c.command("click", {"x": 5, "y": 6, "risk": "none"})
    assert r["ok"] is True
    assert r["data"]["dry_run"] is True
    assert backend.events == []


def test_launch_verifies_foreground(ctl):
    r = ctl.command("launch", {"app": "Chrome"})
    assert r["ok"] is True
    assert r["data"]["active_window"] == "Chrome"


def test_wait_bounds(ctl):
    r = ctl.command("wait", {"seconds": 0.01})
    assert r["ok"] is True
    r = ctl.command("wait", {"seconds": 999})
    assert r["ok"] is False


def test_challenge_text_needs_attention(ctl):
    r = ctl.command("type", {"text": "enter your password", "app": "Finder"})
    assert r["ok"] is False
    assert r["error"]["code"] == "needs_attention"
    assert ctl._backend_for_tests.events == []
