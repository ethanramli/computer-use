"""Tests for the two findings from the re-verification round."""

import json

import pytest

from desktop.controller import Controller
from desktop.mcp_server import McpServer
from tests.test_controller import FakeBackend


@pytest.fixture
def ctl():
    backend = FakeBackend()
    c = Controller(backend=backend, dry_run=False)
    c._backend_for_tests = backend
    return c


# Finding: _click_type bypassed the confirmation gate (_type had it).

def test_click_type_confirmation_gate(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Chrome"
    obs = ctl.command("observe", {"metadata_only": True})
    fid = obs["data"]["frame_id"]
    b.events.clear()  # ignore the observe capture; assert no input events
    r = ctl.command("click_type", {"text": "delete all files", "app": "Chrome",
                                   "x": 10, "y": 10, "frame_id": fid,
                                   "risk": "deletion"})
    assert r["ok"] is False
    assert r["error"]["code"] == "needs_attention"
    assert b.events == []  # click must not have happened either


def test_click_type_confirm_true_allows_execution(ctl):
    b = ctl._backend_for_tests
    b.frontmost = "Chrome"
    obs = ctl.command("observe", {"metadata_only": True})
    fid = obs["data"]["frame_id"]
    r = ctl.command("click_type", {"text": "delete all files", "app": "Chrome",
                                   "x": 10, "y": 10, "frame_id": fid,
                                   "risk": "deletion", "confirm": True})
    assert r["ok"] is True


# Finding: underscore-prefixed internal params must be stripped from ALL
# untrusted input, not just the two known names. Top-level _in_batch
# injection via MCP would waive the hard --app-required refusal.

def test_mcp_top_level_in_batch_injection_dead():
    b = FakeBackend()
    b.frontmost = "Chrome"
    s = McpServer(backend=b, dry_run=False)
    resp = s.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "desktop", "arguments": {
            "command": "type",
            "params": {"text": "hax", "_in_batch": True}}}}))
    env = json.loads(resp)
    data = json.loads(env["result"]["content"][0]["text"])
    assert data["ok"] is False
    assert data["error"]["code"] == "focus_required"
    assert b.events == []


def test_cli_internal_params_stripped(ctl):
    r = ctl.command("type", {"text": "hi", "_in_batch": True})
    # _in_batch stripped -> hard refusal applies even though the flag was set
    assert r["ok"] is False
    assert r["error"]["code"] == "focus_required"
