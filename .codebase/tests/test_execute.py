import random

from desktop.platforms import macos


def test_replay_order_and_count():
    seen = []
    macos.replay([(10, 20), (30, 40), (50, 60)], 0.5, post=seen.append)
    assert seen == [("move", 10, 20), ("move", 30, 40), ("move", 50, 60)]


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


def test_launch_uses_os_resolver_for_any_app(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    macos.launch("Visual Studio Code")
    macos.launch("/Applications/Notes.app")
    assert [call[0] for call in calls] == [
        ["open", "-a", "Visual Studio Code"],
        ["open", "-a", "/Applications/Notes.app"],
    ]


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
        from desktop import input as inp

        while True:
            yield inp.next_type_gap(rng)

    n = macos.type_text("hi", gaps(), post=seen.append)
    assert n == 2
    assert all(0.0 <= g <= 0.4 for _, _, g in seen)
