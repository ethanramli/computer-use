import random

import pytest

from desktop.platforms import macos
from desktop.platforms.base import InputCancelled


def test_replay_order_and_count():
    seen = []
    macos.replay([(10, 20), (30, 40), (50, 60)], 0.5, post=seen.append)
    assert seen == [("move", 10, 20), ("move", 30, 40), ("move", 50, 60)]


def test_active_window_uses_focused_application_not_top_overlay(monkeypatch):
    class Result:
        returncode = 0
        stdout = "Google Chrome\n"

    monkeypatch.setattr(macos.subprocess, "run", lambda *args, **kwargs: Result())
    monkeypatch.setattr(
        macos, "_run", lambda *_args, **_kwargs: pytest.fail("fallback must not run")
    )

    assert macos.active_window() == "Google Chrome"


def test_click_shapes():
    seen = []
    macos.click(1, 2, post=seen.append)
    macos.click(3, 4, button="right", post=seen.append)
    macos.click(5, 6, double=True, post=seen.append)
    assert seen[0] == ("click", 1, 2, "left", False)
    assert seen[1] == ("click", 3, 4, "right", False)
    assert seen[2] == ("click", 5, 6, "left", True)


def test_hotkey_flags():
    seen = []
    macos.hotkey("cmd,s", post=seen.append)
    assert seen == [("hotkey", 1, macos.FLAG_CMD)]


def test_hotkey_unknown_key():
    try:
        macos.hotkey("cmd,f13-nope", post=lambda *a: None)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_launch_routed():
    seen = []
    macos.launch("  Any Installed App  ", post=seen.append)
    assert seen == [("launch", "Any Installed App")]


def test_launch_uses_safe_generic_activation_and_verifies_foreground(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    active = iter([
        "Finder", "Visual Studio Code",
        "Finder", "Visual Studio Code", "Google Chrome",
        "Finder", "Preview",
    ])
    monkeypatch.setattr(macos, "active_window", lambda: next(active))
    monkeypatch.setattr(macos.time, "sleep", lambda _seconds: None)
    macos.launch("Visual Studio Code")
    macos.launch("/Applications/Google Chrome.app")
    macos.launch("Preview")
    assert [call[0][-1] for call in calls] == [
        "Visual Studio Code",
        "/Applications/Google Chrome.app",
        "Preview",
    ]
    assert all(call[0][:5] == [
        "/usr/bin/osascript", "-l", "JavaScript", "-e",
        "function run(argv) { Application(argv[0]).activate(); }",
    ] for call in calls)


def test_focus_app_falls_back_to_open_if_activation_cannot_resolve(monkeypatch):
    calls = []

    class Result:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    results = iter([Result(1, "not running"), Result(), Result()])

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(results)

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    active = iter(["Finder", "Notes"])
    monkeypatch.setattr(macos, "active_window", lambda: next(active))

    assert macos.focus_app("Notes") == "Notes"
    assert calls[1] == ["open", "-a", "Notes"]


def test_focus_app_does_not_reactivate_already_frontmost_app(monkeypatch):
    monkeypatch.setattr(macos, "active_window", lambda: "Google Chrome")
    monkeypatch.setattr(
        macos, "_open_app", lambda _app: pytest.fail("must preserve the focused control")
    )

    assert macos.focus_app("Google Chrome") == "Google Chrome"


def test_launch_rejects_empty_app():
    try:
        macos.launch("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_type_gaps_bounded():
    rng = random.Random(0)
    seen = []

    def gaps():
        from desktop import timing

        while True:
            yield timing.next_type_gap(rng)

    n = macos.type_text("hi", gaps(), post=seen.append)
    assert n == 2
    assert all(0.0 <= g <= 0.4 for _, _, g in seen)


def test_type_post_hook_cancels_between_complete_characters():
    seen = []

    with pytest.raises(InputCancelled) as error:
        macos.type_text(
            "abcd",
            iter([0.0] * 4),
            post=seen.append,
            cancelled=lambda: len(seen) >= 2,
        )

    assert seen == [("type", "a", 0.0), ("type", "b", 0.0)]
    assert error.value.completed == 2
    assert error.value.total == 4


def test_replay_post_hook_cancels_between_points():
    seen = []
    path = [(1, 1), (2, 2), (3, 3), (4, 4)]

    with pytest.raises(InputCancelled) as error:
        macos.replay(
            path,
            0.2,
            post=seen.append,
            cancelled=lambda: len(seen) >= 2,
        )

    assert seen == [("move", 1, 1), ("move", 2, 2)]
    assert error.value.completed == 2
    assert error.value.total == 4


def test_scroll_post_hook_cancels_between_ticks():
    seen = []

    with pytest.raises(InputCancelled) as error:
        macos.scroll(
            "down",
            5,
            post=seen.append,
            cancelled=lambda: len(seen) >= 2,
        )

    assert len(seen) == 2
    assert error.value.completed == 2
    assert error.value.total == 5


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("down", ["scroll", "-3", "0", "2"]),
        ("up", ["scroll", "3", "0", "2"]),
        ("left", ["scroll", "0", "3", "2"]),
        ("right", ["scroll", "0", "-3", "2"]),
    ],
)
def test_native_scroll_uses_the_requested_wheel_axis(monkeypatch, direction, expected):
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return "2"

    monkeypatch.setattr(macos, "_run", fake_run)

    macos.scroll(direction, 2)

    assert calls == [expected]


def test_focus_app_waits_until_requested_app_is_frontmost(monkeypatch):
    active = iter(["Visual Studio Code", "Google Chrome"])
    launched = []

    monkeypatch.setattr(macos, "active_window", lambda: next(active))
    monkeypatch.setattr(macos, "_open_app", launched.append)
    monkeypatch.setattr(macos.time, "sleep", lambda _seconds: None)

    assert macos.focus_app("Google Chrome", timeout=0.5) == "Google Chrome"
    assert launched == ["Google Chrome"]
