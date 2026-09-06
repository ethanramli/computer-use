"""MCP stdio server tests. Public seam: McpServer.handle_line(line) -> response.

Covers JSON-RPC initialize, tools/list, tools/call, cancellation notification,
EOF shutdown, bounded payload rejection, and no outbound sockets.
"""

import json
import queue
import threading
import time

import pytest

from tests.test_controller import FakeBackend
from desktop.mcp_server import McpServer, MAX_MESSAGE_BYTES


def make_server(dry_run=True):
    return McpServer(backend=FakeBackend(), dry_run=dry_run)


def rpc(server, **req):
    line = json.dumps(req)
    resp = server.handle_line(line)
    return json.loads(resp) if resp else None


def test_initialize_handshake():
    s = make_server()
    r = rpc(s, jsonrpc="2.0", id=1, method="initialize",
            params={"protocolVersion": "2026-07-28",
                    "capabilities": {}, "clientInfo": {"name": "test"}})
    assert r["id"] == 1
    assert r["result"]["protocolVersion"] == "2026-07-28"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_exposes_desktop_commands():
    s = make_server()
    rpc(s, jsonrpc="2.0", id=1, method="initialize", params={})
    r = rpc(s, jsonrpc="2.0", id=2, method="tools/list", params={})
    names = [t["name"] for t in r["result"]["tools"]]
    assert "desktop" in names


def test_tools_call_click_dry_run():
    s = make_server()
    rpc(s, jsonrpc="2.0", id=1, method="initialize", params={})
    r = rpc(s, jsonrpc="2.0", id=2, method="tools/call",
                params={"name": "desktop", "arguments": {"command": "click",
                        "params": {"x": 5, "y": 6, "risk": "none"}}})
    assert r["result"]["isError"] is False
    data = json.loads(r["result"]["content"][0]["text"])
    assert data["data"]["dry_run"] is True


def test_ping():
    s = make_server()
    r = rpc(s, jsonrpc="2.0", id=3, method="ping", params={})
    assert r["result"] == {}


def test_unknown_method_error():
    s = make_server()
    r = rpc(s, jsonrpc="2.0", id=4, method="no/such", params={})
    assert r["error"]["code"] == -32601


def test_malformed_json_returns_parse_error():
    s = make_server()
    resp = s.handle_line("not json")
    r = json.loads(resp)
    assert r["error"]["code"] == -32700


def test_oversized_message_rejected():
    s = make_server()
    resp = s.handle_line(json.dumps({"junk": "x" * (MAX_MESSAGE_BYTES + 1)}))
    r = json.loads(resp)
    assert r["error"]["code"] == -32700 or "too large" in r["error"]["message"]


def test_oversized_utf8_message_uses_encoded_byte_length():
    s = make_server()
    line = json.dumps(
        {"jsonrpc": "2.0", "id": 8, "method": "ping", "padding": "😀" * 1_100_000},
        ensure_ascii=False,
    )

    response = json.loads(s.handle_line(line))

    assert len(line) < MAX_MESSAGE_BYTES
    assert len(line.encode("utf-8")) > MAX_MESSAGE_BYTES
    assert response["error"]["code"] == -32700


@pytest.mark.parametrize("params", [[], "bad", 1, True])
def test_request_params_must_be_an_object(params):
    s = make_server()

    response = rpc(s, jsonrpc="2.0", id=9, method="ping", params=params)

    assert response["error"]["code"] == -32602


@pytest.mark.parametrize("command_params", [[], "bad", 1, True, None])
def test_desktop_command_params_must_be_an_object(command_params):
    s = make_server()

    response = rpc(
        s,
        jsonrpc="2.0",
        id=10,
        method="tools/call",
        params={
            "name": "desktop",
            "arguments": {"command": "wait", "params": command_params},
        },
    )

    assert response["error"]["code"] == -32602


def test_cancellation_notification_returns_none():
    s = make_server()
    resp = s.handle_line(json.dumps({"jsonrpc": "2.0",
                                     "method": "notifications/cancelled",
                                     "params": {"requestId": 1}}))
    assert resp is None


def test_eof_shutdown_clean():
    s = make_server()
    s.shutdown()
    assert s._shutdown is True


def test_live_click_through_mcp():
    s = McpServer(backend=FakeBackend(), dry_run=False)
    rpc(s, jsonrpc="2.0", id=1, method="initialize", params={})
    obs = rpc(s, jsonrpc="2.0", id=2, method="tools/call",
              params={"name": "desktop", "arguments": {"command": "observe",
                      "params": {"metadata_only": True}}})
    fid = json.loads(obs["result"]["content"][0]["text"])["data"]["frame_id"]
    r = rpc(s, jsonrpc="2.0", id=3, method="tools/call",
                params={"name": "desktop", "arguments": {"command": "click",
                        "params": {"x": 10, "y": 20, "frame_id": fid,
                                   "risk": "none"}}})
    data = json.loads(r["result"]["content"][0]["text"])
    assert data["ok"] is True
    assert ("click", 10, 20, "left", False) in s.controller.backend.events


