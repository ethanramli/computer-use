"""Regression tests for review findings. Each maps to a finding in
the archived 2026-09-04 standards and spec reviews."""

import pytest

from desktop import protocol
from desktop.controller import Controller
from desktop.platforms.base import CapabilityError
from tests.test_controller import FakeBackend


@pytest.fixture
def ctl():
    backend = FakeBackend()
    c = Controller(backend=backend, dry_run=False)
    c._backend_for_tests = backend
    return c


# Finding: batched keyboard actions require an explicit action/batch target.

def test_batch_keyboard_without_app_is_rejected(ctl):
    r = ctl.command("batch", {"risk": "none",
                               "actions": [{"op": "type", "text": "hi"}]})
    assert r["ok"] is False
    assert r["error"]["code"] == "focus_required"
    assert ctl._backend_for_tests.events == []


def test_batch_type_app_mismatch_still_refuses(ctl):
    ctl._backend_for_tests.frontmost = "Finder"
    r = ctl.command("batch", {"risk": "none", "actions": [
        {"op": "type", "text": "hi", "app": "Chrome"}]})
    assert r["ok"] is False
    assert ctl._backend_for_tests.events == []


def test_batch_uses_batch_app_context_when_action_lacks_app(ctl):
    r = ctl.command("batch", {
        "app": "Finder",
        "risk": "none",
        "actions": [{"op": "type", "text": "a"}, {"op": "press", "keys": "return"}],
    })
    assert r["ok"] is True


# Finding: batch deadline check must also bound the deadline value.

def test_batch_deadline_bounded(ctl):
    r = ctl.command("batch", {"deadline_ms": 10 ** 9, "actions": [
        {"op": "wait", "seconds": 0.01}]})
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"


# Finding: click without frame_id in live mode was already gated; batch
# click actions must be gated identically (no _in_batch bypass).

def test_batch_click_still_requires_fresh_frame(ctl):
    r = ctl.command("batch", {"risk": "none",
                               "actions": [{"op": "click", "x": 5, "y": 5}]})
    assert r["ok"] is False
    assert "stale_frame" in str(r) or "frame" in str(r).lower()
    assert ctl._backend_for_tests.events == []


# Finding: internal _-prefixed params must be stripped from untrusted input.
# The MCP server and CLI batch --json must not pass _in_batch/_batch_app
# through from user-supplied JSON.

def test_internal_params_stripped_from_batch_actions(ctl):
    # batch action tries to smuggle controller-private context
    b = ctl._backend_for_tests
    b.frontmost = "Chrome"
    r = ctl.command("batch", {"app": "Chrome", "risk": "none", "actions": [
        {"op": "type", "text": "x", "_batch_app": "Finder"}]})
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"
    assert b.events == []


def test_smuggled_batch_app_cannot_supply_required_focus_target(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Chrome"
    # without batch app, action's smuggled _batch_app is ignored entirely
    r = ctl.command("batch", {"risk": "none", "actions": [
        {"op": "type", "text": "y", "_batch_app": "Chrome"}]})
    assert r["ok"] is False
    assert r["error"]["code"] in {"bad_arg", "focus_required"}
    assert b.events == []

def test_mcp_rejects_oversized_params():
    from desktop.mcp_server import McpServer

    s = McpServer(backend=FakeBackend(), dry_run=True)
    big = {"command": "type", "params": {"text": "x" * (5 * 1024 * 1024)}}
    resp = s.handle_line(__import__("json").dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "desktop", "arguments": big}}))
    r = __import__("json").loads(resp)
    # transport-level bound fires first (JSON-RPC error), or tool-level
    # bound returns isError — both are honest rejections
    if "error" in r:
        assert "too large" in r["error"]["message"]
    else:
        assert r["result"]["isError"] is True
        assert "too large" in r["result"]["content"][0]["text"]


# Finding: stop must remain responsive while a batch executes (out-of-band).
# Simulate by requesting cancel from another thread mid-batch.

def test_cancel_from_other_thread_stops_batch(ctl):
    import threading

    b = ctl._backend_for_tests
    orig = b.type_text
    state = {"n": 0}

    def slow_type(text, gaps, cancelled=None):
        state["n"] += 1
        if state["n"] == 2:
            ctl.request_cancel()  # another "thread" hits stop
        return orig(text, gaps)

    b.type_text = slow_type
    r = ctl.command("batch", {"app": "Finder", "risk": "none", "actions": [
        {"op": "type", "text": "one"},
        {"op": "type", "text": "two"},
        {"op": "type", "text": "three"},
    ]})
    assert r["data"]["status"] == "cancelled"
    assert r["data"]["last_completed"] == 1
    assert state["n"] == 2  # third action never dispatched
