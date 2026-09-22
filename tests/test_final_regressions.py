"""Late audit regressions at public controller, CLI, and MCP boundaries."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from desktop.controller import Controller
from desktop.mcp_server import McpServer
from tests.test_controller import FakeBackend


def test_nested_batch_inherits_outer_keyboard_target_before_and_during_dispatch():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "batch",
            {
                "app": "Finder",
                "risk": "none",
                "actions": [
                    {
                        "op": "batch",
                        "actions": [{"op": "type", "text": "safe"}],
                    }
                ],
            },
        )
    finally:
        controller.close()

    assert result["ok"] is True
    assert [e for e in backend.events if e[0] != "move"] == [("type", "safe")]


def test_batch_deadline_interrupts_a_running_wait():
    controller = Controller(backend=FakeBackend(), dry_run=False)
    started = time.monotonic()
    try:
        result = controller.command(
            "batch",
            {
                "deadline_ms": 30,
                "actions": [{"op": "wait", "seconds": 0.2}],
            },
        )
    finally:
        controller.close()

    assert time.monotonic() - started < 0.15
    assert result["ok"] is False
    assert result["error"]["code"] == "deadline_exceeded"
    assert result["data"]["status"] == "deadline_exceeded"


def test_mcp_rejects_non_string_method_with_json_rpc_error():
    server = McpServer(backend=FakeBackend())
    try:
        response = server.handle_line(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": {"bad": True}})
        )
    finally:
        server.controller.close()

    assert json.loads(response)["error"]["code"] == -32600


def test_effect_verification_never_echoes_typed_text():
    backend = FakeBackend()
    backend.focused_element_state = {"value": "before"}

    def type_and_update(text, gaps, cancelled=None):
        backend.focused_element_state = {"value": "before" + text}
        return len(text)

    backend.type_text = type_and_update
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type",
            {
                "text": "private-value",
                "app": "Finder",
                "risk": "none",
                "verify": "effect",
            },
        )
    finally:
        controller.close()

    assert result["data"]["effect_verified"] is True
    assert "private-value" not in json.dumps(result)


def test_second_safety_state_probe_failure_fails_closed_as_needs_attention():
    backend = FakeBackend()
    probes = 0

    def focused_element():
        nonlocal probes
        probes += 1
        if probes == 1:
            return {"role": "AXTextField"}
        raise RuntimeError("focused element disappeared")

    backend.focused_element = focused_element
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type", {"text": "safe", "app": "Finder", "risk": "none"}
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_cli_does_not_invent_a_none_risk_for_the_caller():
    environment = dict(os.environ)
    environment["DESKTOP_FAKE_BACKEND"] = "1"
    environment["PYTHONPATH"] = os.path.dirname(os.path.dirname(__file__))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "desktop.cli",
            "type",
            "safe",
            "--app",
            "Finder",
            "--execute",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
    )

    envelope = json.loads(result.stdout)
    assert result.returncode == 2
    assert envelope["error"]["code"] == "bad_arg"
    assert "risk" in envelope["error"]["message"]


def test_text_rejects_embedded_nul_before_backend_input():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type",
            {"text": "before\0after", "app": "Finder", "risk": "none"},
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_batch_rechecks_frame_after_an_observation_replaces_it():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        first = controller.command("observe", {"metadata_only": True})
        old_frame = first["data"]["frame_id"]
        backend.events.clear()
        result = controller.command(
            "batch",
            {
                "actions": [
                    {"op": "observe", "metadata_only": True},
                    {
                        "op": "click",
                        "x": 10,
                        "y": 10,
                        "frame_id": old_frame,
                        "risk": "none",
                    },
                ]
            },
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert result["data"]["last_completed"] == 0
    assert not any(event[0] == "click" for event in backend.events)


def test_batch_copies_nested_input_before_preflight_and_dispatch():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    observed = controller.command("observe", {"metadata_only": True})
    frame_id = observed["data"]["frame_id"]
    backend.events.clear()
    actions = [
        {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
        {"op": "wait", "seconds": 0},
    ]

    def mutate_caller_data(direction, amount, cancelled=None):
        backend.events.append(("scroll", direction, amount))
        actions[1].clear()
        actions[1].update({
            "op": "click",
            "x": 10,
            "y": 10,
            "frame_id": frame_id,
            "risk": "deletion",
        })

    backend.scroll = mutate_caller_data
    try:
        result = controller.command("batch", {"actions": actions})
    finally:
        controller.close()

    assert result["ok"] is True
    assert [e for e in backend.events if e[0] != "move"] == [("scroll", "down", 1)]


def test_batch_rejects_base64_observation_receipts_before_capture():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "batch",
            {"actions": [{"op": "observe"}, {"op": "observe"}]},
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_batch_rejects_mutable_path_observation_receipts_before_capture():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "batch",
            {"actions": [{"op": "observe", "path_mode": True}]},
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_press_rejects_modifiers_and_multiple_non_modifier_keys():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        modifier = controller.command(
            "press", {"keys": "cmd", "app": "Finder", "risk": "none"}
        )
        multiple = controller.command(
            "press", {"keys": "a,b", "app": "Finder", "risk": "none"}
        )
    finally:
        controller.close()

    assert modifier["error"]["code"] == "bad_arg"
    assert multiple["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_hotkey_rejects_multiple_non_modifier_keys():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "hotkey", {"keys": "cmd,a,b", "app": "Finder", "risk": "none"}
        )
    finally:
        controller.close()

    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_macos_hotkey_does_not_silently_drop_win_modifier():
    from desktop.platforms.macos import hotkey

    with pytest.raises(ValueError, match="win.*macOS"):
        hotkey("win,r", post=lambda _event: None)


def test_stop_command_interrupts_active_request_without_waiting_for_action_lock():
    controller = Controller(backend=FakeBackend(), dry_run=False)
    result_holder = {}

    def run_wait():
        result_holder["wait"] = controller.command(
            "wait", {"seconds": 0.2}, request_id="active-wait"
        )

    thread = threading.Thread(target=run_wait)
    thread.start()
    time.sleep(0.03)
    started = time.monotonic()
    stopped = controller.command("stop", {})
    stop_elapsed = time.monotonic() - started
    thread.join(timeout=1)
    controller.close()

    assert stop_elapsed < 0.05
    assert stopped["data"]["stopped"] is True
    assert result_holder["wait"]["error"]["code"] == "cancelled"


def test_idle_controller_stop_is_honest_and_does_not_poison_next_request():
    controller = Controller(backend=FakeBackend(), dry_run=False)
    try:
        stopped = controller.command("stop", {})
        next_result = controller.command("wait", {"seconds": 0})
    finally:
        controller.close()

    assert stopped["data"]["stopped"] is False
    assert next_result["ok"] is True


def test_stop_params_still_require_an_object():
    controller = Controller(backend=FakeBackend(), dry_run=False)
    try:
        result = controller.command("stop", [])
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"


def test_controller_converts_excessive_nesting_to_bad_arg_without_events():
    backend = FakeBackend()
    params = {"actions": []}
    for _ in range(1100):
        params = {"actions": [{"op": "batch", **params}]}
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command("batch", params)
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_mcp_converts_excessive_json_nesting_to_parse_error():
    server = McpServer(backend=FakeBackend())
    line = (
        '{"jsonrpc":"2.0","id":1,"method":"ping","params":'
        + "[" * 1100
        + "0"
        + "]" * 1100
        + "}"
    )
    try:
        response = server.handle_line(line)
    finally:
        server.controller.close()

    assert json.loads(response)["error"]["code"] == -32700


def test_mcp_does_not_execute_idless_tool_notification():
    backend = FakeBackend()
    server = McpServer(backend=backend, dry_run=False)
    line = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "desktop",
                "arguments": {
                    "command": "scroll",
                    "params": {"direction": "down", "amount": 1, "risk": "none"},
                },
            },
        }
    )
    try:
        response = server.handle_line(line)
    finally:
        server.controller.close()

    assert response is None
    assert backend.events == []


def test_mcp_rejects_non_json_numeric_constants():
    server = McpServer(backend=FakeBackend())
    try:
        response = server.handle_line(
            '{"jsonrpc":"2.0","id":NaN,"method":"ping","params":{}}'
        )
    finally:
        server.controller.close()

    assert json.loads(response)["error"]["code"] == -32700


@pytest.mark.parametrize("request_id", [True, [], {"nested": 1}])
def test_mcp_rejects_invalid_request_id_types(request_id):
    server = McpServer(backend=FakeBackend())
    try:
        response = server.handle_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "ping",
                    "params": {},
                }
            )
        )
    finally:
        server.controller.close()

    parsed = json.loads(response)
    assert parsed["id"] is None
    assert parsed["error"]["code"] == -32600


def test_native_helper_guards_every_input_command_with_accessibility_trust():
    source = (
        os.path.dirname(os.path.dirname(__file__)) + "/native/cghelper.c"
    )
    with open(source, encoding="utf-8") as helper_source:
        code = helper_source.read()

    assert "requires_accessibility(argv[1]) && !AXIsProcessTrusted()" in code


@pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("COMPUTER_AUTOMATION_LIVE_TEST") != "1",
    reason="live desktop checks require an explicit macOS opt-in",
)
def test_live_native_helper_returns_focused_metadata():
    root = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        os.path.join(root, "build", "cghelper"),
        os.path.join(root, "desktop", "_bin", "cghelper"),
    ]
    helper = next((path for path in candidates if os.path.isfile(path)), None)
    if helper is None:
        pytest.skip("macOS cghelper is not built")

    with tempfile.NamedTemporaryFile(
        prefix="computer-automation-rust-focus-", suffix=".txt", delete=False
    ) as document:
        document.write(b"rust focus regression\n")
        document_path = document.name
    document_name = os.path.basename(document_path)
    try:
        launch = subprocess.run(
            ["open", "-a", "TextEdit", document_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert launch.returncode == 0, launch.stderr
        deadline = time.monotonic() + 5
        result = None
        while time.monotonic() < deadline:
            result = subprocess.run(
                [helper, "focused"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                break
            time.sleep(0.05)
        assert result is not None
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert isinstance(state, dict)
        assert state.get("role")
    finally:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "TextEdit" to close (first document whose name is "{document_name}") saving no',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        try:
            os.unlink(document_path)
        except FileNotFoundError:
            pass


def test_native_scroll_loop_has_no_unrequested_artificial_delay():
    source = os.path.dirname(os.path.dirname(__file__)) + "/native/cghelper.c"
    with open(source, encoding="utf-8") as helper_source:
        code = helper_source.read()
    scroll_loop = code[code.index('strcmp(argv[1], "scroll")'):
                       code.index('strcmp(argv[1], "type")')]

    assert "usleep" not in scroll_loop


def test_native_cancelled_drag_releases_at_last_completed_point():
    source = os.path.dirname(os.path.dirname(__file__)) + "/native/cghelper.c"
    with open(source, encoding="utf-8") as helper_source:
        code = helper_source.read()
    drag_block = code[code.index('strcmp(argv[1], "drag")'):
                      code.index('strcmp(argv[1], "scroll")')]

    assert "release_x = x" in drag_block
    assert "release_y = y" in drag_block
    assert "kCGEventLeftMouseUp, release_x, release_y" in drag_block
    assert "kCGEventLeftMouseUp, x2, y2" not in drag_block


def test_native_key_receipt_reports_a_completed_primitive():
    source = os.path.dirname(os.path.dirname(__file__)) + "/native/cghelper.c"
    with open(source, encoding="utf-8") as helper_source:
        code = helper_source.read()
    key_block = code[code.index('strcmp(argv[1], "key")'):
                     code.index('strcmp(argv[1], "release")')]

    assert 'printf("1\\n")' in key_block


def test_omitted_timing_uses_native_typing_without_artificial_gaps():
    backend = FakeBackend()
    observed_gaps = []

    def capture_gaps(text, gaps, cancelled=None):
        observed_gaps.extend(gaps)
        return len(text)

    backend.type_text = capture_gaps
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type", {"text": "abc", "app": "Finder", "risk": "none"}
        )
    finally:
        controller.close()

    assert result["ok"] is True
    assert observed_gaps == [0.0, 0.0, 0.0]


def test_omitted_timing_preserves_visible_pointer_duration():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        backend.events.clear()
        result = controller.command(
            "move",
            {
                "x": 100,
                "y": 100,
                "frame_id": observed["data"]["frame_id"],
                "risk": "none",
            },
        )
    finally:
        controller.close()

    assert result["ok"] is True
    assert backend.events[0][0] == "move"
    assert backend.events[0][2] > 0.0


def test_native_pointer_mode_preserves_curve_and_exact_endpoint():
    backend = FakeBackend()
    dispatched = []

    def capture_path(path, total_secs, cancelled=None):
        dispatched.extend(path)

    backend.move_path = capture_path
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        result = controller.command(
            "move",
            {
                "x": 100,
                "y": 100,
                "frame_id": observed["data"]["frame_id"],
                "risk": "none",
            },
        )
    finally:
        controller.close()

    assert result["ok"] is True
    assert len(set(dispatched)) > 1
    assert dispatched[-1] == (100, 100)


def test_helper_accessibility_exit_becomes_structured_capability_error(monkeypatch):
    from desktop.platforms import macos
    from desktop.platforms.base import CapabilityError

    class Process:
        returncode = 5

        def communicate(self, input=None, timeout=None):
            return "", "cghelper: Accessibility trust missing\n"

    monkeypatch.setattr(macos, "helper_path", lambda: "/safe/cghelper")
    monkeypatch.setattr(macos.subprocess, "Popen", lambda *args, **kwargs: Process())

    with pytest.raises(CapabilityError) as error:
        macos._run(["click", "1", "1", "0", "1"])

    assert error.value.capability == "accessibility"


def test_doctor_marks_permission_checks_blocked_by_missing_helper():
    from desktop.platforms.base import CapabilityError

    backend = FakeBackend()
    backend.helper_available = lambda: (_ for _ in ()).throw(
        CapabilityError("helper", "cghelper missing")
    )
    backend.trusted = lambda: (_ for _ in ()).throw(
        CapabilityError("helper", "cghelper missing")
    )
    backend.screen_recording_authorized = lambda: (_ for _ in ()).throw(
        CapabilityError("helper", "cghelper missing")
    )
    controller = Controller(backend=backend)
    try:
        result = controller.command("doctor", {})
    finally:
        controller.close()

    checks = result["data"]["checks"]
    assert checks["helper"]["ok"] is None
    assert checks["accessibility"]["ok"] is None
    assert "helper" in checks["accessibility"]["recover"].lower()
    assert checks["screen_recording"]["ok"] is None
    assert "helper" in checks["screen_recording"]["recover"].lower()


def test_macos_capture_refuses_revoked_screen_recording_before_mss(monkeypatch):
    from desktop.platforms.macos import MacosBackend
    from desktop.platforms.base import CapabilityError

    backend = MacosBackend()
    monkeypatch.setattr(backend, "screen_recording_authorized", lambda: False)
    monkeypatch.setitem(
        sys.modules,
        "mss",
        type("NoCapture", (), {"MSS": lambda: pytest.fail("MSS must not run")}),
    )

    with pytest.raises(CapabilityError) as error:
        backend.capture_region(0, 0, 1, 1)

    assert error.value.capability == "screen_recording"


def test_short_type_count_is_an_honest_partial_failure():
    backend = FakeBackend()
    backend.type_text = lambda text, gaps, cancelled=None: 2
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type", {"text": "hello", "app": "Finder", "risk": "none"}
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert result["data"]["chars"] == 2
    assert result["data"]["requested_chars"] == 5


def test_click_type_short_count_preserves_click_and_partial_type_receipts():
    backend = FakeBackend()
    backend.type_text = lambda text, gaps, cancelled=None: 2
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        backend.events.clear()
        result = controller.command(
            "click_type",
            {
                "text": "hello",
                "app": "Finder",
                "x": 10,
                "y": 10,
                "frame_id": observed["data"]["frame_id"],
                "risk": "none",
            },
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert result["data"]["last_completed"] == "click"
    assert result["data"]["chars"] == 2
    assert [receipt["status"] for receipt in result["data"]["receipts"]] == [
        "ok",
        "partial",
    ]


def test_type_backend_failure_after_dispatch_reports_unknown_partial_without_text():
    backend = FakeBackend()
    backend.type_text = lambda text, gaps, cancelled=None: (_ for _ in ()).throw(
        RuntimeError(f"failed while typing {text}")
    )
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command(
            "type",
            {"text": "private-value", "app": "Finder", "risk": "none"},
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert result["data"]["chars"] is None
    assert result["data"]["receipts"] == [
        {"step": "type", "status": "unknown"}
    ]
    assert "private-value" not in json.dumps(result)


def test_click_type_invalid_count_preserves_click_and_unknown_type_receipt():
    backend = FakeBackend()
    backend.type_text = lambda text, gaps, cancelled=None: None
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        result = controller.command(
            "click_type",
            {
                "text": "hello",
                "app": "Finder",
                "x": 10,
                "y": 10,
                "frame_id": observed["data"]["frame_id"],
                "risk": "none",
            },
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert result["data"]["last_completed"] == "click"
    assert result["data"]["chars"] is None
    assert result["data"]["receipts"] == [
        {"step": "click", "status": "ok"},
        {"step": "type", "status": "unknown"},
    ]


def test_observe_budgets_actual_result_metadata_before_capture():
    backend = FakeBackend()
    backend.screen = {"width": 1, "height": 1}
    backend.frontmost = "W" * 2_000
    controller = Controller(backend=backend, dry_run=False, frame_bytes=1_000)
    try:
        result = controller.command("observe", {"metadata_only": True})
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert "too_large" in result["error"]["message"]
    assert backend.events == []


def test_observe_rejects_invalid_active_window_metadata_before_capture():
    backend = FakeBackend()
    backend.frontmost = {"not": "a window name"}
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command("observe", {"metadata_only": True})
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert backend.events == []


def test_focus_change_invalidates_a_coordinate_frame_before_input():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        backend.frontmost = "OtherApp"
        backend.events.clear()
        result = controller.command(
            "click",
            {
                "x": 10,
                "y": 10,
                "frame_id": observed["data"]["frame_id"],
                "risk": "none",
            },
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert backend.events == []


def test_focus_change_during_capture_does_not_publish_a_frame():
    backend = FakeBackend()
    original_capture = backend.capture_region

    def capture_then_switch(x, y, width, height):
        captured = original_capture(x, y, width, height)
        backend.frontmost = "OtherApp"
        return captured

    backend.capture_region = capture_then_switch
    controller = Controller(backend=backend, dry_run=False)
    try:
        result = controller.command("observe", {"metadata_only": True})
        latest = controller.frames.latest()
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert latest is None


def test_batch_backend_failure_after_input_start_preserves_unknown_receipt():
    backend = FakeBackend()

    def uncertain_click(x, y, button="left", double=False, cancelled=None):
        backend.events.append(("possibly-clicked", x, y))
        raise RuntimeError("backend lost its acknowledgement")

    backend.click = uncertain_click
    controller = Controller(backend=backend, dry_run=False)
    try:
        observed = controller.command("observe", {"metadata_only": True})
        backend.events.clear()
        result = controller.command(
            "batch",
            {
                "actions": [
                    {"op": "wait", "seconds": 0},
                    {
                        "op": "click",
                        "x": 10,
                        "y": 10,
                        "frame_id": observed["data"]["frame_id"],
                        "risk": "none",
                    },
                ]
            },
        )
    finally:
        controller.close()

    assert result["ok"] is False
    assert result["data"]["last_completed"] == 0
    failed = result["data"]["receipts"][1]
    assert failed["status"] == "failed"
    assert failed["data"]["last_completed"] is None
    assert failed["data"]["receipts"] == [
        {"step": "click", "status": "unknown"}
    ]
