"""Request-scoped cancellation through the public controller seam."""

import threading
import time

from desktop.controller import Controller
from desktop.platforms.base import InputCancelled
from tests.test_controller import FakeBackend


def run_in_thread(controller, command, params, request_id):
    output = {}

    def target():
        output["result"] = controller.command(
            command, params, request_id=request_id
        )

    thread = threading.Thread(target=target)
    thread.start()
    return thread, output


def test_idle_or_unmatched_cancellation_does_not_poison_next_command():
    controller = Controller(FakeBackend(), dry_run=False)

    assert controller.request_cancel("missing-request") is False
    result = controller.command("wait", {"seconds": 0}, request_id="next")

    assert result["ok"] is True


def test_matching_request_cancels_200ms_wait_before_completion():
    controller = Controller(FakeBackend(), dry_run=False)
    started = time.monotonic()
    thread, output = run_in_thread(
        controller, "wait", {"seconds": 0.2}, request_id="wait-1"
    )
    time.sleep(0.03)

    assert controller.request_cancel("other-request") is False
    assert controller.request_cancel("wait-1") is True
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert output["result"]["error"]["code"] == "cancelled"
    assert time.monotonic() - started < 0.18


def test_cancellation_during_typing_stops_between_characters():
    backend = FakeBackend()
    controller = Controller(backend, dry_run=False)

    def slow_type(text, gaps, cancelled=None):
        completed = 0
        for character in text:
            if cancelled and cancelled():
                raise InputCancelled("type", completed, len(text))
            backend.events.append(("type-character", character))
            completed += 1
            time.sleep(0.02)
        return completed

    backend.type_text = slow_type
    thread, output = run_in_thread(
        controller,
        "type",
        {"text": "abcdefghij", "app": "Finder", "risk": "none"},
        request_id="type-1",
    )
    while len(backend.events) < 2:
        time.sleep(0.002)
    assert controller.request_cancel("type-1") is True
    thread.join(timeout=1)

    result = output["result"]
    assert result["error"]["code"] == "cancelled"
    assert 1 <= result["data"]["completed_primitives"] < 10
    assert len(backend.events) < 10


def test_cancellation_during_move_stops_between_points_and_releases_input():
    backend = FakeBackend()
    controller = Controller(backend, dry_run=False)
    observed = controller.command("observe", {"metadata_only": True})
    backend.events.clear()

    def slow_move(path, total_secs, cancelled=None):
        completed = 0
        for point in path:
            if cancelled and cancelled():
                backend._button_down = True
                raise InputCancelled("move", completed, len(path))
            backend.events.append(("move-point", point))
            completed += 1
            time.sleep(0.005)

    backend.move_path = slow_move
    thread, output = run_in_thread(
        controller,
        "move",
        {
            "x": 500,
            "y": 400,
            "frame_id": observed["data"]["frame_id"],
            "timing": "human",
            "risk": "none",
        },
        request_id="move-1",
    )
    while len(backend.events) < 2:
        time.sleep(0.002)
    assert controller.request_cancel("move-1") is True
    thread.join(timeout=1)

    result = output["result"]
    assert result["error"]["code"] == "cancelled"
    assert result["data"]["completed_primitives"] < result["data"]["total_primitives"]
    assert backend.events[-1] == ("release_all",)


def test_cancellation_during_scroll_stops_between_ticks():
    backend = FakeBackend()
    controller = Controller(backend, dry_run=False)

    def slow_scroll(direction, amount, cancelled=None):
        for completed in range(amount):
            if cancelled and cancelled():
                raise InputCancelled("scroll", completed, amount)
            backend.events.append(("scroll-tick", direction))
            time.sleep(0.015)

    backend.scroll = slow_scroll
    thread, output = run_in_thread(
        controller,
        "scroll",
        {"direction": "down", "amount": 10, "risk": "none"},
        request_id="scroll-1",
    )
    while len(backend.events) < 2:
        time.sleep(0.002)
    assert controller.request_cancel("scroll-1") is True
    thread.join(timeout=1)

    result = output["result"]
    assert result["error"]["code"] == "cancelled"
    assert result["data"]["completed_primitives"] < 10
    assert len(backend.events) < 10
