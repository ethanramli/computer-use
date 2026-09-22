"""MCP stdio server. Newline-delimited JSON-RPC. One persistent process.

Local-only by construction: stdin/stdout only, no sockets created.
"""

import json
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from . import protocol
from ._version import __version__
from .controller import Controller
from .platforms.base import Backend

PROTOCOL_VERSION = "2026-07-28"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024  # 4 MiB input bound; backpressure by rejection

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "desktop",
        "description": (
            "Run a desktop automation command. Real OS input with a visible "
            "Bezier cursor cue before every action. "
            "Verify opens: launch/focus_app return active_window plus "
            "effect_verified (true means the requested app is frontmost). "
            "If effect_verified is false or focus_failed, stop and observe; "
            "never type into the wrong app. Then observe to see the result. "
            "Keys are ONE string, never a list: press takes a single key "
            "('enter'), hotkey takes a combo ('cmd,space', 'cmd,s'). "
            "Keyboard input (type/press/hotkey/click_type) always needs "
            "'app' set to the current active-window value and 'risk' set to "
            "one of none/deletion/purchase/message/publishing/permission/"
            "account_security (consequential ones also need confirm:true). "
            "Coordinate actions (move/click/double-click/right_click/drag/"
            "click_type) need x/y plus a fresh frame_id from observe in THIS "
            "session; stale_frame means observe again. "
            "System UI (Spotlight): hotkey cmd,space with app=current "
            "active-window, then call active-window again and use THAT value "
            "as app for the next type/press. Example open-Terminal flow: "
            "launch Terminal, or hotkey cmd+space, type 'Terminal', press "
            "enter, then observe. "
            "Cheap checks: observe with metadata_only:true returns frame_id "
            "plus active_window with no image; batch observe requires "
            "metadata_only. Use batch final_observe:{image:true} to receive "
            "one final screenshot with its receipts. Never issue move to explore: only move/click to "
            "coordinates read from a fresh observe."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": [
                        "observe", "list_apps", "list_windows",
                        "active-window", "focus_app", "launch", "move",
                        "click", "double-click", "right_click", "drag",
                        "scroll", "type", "click_type", "press", "hotkey",
                        "wait", "batch", "stop", "doctor",
                    ],
                },
                "params": {
                    "type": "object",
                    "description": (
                        "observe: {region:'x,y,w,h', metadata_only, path_mode}. "
                        "launch/focus_app: {app}. "
                        "type: {text, app, risk, timing?, verify?}. "
                        "press: {keys:'enter', app, risk}. "
                        "hotkey: {keys:'cmd,space', app, risk}. "
                        "click/move: {x, y, frame_id, risk}. "
                        "batch: {actions:[{op,...}], app?, risk?, "
                        "final_observe?:{image?:boolean}}."
                    ),
                },
            },
            "required": ["command"],
        },
    }
]


def _reject_non_json_constant(value: str):
    raise ValueError(f"invalid JSON constant: {value}")


def _loads(line: str):
    return json.loads(line, parse_constant=_reject_non_json_constant)


