"""Effect verification tests. After keyboard input, the controller can prove
the focused element actually received the text (when the OS exposes it), or
honestly report the effect as unverified.
"""

import pytest

from tests.test_controller import FakeBackend
from desktop.controller import Controller


@pytest.fixture
def ctl():
    backend = FakeBackend()
    c = Controller(backend=backend, dry_run=False)
    c._backend_for_tests = backend
    return c


def test_type_with_effect_verify_reports_verified(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    b.focused_element_value = "before"
    b.focused_element_state = {"value": "before"}

    def fake_type(text, gaps, cancelled=None):
        b.focused_element_state = {"value": "before" + text}
        return len(text)

    b.type_text = fake_type
    r = ctl.command("type", {"text": "hi", "app": "Finder", "verify": "effect",
                             "risk": "none"})
    assert r["ok"] is True
    assert r["data"]["effect_verified"] is True
    assert "focused_value_contains" not in r["data"]


def test_type_effect_not_visible_reports_unverified(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    b.focused_element_state = {"value": "unrelated"}

    def fake_type(text, gaps, cancelled=None):
        b.focused_element_state = {"value": "unrelated"}  # text did NOT land
        return len(text)

    b.type_text = fake_type
    r = ctl.command("type", {"text": "hi", "app": "Finder", "verify": "effect",
                             "risk": "none"})
    assert r["ok"] is True  # dispatch succeeded; effect honestly unverified
    assert r["data"]["effect_verified"] is False


def test_type_effect_is_not_verified_when_text_was_already_present(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    b.focused_element_state = {"value": "hi"}

    r = ctl.command(
        "type",
        {"text": "hi", "app": "Finder", "verify": "effect", "risk": "none"},
    )

    assert r["ok"] is True
    assert r["data"]["effect_verified"] is False


def test_type_effect_is_not_verified_by_an_unrelated_change_containing_text(ctl):
    backend = ctl._backend_for_tests
    backend.frontmost = "Finder"
    backend.focused_element_state = {"value": "before"}

    def fake_type(text, gaps, cancelled=None):
        backend.focused_element_state = {"value": "private unrelated change"}
        return len(text)

    backend.type_text = fake_type
    result = ctl.command(
        "type",
        {
            "text": "private",
            "app": "Finder",
            "verify": "effect",
            "risk": "none",
        },
    )

    assert result["ok"] is True
    assert result["data"]["effect_verified"] is False


def test_type_effect_unavailable_reports_null(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    r = ctl.command("type", {"text": "hi", "app": "Finder", "verify": "effect",
                             "risk": "none"})
    assert r["ok"] is True
    assert "effect_verified" not in r["data"] or r["data"]["effect_verified"] is None


def test_type_post_dispatch_probe_failure_preserves_success_receipt(ctl):
    backend = ctl._backend_for_tests
    backend.frontmost = "Finder"
    probes = 0

    def focused_element():
        nonlocal probes
        probes += 1
        if probes <= 3:
            return {"value": "before"}
        raise RuntimeError("element became unavailable after dispatch")

    backend.focused_element = focused_element

    result = ctl.command(
        "type",
        {
            "text": "hi",
            "app": "Finder",
            "verify": "effect",
            "risk": "none",
        },
    )

    assert result["ok"] is True
    assert result["data"]["executed"] is True
    assert result["data"]["chars"] == 2
    assert result["data"]["effect_verified"] is None


def test_press_effect_verify_checks_focus_still_correct(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Finder"
    r = ctl.command("press", {"keys": "return", "app": "Finder", "verify": "focus",
                              "risk": "none"})
    assert r["ok"] is True
    assert r["data"]["effect_verified"] is True


@pytest.mark.parametrize(("command", "keys"), [("press", "return"), ("hotkey", "cmd,s")])
def test_key_effect_verification_is_unavailable_without_operation_evidence(
    ctl, command, keys
):
    result = ctl.command(
        command,
        {
            "keys": keys,
            "app": "Finder",
            "verify": "effect",
            "risk": "none",
        },
    )

    assert result["ok"] is True
    assert result["data"]["effect_verified"] is None