def test_observe_uses_direct_mcp_image_content_without_text_duplication():
    server = McpServer(backend=FakeBackend(), dry_run=False)
    try:
        response = rpc(
            server,
            jsonrpc="2.0",
            id="observe-image",
            method="tools/call",
            params={
                "name": "desktop",
                "arguments": {"command": "observe", "params": {}},
            },
        )
    finally:
        server.controller.close()

    content = response["result"]["content"]
    assert [item["type"] for item in content] == ["text", "image"]
    envelope = json.loads(content[0]["text"])
    assert "image_b64" not in envelope["data"]
    assert content[1]["mimeType"] == "image/png"
    assert content[1]["data"].startswith("iVBOR")


def test_no_outbound_sockets():
    import socket

    created = []
    orig = socket.socket
    # creating a socket in-process would be a violation; prove none is created
    # during a full command cycle
    s = make_server()
    try:
        socket.socket = lambda *a, **k: created.append(1) or orig(*a, **k)
        rpc(s, jsonrpc="2.0", id=1, method="initialize", params={})
        rpc(s, jsonrpc="2.0", id=2, method="tools/call",
            params={"name": "desktop", "arguments": {"command": "observe",
                    "params": {}}})
    finally:
        socket.socket = orig
    assert created == []


class FeedingInput:
    def __init__(self):
        self.items = queue.Queue()

    def send(self, value):
        self.items.put(value + "\n")

    def close(self):
        self.items.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        value = self.items.get(timeout=2)
        if value is None:
            raise StopIteration
        return value


class RecordingOutput:
    def __init__(self):
        self.lines = []
        self.lock = threading.Lock()

    def write(self, value):
        with self.lock:
            self.lines.extend(line for line in value.splitlines() if line)

    def flush(self):
        pass


def request_line(request_id, command, params):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": "desktop",
                "arguments": {"command": command, "params": params},
            },
        }
    )


def test_run_reads_matching_cancellation_while_action_executor_is_busy():
    feed = FeedingInput()
    output = RecordingOutput()
    server = McpServer(
        backend=FakeBackend(), dry_run=False, stdin=feed, stdout=output
    )
    thread = threading.Thread(target=server.run)
    started = time.monotonic()
    thread.start()
    feed.send(request_line("wait-1", "wait", {"seconds": 0.2}))
    time.sleep(0.03)
    feed.send(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "wait-1"},
            }
        )
    )
    feed.close()
    thread.join(timeout=1)

    assert not thread.is_alive()
    responses = [json.loads(line) for line in output.lines]
    envelope = json.loads(responses[0]["result"]["content"][0]["text"])
    assert envelope["error"]["code"] == "cancelled"
    assert time.monotonic() - started < 0.18


def test_run_processes_stop_tool_while_action_executor_is_busy():
    feed = FeedingInput()
    output = RecordingOutput()
    server = McpServer(
        backend=FakeBackend(), dry_run=False, stdin=feed, stdout=output
    )
    thread = threading.Thread(target=server.run)
    started = time.monotonic()
    thread.start()
    feed.send(request_line("wait-stop", "wait", {"seconds": 0.2}))
    time.sleep(0.03)
    feed.send(request_line("stop-1", "stop", {}))
    feed.close()
    thread.join(timeout=1)

    assert not thread.is_alive()
    responses = {json.loads(line)["id"]: json.loads(line) for line in output.lines}
    wait_envelope = json.loads(
        responses["wait-stop"]["result"]["content"][0]["text"]
    )
    stop_envelope = json.loads(
        responses["stop-1"]["result"]["content"][0]["text"]
    )
    assert wait_envelope["error"]["code"] == "cancelled"
    assert stop_envelope["data"]["stopped"] is True
    assert time.monotonic() - started < 0.18


def test_run_ignores_mismatched_cancellation_for_active_request():
    feed = FeedingInput()
    output = RecordingOutput()
    server = McpServer(
        backend=FakeBackend(), dry_run=False, stdin=feed, stdout=output
    )
    thread = threading.Thread(target=server.run)
    thread.start()
    feed.send(request_line("wait-2", "wait", {"seconds": 0.08}))
    time.sleep(0.02)
    feed.send(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "someone-else"},
            }
        )
    )
    feed.close()
    thread.join(timeout=1)

    response = json.loads(output.lines[0])
    envelope = json.loads(response["result"]["content"][0]["text"])
    assert envelope["ok"] is True
