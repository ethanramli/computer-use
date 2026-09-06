"""Every public input route must visibly travel before posting input."""

import pytest

from desktop.controller import Controller
from tests.test_controller import FakeBackend


class MotionBackend(FakeBackend):
    def cursor_position(self):
        return (300, 300)

    def move_path(self, points, total_secs, cancelled=None):
        assert len(set(points)) > 1
        assert total_secs > 0
        super().move_path(points, total_secs, cancelled)


@pytest.mark.parametrize("command,params,event", [
    ("type", {"text": "hello"}, "type"),
    ("press", {"keys": "enter"}, "press"),
    ("hotkey", {"keys": "cmd,t"}, "hotkey"),
    ("scroll", {}, "scroll"),
    ("click_type", {"x": 300, "y": 300, "text": "hello"}, "click"),
    ("drag", {"from_x": 100, "from_y": 100, "to_x": 200, "to_y": 200}, "drag"),
    ("move", {"x": 500, "y": 500, "timing": "native"}, "move"),
])
def test_input_always_travels(command, params, event):
    backend = MotionBackend()
    with_controller = Controller(backend, dry_run=False)
    try:
        frame = with_controller.command("observe", {"metadata_only": True})
        backend.events.clear()
        arguments = {**params, "risk": "none"}
        if command in {"type", "press", "hotkey", "click_type"}:
            arguments["app"] = "Finder"
        if command in {"move", "drag", "click_type"}:
            arguments["frame_id"] = frame["data"]["frame_id"]
        result = with_controller.command(command, arguments)
        assert result["ok"], result
        events = [entry[0] for entry in backend.events]
        assert events[0] == "move"
        if event != "move":
            assert events.index(event) > 0
    finally:
        with_controller.close()
