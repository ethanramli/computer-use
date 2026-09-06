"""Regressions for the current independent-review remediation goal.

Public seam: ``Controller.command(name, params)``.  The recording backend
proves whether any OS input primitive crossed the backend interface.
"""

import pytest
import inspect

from desktop.controller import Controller
from tests.test_controller import FakeBackend


def make_controller():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False)
    return controller, backend


def test_batch_invalid_canonical_double_click_sends_zero_events():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
                {"op": "double-click", "x": 10, "risk": "none"},
            ]
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert backend.events == []


def test_batch_later_unconfirmed_consequential_text_sends_zero_events():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "app": "Finder",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
                {"op": "type", "text": "hello", "risk": "message"},
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_batch_later_invalid_frame_id_sends_zero_events():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
                {"op": "click", "x": 10, "y": 20, "frame_id": "frame-missing", "risk": "none"},
            ]
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert backend.events == []


def test_batch_dispatch_failure_preserves_receipts_and_last_completed():
    controller, backend = make_controller()
    original_scroll = backend.scroll
    calls = 0

    def fail_second_scroll(direction, amount, cancelled=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected backend failure")
        original_scroll(direction, amount, cancelled=cancelled)

    backend.scroll = fail_second_scroll
    result = controller.command(
        "batch",
        {
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
            ]
        },
    )

    assert result["ok"] is False
    assert result["data"]["last_completed"] == 0
    assert result["data"]["receipts"] == [
        {
            "index": 0,
            "status": "ok",
            "data": {"executed": True, "direction": "down", "amount": 1},
        },
            {
                "index": 1,
                "status": "failed",
                "error": {
                    "code": "exec_failed",
                    "message": (
                        "scroll failed after input dispatch began; "
                        "completion is unknown"
                    ),
                    "recover": (
                        "inspect the target before retrying; input cannot be undone"
                    ),
                },
                "data": {
                    "executed": False,
                    "last_completed": None,
                    "receipts": [{"step": "scroll", "status": "unknown"}],
                },
            },
        ]


def test_batch_keyboard_requires_action_or_batch_target_before_dispatch():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"},
                {"op": "type", "text": "hello", "risk": "none"},
            ]
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "focus_required"
    assert backend.events == []


