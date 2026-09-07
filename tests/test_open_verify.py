"""Open-verification, key usability, and tight keystroke cues.

Covers the failures seen when a model drives the MCP natively:
guessed param names, list-typed keys, unchecked launches, and the
cursor circling on every keystroke.
"""

import json
import math

import pytest

from desktop import move
from desktop.controller import Controller
from desktop.platforms import macos
from desktop.safety import validate_keys
from tests.test_controller import FakeBackend


def _ctl():
    backend = FakeBackend()
    c = Controller(backend=backend, dry_run=False)
    c._backend_for_tests = backend
    return c


def test_keys_list_rejected_with_string_hint():
    with pytest.raises(ValueError, match="must be a string"):
        validate_keys(["ENTER"])
    r = _ctl().command(
        "press", {"keys": ["ENTER"], "app": "Finder", "risk": "none"}
    )
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"
    assert "must be a string" in r["error"]["message"]


def test_unknown_arg_hints_point_at_real_params():
    r = _ctl().command(
        "type", {"text": "hi", "target": "Terminal", "risk": "none"}
    )
    assert r["ok"] is False
    assert "'app'" in r["error"]["message"]
    r = _ctl().command(
        "press", {"text": "ENTER", "app": "Finder", "risk": "none"}
    )
    assert "'keys'" in r["error"]["message"]


def test_launch_and_focus_report_effect_verified():
    ctl = _ctl()
    r = ctl.command("launch", {"app": "Chrome"})
    assert r["data"]["active_window"] == "Chrome"
    assert r["data"]["effect_verified"] is True
    # Fresh backend still on Finder: verification honestly reports false
    r = _ctl().command("focus_app", {"app": "Chrome"})
    assert r["data"]["active_window"] == "Finder"
    assert r["data"]["effect_verified"] is False


def test_new_key_names_validate_and_map():
    assert validate_keys("cmd,space") == ["cmd", "space"]
    assert validate_keys("f5") == ["f5"]
    assert validate_keys("forward_delete") == ["forward_delete"]
    seen = []
    macos.hotkey("cmd,space", post=seen.append)
    assert seen == [("hotkey", 49, macos.FLAG_CMD)]
    seen.clear()
    macos.hotkey("f1", post=seen.append)
    assert seen == [("hotkey", 122, 0)]
    seen.clear()
    macos.hotkey("forward_delete", post=seen.append)
    assert seen == [("hotkey", 117, 0)]


def test_macos_list_apps_parses_running_apps(monkeypatch):
    monkeypatch.setattr(
        macos, "_run_jxa", lambda _s: json.dumps(["Terminal", "Finder", ""])
    )
    assert macos.MacosBackend().list_apps() == ["Finder", "Terminal"]
    monkeypatch.setattr(macos, "_run_jxa", lambda _s: "")
    with pytest.raises(Exception):
        macos.MacosBackend().list_apps()


def test_zero_distance_travel_pulses_instead_of_circling():
    pts = move.points(100, 100, 100, 100, seed=0)
    assert pts[-1] == (100, 100)
    assert len(set(pts)) > 1
    assert max(math.hypot(x - 100, y - 100) for x, y in pts) <= 12


def test_long_move_unchanged_by_pulse_scaling():
    a = move.points(0, 0, 640, 420, seed=7)
    b = move.points(0, 0, 640, 420, seed=7)
    assert a == b
    assert a[-1] == (640, 420)


def test_mcp_tool_schema_names_commands_and_spotlight():
    from desktop.mcp_server import TOOLS

    schema = TOOLS[0]["inputSchema"]["properties"]["command"]
    assert "hotkey" in schema["enum"] and "launch" in schema["enum"]
    assert "cmd,space" in TOOLS[0]["description"]
    assert "effect_verified" in TOOLS[0]["description"]


def test_version_reported_everywhere():
    import desktop

    assert desktop.__version__
    r = _ctl().command("doctor", {})
    assert r["data"]["version"] == desktop.__version__