class McpServer:
    """One instance per process. handle_line is the transport seam; run()
    loops over stdin until EOF."""

    def __init__(self, backend: Backend, dry_run: bool = True,
                 stdin=None, stdout=None):
        self.controller = Controller(backend=backend, dry_run=dry_run)
        self._shutdown = False
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stdout = stdout if stdout is not None else sys.stdout

    # -- JSON-RPC -------------------------------------------------------------

    def handle_line(self, line: str) -> Optional[str]:
        """Handle one request line. Returns response line or None (notification)."""
        try:
            message_bytes = len(line.encode("utf-8"))
        except (AttributeError, UnicodeEncodeError):
            return self._error(None, -32700, "parse error")
        if message_bytes > MAX_MESSAGE_BYTES:
            return self._error(None, -32700, "request too large")
        try:
            req = _loads(line)
        except (json.JSONDecodeError, ValueError, RecursionError):
            return self._error(None, -32700, "parse error")
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "invalid request")
        method = req.get("method")
        req_id = req.get("id")
        if "id" in req and (
            isinstance(req_id, bool)
            or (req_id is not None and not isinstance(req_id, (str, int, float)))
        ):
            return self._error(None, -32600, "invalid request id")
        if not isinstance(method, str):
            return self._error(req_id, -32600, "method must be a string")
        if method == "notifications/cancelled":
            params = req.get("params", {})
            if isinstance(params, dict):
                self._on_cancelled(params)
            return None
        if method and method.startswith("notifications/"):
            return None
        if "id" not in req:
            return None
        params = req.get("params", {})
        if not isinstance(params, dict):
            return self._error(req_id, -32602, "params must be an object")
        try:
            result = self._method(method, params, request_id=req_id)
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
        except RpcError as e:
            return self._error(req_id, e.code, e.message)
        except Exception as e:
            return self._error(req_id, -32603, str(e)[:500])

    def _method(self, method: str, params: Dict[str, Any],
                request_id: Any = None) -> Dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "computer-mcp", "version": __version__},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self._tools_call(params, request_id=request_id)
        raise RpcError(-32601, f"method not found: {method}")

    def _tools_call(self, params: Dict[str, Any],
                    request_id: Any = None) -> Dict[str, Any]:
        name = params.get("name")
        if name != "desktop":
            raise RpcError(-32602, f"unknown tool: {name}")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            raise RpcError(-32602, "arguments must be an object")
        if len(
            json.dumps(args, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ) > MAX_MESSAGE_BYTES:
            envelope = protocol.fail(
                "bad_arg",
                f"arguments too large: exceeds {MAX_MESSAGE_BYTES} bytes",
                "split the request or reduce text/payload size")
            return {
                "content": [{"type": "text", "text": json.dumps(envelope)}],
                "isError": True,
            }
        command = args.get("command")
        if not isinstance(command, str) or not command:
            raise RpcError(-32602, "arguments.command is required")
        command_params = args.get("params", {})
        if not isinstance(command_params, dict):
            raise RpcError(-32602, "arguments.params must be an object")
        envelope = self.controller.command(
            command, command_params, request_id=request_id
        )
        image_b64 = None
        text_envelope = envelope
        data = envelope.get("data")
        if isinstance(data, dict) and isinstance(data.get("image_b64"), str):
            image_b64 = data["image_b64"]
            text_envelope = {**envelope, "data": {**data}}
            text_envelope["data"].pop("image_b64")
        content = [
            {"type": "text", "text": json.dumps(text_envelope)}
        ]
        if image_b64 is not None:
            content.append(
                {"type": "image", "data": image_b64, "mimeType": "image/png"}
            )
        return {
            "content": content,
            "isError": not envelope.get("ok", False),
        }

    def _on_cancelled(self, params: Dict[str, Any]) -> None:
        if "requestId" not in params:
            return
        generation = params.get("generation")
        if generation is not None and (
            isinstance(generation, bool) or not isinstance(generation, int)
        ):
            return
        self.controller.request_cancel(params["requestId"], generation=generation)

    # -- transport ---------------------------------------------------------------

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> str:
        return json.dumps({"jsonrpc": "2.0", "id": req_id,
                           "error": {"code": code, "message": message}})

    def shutdown(self) -> None:
        self._shutdown = True
        self.controller.request_cancel()

    @staticmethod
    def _is_cancellation(line: str) -> bool:
        try:
            request = _loads(line)
        except (TypeError, ValueError, RecursionError):
            return False
        return (
            isinstance(request, dict)
            and request.get("jsonrpc") == "2.0"
            and request.get("method") == "notifications/cancelled"
        )

    @staticmethod
    def _is_stop_request(line: str) -> bool:
        try:
            request = _loads(line)
            params = request.get("params", {})
            arguments = params.get("arguments", {})
        except (AttributeError, TypeError, ValueError, RecursionError):
            return False
        return (
            request.get("jsonrpc") == "2.0"
            and request.get("method") == "tools/call"
            and params.get("name") == "desktop"
            and arguments.get("command") == "stop"
        )

    def run(self) -> int:
        """Read newline-JSON requests until EOF. Returns process exit code."""
        output_lock = threading.Lock()

        def emit(future: Future) -> None:
            response = future.result()
            if response is None:
                return
            with output_lock:
                self._stdout.write(response + "\n")
                self._stdout.flush()

        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="desktop-actions"
        ) as executor:
            for line in self._stdin:
                line = line.rstrip("\n")
                if not line:
                    continue
                if self._is_cancellation(line):
                    self.handle_line(line)
                elif self._is_stop_request(line):
                    response = self.handle_line(line)
                    if response is not None:
                        with output_lock:
                            self._stdout.write(response + "\n")
                            self._stdout.flush()
                else:
                    executor.submit(self.handle_line, line).add_done_callback(emit)
                if self._shutdown:
                    break
        self.controller.close()
        return 0


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def main(argv=None) -> int:
    """Entry point for the computer-mcp executable."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        if args == ["--help"] or args == ["-h"]:
            print(
                "computer-mcp: local newline-delimited JSON-RPC/MCP stdio server "
                "over stdin/stdout; send initialize, ping, tools/list, or tools/call"
            )
            return 0
        print("computer-mcp accepts only --help; protocol traffic uses stdio")
        return 2
    from .platforms import get_backend

    backend = get_backend()
    server = McpServer(backend=backend, dry_run=False)
    return server.run()


if __name__ == "__main__":
    raise SystemExit(main())