def test_confirmation_must_be_literal_true():
    controller, backend = make_controller()

    result = controller.command(
        "type",
        {
            "text": "hello",
            "app": "Finder",
            "risk": "message",
            "confirm": "true",
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_input_requires_explicit_risk_classification():
    controller, backend = make_controller()

    result = controller.command("type", {"text": "hello", "app": "Finder"})

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "risk" in result["error"]["message"]
    assert backend.events == []


def test_batch_later_invalid_timing_sends_zero_events():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "app": "Finder",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {"op": "type", "text": "hello", "timing": "warp"},
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "timing" in result["error"]["message"]
    assert backend.events == []


def test_batch_later_nested_invalid_deadline_sends_zero_events():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {
                    "op": "batch",
                    "deadline_ms": 1_000_000,
                    "actions": [{"op": "wait", "seconds": 0}],
                },
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "deadline_ms" in result["error"]["message"]
    assert backend.events == []


def test_batch_action_limit_counts_nested_actions_before_dispatch():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {
                    "op": "batch",
                    "actions": [{"op": "wait", "seconds": 0}] * 500,
                },
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "too many actions" in result["error"]["message"]
    assert backend.events == []


def test_batch_payload_limit_uses_utf8_bytes_before_dispatch():
    controller, backend = make_controller()
    large_text = "😀" * 100_000

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "app": "Finder",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                *[
                    {"op": "type", "text": large_text, "timing": "native"}
                    for _ in range(11)
                ],
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "bytes" in result["error"]["message"]
    assert backend.events == []


def test_batch_rejects_unknown_later_action_argument_before_dispatch():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {"op": "wait", "seconds": 0, "mystery": True},
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "mystery" in result["error"]["message"]
    assert backend.events == []


def test_batch_rejects_boolean_numeric_argument_before_dispatch():
    controller, backend = make_controller()

    result = controller.command(
        "batch",
        {
            "risk": "none",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {"op": "scroll", "direction": "down", "amount": True},
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "amount" in result["error"]["message"]
    assert backend.events == []


def test_blocked_hotkey_uses_canonical_aliases_and_modifier_order():
    controller, backend = make_controller()

    result = controller.command(
        "hotkey",
        {
            "keys": "q-command-shift",
            "app": "Finder",
            "risk": "none",
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "blocked"
    assert backend.events == []


def test_secure_focused_element_stops_keyboard_input():
    controller, backend = make_controller()
    backend.focused_element_state = {
        "role": "AXSecureTextField",
        "title": "Password",
    }

    result = controller.command(
        "type",
        {"text": "hello", "app": "Finder", "risk": "none"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


@pytest.mark.parametrize(
    "risk",
    ["deletion", "purchase", "message", "publishing", "permission", "account_security"],
)
def test_each_consequential_category_requires_confirmation(risk):
    controller, backend = make_controller()

    result = controller.command(
        "scroll", {"direction": "down", "amount": 1, "risk": risk}
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("move", {"x": 1, "y": 1}),
        ("click", {"x": 1, "y": 1}),
        ("double-click", {"x": 1, "y": 1}),
        ("right_click", {"x": 1, "y": 1}),
        ("drag", {"from_x": 1, "from_y": 1, "to_x": 2, "to_y": 2}),
        ("scroll", {"direction": "down", "amount": 1}),
        ("type", {"text": "hello", "app": "Finder"}),
        ("click_type", {"text": "hello", "app": "Finder", "x": 1, "y": 1}),
        ("press", {"keys": "enter", "app": "Finder"}),
        ("hotkey", {"keys": "cmd,s", "app": "Finder"}),
    ],
)
def test_every_input_family_uses_the_consequential_gate(command, params):
    controller, backend = make_controller()

    result = controller.command(command, {**params, "risk": "deletion"})

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


@pytest.mark.parametrize("confirm", ["true", 1, {"truthy": True}])
def test_truthy_non_boolean_confirmation_never_authorizes_input(confirm):
    controller, backend = make_controller()

    result = controller.command(
        "scroll",
        {
            "direction": "down",
            "amount": 1,
            "risk": "purchase",
            "confirm": confirm,
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_region_frame_only_authorizes_coordinates_inside_captured_region():
    controller, backend = make_controller()
    observed = controller.command("observe", {"region": "100,100,50,50"})
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

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert backend.events == []


def test_controller_uses_only_the_shared_app_matching_seam():
    import desktop.controller as controller_module

    assert "platforms.macos" not in inspect.getsource(controller_module)


def test_macos_backend_lists_running_apps_and_fails_honestly(monkeypatch):
    import json

    from desktop.platforms import macos
    from desktop.platforms.base import Backend, CapabilityError
    from desktop.platforms.macos import MacosBackend

    backend = MacosBackend()
    assert isinstance(backend, Backend)
    monkeypatch.setattr(
        macos, "_run_jxa", lambda _script: json.dumps(["Terminal", "Finder"])
    )
    assert backend.list_apps() == ["Finder", "Terminal"]
    monkeypatch.setattr(macos, "_run_jxa", lambda _script: "")
    with pytest.raises(CapabilityError) as error:
        backend.list_apps()
    assert error.value.capability == "list_apps"


def test_macos_input_reports_missing_helper_and_accessibility_separately(monkeypatch):
    from desktop.platforms.base import CapabilityError
    from desktop.platforms import macos

    backend = macos.MacosBackend()
    monkeypatch.setattr(
        macos,
        "helper_path",
        lambda: (_ for _ in ()).throw(
            CapabilityError("helper", "cghelper missing")
        ),
    )
    with pytest.raises(CapabilityError) as missing_helper:
        backend.click(1, 1)
    assert missing_helper.value.capability == "helper"

    monkeypatch.setattr(
        macos,
        "click",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CapabilityError("accessibility", "Accessibility trust missing")
        ),
    )
    with pytest.raises(CapabilityError) as untrusted:
        backend.click(1, 1)
    assert untrusted.value.capability == "accessibility"


def test_macos_focus_error_is_controller_focus_failed(monkeypatch):
    from desktop.platforms import macos
    from desktop.platforms.base import FocusError

    monkeypatch.setattr(
        macos,
        "focus_app",
        lambda app, timeout=5.0: (_ for _ in ()).throw(
            FocusError("frontmost app could not be verified")
        ),
    )
    result = Controller(macos.MacosBackend(), dry_run=False).command(
        "focus_app", {"app": "Finder"}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "focus_failed"


def test_macos_focused_element_returns_metadata_without_field_value(monkeypatch):
    from desktop.platforms import macos

    monkeypatch.setattr(
        macos,
        "_run",
        lambda args, stdin_text=None: (
            '{"role":"AXTextField","subrole":"AXSecureTextField",'
            '"title":"Password","window_title":"Sign in"}'
        ),
    )

    state = macos.MacosBackend().focused_element()

    assert state["subrole"] == "AXSecureTextField"
    assert state["window_title"] == "Sign in"
    assert "value" not in state


def test_click_type_inspects_coordinate_target_before_clicking():
    controller, backend = make_controller()
    backend.element_at = lambda x, y: {
        "role": "AXTextField",
        "subrole": "AXSecureTextField",
        "title": "Password",
    }
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

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_keyboard_rechecks_ui_state_immediately_before_typing():
    controller, backend = make_controller()
    states = iter(
        [
            {"role": "AXTextField", "title": "Notes"},
            {"role": "AXSecureTextField", "title": "Password"},
        ]
    )
    backend.focused_element = lambda: next(states)

    result = controller.command(
        "type",
        {"text": "hello", "app": "Finder", "risk": "none"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert backend.events == []


def test_click_type_rechecks_focus_after_click_and_reports_partial_dispatch():
    controller, backend = make_controller()
    observed = controller.command("observe", {"metadata_only": True})
    backend.events.clear()
    original_click = backend.click

    def click_then_focus_secure_field(*args, **kwargs):
        original_click(*args, **kwargs)
        backend.focused_element_state = {
            "role": "AXSecureTextField",
            "title": "Password",
        }

    backend.click = click_then_focus_secure_field
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

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert result["data"] == {
        "executed": False,
        "clicked": True,
        "typed": False,
        "last_completed": "click",
        "receipts": [{"step": "click", "status": "ok"}],
    }
    assert [e for e in backend.events if e[0] != "move"] == [("click", 10, 10, "left", False)]


def test_batch_preserves_partial_action_receipt_after_click_type_click():
    controller, backend = make_controller()
    observed = controller.command("observe", {"metadata_only": True})
    backend.events.clear()
    original_click = backend.click

    def click_then_focus_secure_field(*args, **kwargs):
        original_click(*args, **kwargs)
        backend.focused_element_state = {
            "role": "AXSecureTextField",
            "title": "Password",
        }

    backend.click = click_then_focus_secure_field
    result = controller.command(
        "batch",
        {
            "app": "Finder",
            "risk": "none",
            "actions": [
                {
                    "op": "click_type",
                    "text": "hello",
                    "x": 10,
                    "y": 10,
                    "frame_id": observed["data"]["frame_id"],
                }
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "needs_attention"
    assert result["data"]["last_completed"] == -1
    assert result["data"]["receipts"][0]["status"] == "failed"
    assert result["data"]["receipts"][0]["data"]["last_completed"] == "click"
    assert [e for e in backend.events if e[0] != "move"] == [("click", 10, 10, "left", False)]


def test_observe_rejects_pixel_budget_before_backend_capture():
    backend = FakeBackend()
    controller = Controller(backend=backend, dry_run=False, frame_bytes=100)

    result = controller.command("observe", {"region": "0,0,10,10"})

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert backend.events == []


def test_layout_scale_change_invalidates_an_existing_frame():
    controller, backend = make_controller()
    observed = controller.command("observe", {"metadata_only": True})
    backend.events.clear()
    original_layout = backend.display_layout

    def changed_layout():
        layout = original_layout()
        layout["displays"][0]["scale"] = [2.0, 2.0]
        return layout

    backend.display_layout = changed_layout
    result = controller.command(
        "click",
        {
            "x": 10,
            "y": 10,
            "frame_id": observed["data"]["frame_id"],
            "risk": "none",
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert backend.events == []


def test_observe_returns_full_layout_and_owned_png():
    controller, _ = make_controller()

    result = controller.command("observe", {})

    assert result["ok"] is True
    assert result["data"]["layout"]["displays"][0]["scale"] == [1.0, 1.0]
    assert result["data"]["layout"]["displays"][0]["rotation"] == 0.0
    import base64
    assert base64.b64decode(result["data"]["image_b64"]).startswith(
        b"\x89PNG\r\n\x1a\n"
    )


def test_negative_origin_coordinate_is_authorized_by_observed_layout():
    controller, backend = make_controller()
    backend.screen = {"left": -200, "top": 0, "width": 400, "height": 200}
    observed = controller.command("observe", {"metadata_only": True})
    backend.events.clear()

    result = controller.command(
        "click",
        {
            "x": -100,
            "y": 20,
            "frame_id": observed["data"]["frame_id"],
            "risk": "none",
        },
    )

    assert result["ok"] is True
    assert backend.events[0][0] == "move"
    assert backend.events[0][1] == (-100, 20)
    assert backend.events[1] == ("click", -100, 20, "left", False)


def test_invalid_backend_layout_fails_before_capture():
    controller, backend = make_controller()
    backend.display_layout = lambda: {
        "origin": [0, 0],
        "width": 100,
        "height": 100,
        "displays": [
            {
                "id": "broken",
                "origin": [0, 0],
                "width": 100,
                "height": 100,
                # scale and rotation are required frame-freshness inputs
            }
        ],
    }

    result = controller.command("observe", {})

    assert result["ok"] is False
    assert result["error"]["code"] == "exec_failed"
    assert backend.events == []


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("move", {"x": 200, "y": 200}),
        ("click", {"x": 200, "y": 200}),
        ("double-click", {"x": 200, "y": 200}),
        ("right_click", {"x": 200, "y": 200}),
        (
            "drag",
            {"from_x": 110, "from_y": 110, "to_x": 200, "to_y": 200},
        ),
        (
            "click_type",
            {"x": 200, "y": 200, "text": "hello", "app": "Finder"},
        ),
    ],
)
def test_every_coordinate_input_uses_the_same_region_guard(command, params):
    controller, backend = make_controller()
    observed = controller.command(
        "observe", {"region": "100,100,50,50", "metadata_only": True}
    )
    backend.events.clear()

    result = controller.command(
        command,
        {
            **params,
            "frame_id": observed["data"]["frame_id"],
            "risk": "none",
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stale_frame"
    assert backend.events == []


def test_controller_path_mode_returns_stable_path_and_shutdown_cleans_it():
    from pathlib import Path

    controller, _ = make_controller()
    first = controller.command("observe", {"path_mode": True})
    path = Path(first["data"]["path"])
    parent = path.parent
    assert path.exists()

    second = controller.command("observe", {"path_mode": True})
    assert second["data"]["path"] == str(path)
    assert path.exists()

    controller.close()
    assert not path.exists()
    assert not parent.exists()


def test_replacing_path_observation_removes_previous_screenshot():
    from pathlib import Path

    controller, _ = make_controller()
    first = controller.command("observe", {"path_mode": True})
    path = Path(first["data"]["path"])
    parent = path.parent

    result = controller.command("observe", {"metadata_only": True})

    assert result["ok"] is True
    assert not path.exists()
    controller.close()
    assert not parent.exists()


def test_controller_rejects_non_object_params_without_coercing_them():
    controller, backend = make_controller()

    result = controller.command("wait", [["seconds", 0]])

    assert result["ok"] is False
    assert result["error"]["code"] == "bad_arg"
    assert "object" in result["error"]["message"]
    assert backend.events == []


def test_doctor_reports_each_dependency_and_permission_separately():
    controller, _ = make_controller()

    result = controller.command("doctor", {})

    assert result["ok"] is True
    assert set(result["data"]["checks"]) == {
        "helper", "accessibility", "screen_recording", "mss"
    }
    assert all(
        "ok" in check and "recover" in check
        for check in result["data"]["checks"].values()
    )


def test_doctor_gives_specific_recovery_for_each_missing_component():
    controller, backend = make_controller()
    backend.helper_available = lambda: False
    backend.trusted = lambda: False
    backend.screen_recording_authorized = lambda: False

    result = controller.command("doctor", {})
    checks = result["data"]["checks"]

    assert checks["helper"]["ok"] is False
    assert "native/cghelper.c" in checks["helper"]["recover"]
    assert checks["accessibility"]["ok"] is False
    assert "Accessibility" in checks["accessibility"]["recover"]
    assert checks["screen_recording"]["ok"] is False
    assert "Screen Recording" in checks["screen_recording"]["recover"]
    assert checks["mss"]["recover"] != checks["helper"]["recover"]
