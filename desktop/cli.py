"""desktop CLI. Thin adapter over the Controller. JSON out, stable exit codes.

Exit codes: 0 ok, 2 bad_arg, 3 needs_attention/focus_required, 4
blocked/unsupported, 5 exec/focus/stale-frame failures.
"""

import argparse
import json
import os
import sys

from . import protocol
from ._version import __version__
from .controller import EXIT_CODES, Controller
from .platforms import get_backend


def _version_string() -> str:
    return f"%(prog)s {__version__}"


class CliUsageError(ValueError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CliUsageError(message)


def _fake_backend():
    """Test double used by the contract test suite (DESKTOP_FAKE_BACKEND=1)."""
    from tests.test_controller import FakeBackend

    return FakeBackend()


def build_controller(execute: bool) -> Controller:
    if os.environ.get("DESKTOP_FAKE_BACKEND") == "1":
        backend = _fake_backend()
    else:
        backend = get_backend()
    return Controller(backend=backend, dry_run=not execute)


def out(envelope: dict) -> int:
    print(json.dumps(envelope))
    code = 0
    if not envelope.get("ok", False):
        code = EXIT_CODES.get(envelope.get("error", {}).get("code", ""), 5)
    return code


# -- per-command argparse glue -------------------------------------------------

def p_observe(sub):
    o = sub.add_parser("observe", help="capture the screen or a region")
    o.add_argument("--region", default="", help="x,y,w,h")
    o.add_argument("--metadata-only", action="store_true")
    o.add_argument("--to-file", action="store_true",
                   help="write the one current-frame temp file and return its path")


def p_move(sub):
    m = sub.add_parser("move", help="move the cursor along a seeded path")
    m.add_argument("--x", type=int, required=True)
    m.add_argument("--y", type=int, required=True)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--timing", default="native",
                   choices=["human", "compatibility", "native"],
                   help="cursor always uses Bezier+Fitts pacing; retained for compatibility")
    _add_safety(m)


def _add_timing(parser):
    parser.add_argument("--timing", default="native",
                        choices=["human", "compatibility", "native"],
                        help="human=measured typing gaps, native=immediate")


def _add_safety(parser):
    parser.add_argument(
        "--risk",
        default=None,
        choices=[
            "none", "deletion", "purchase", "message", "publishing",
            "permission", "account_security",
        ],
        help="required input-intent classification; consequential values require --confirm",
    )
    parser.add_argument("--confirm", action="store_true",
                        help="fresh confirmation for consequential input")


def p_click(sub, name, help_text):
    c = sub.add_parser(name, help=help_text)
    c.add_argument("--x", type=int, required=True)
    c.add_argument("--y", type=int, required=True)
    c.add_argument("--frame-id", dest="frame_id", default="",
                   help="frame_id from a fresh observe (required on execute)")
    _add_safety(c)


def p_keys(sub, name, help_text):
    k = sub.add_parser(name, help=help_text)
    k.add_argument("keys", help="e.g. enter | cmd,s | ctrl+alt+t")
    k.add_argument("--app", default="", help="focus and verify this app first")
    _add_safety(k)


def p_type(sub, name, help_text, required_app):
    t = sub.add_parser(name, help=help_text)
    t.add_argument("text")
    if required_app:
        t.add_argument("--app", required=True,
                       help="focus and verify this app before input")
    else:
        t.add_argument("--app", default="", help="focus and verify this app first")
    if name == "click_type":
        t.add_argument("--x", type=int, required=True)
        t.add_argument("--y", type=int, required=True)
        t.add_argument("--frame-id", dest="frame_id", default="")
    _add_safety(t)
    return t


def p_drag(sub):
    d = sub.add_parser("drag", help="drag from one point to another")
    d.add_argument("--from", dest="frm", required=True, help="x,y")
    d.add_argument("--to", required=True, help="x,y")
    d.add_argument("--frame-id", dest="frame_id", default="")
    _add_safety(d)


def build_parser() -> argparse.ArgumentParser:
    p = JsonArgumentParser(
        prog="desktop",
        description="OS-level desktop control. Real OS input only. "
                    "Dry-run is the default; pass --execute to act.",
    )
    p.add_argument("--version", action="version", version=_version_string())
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true",
                      help="actually move the cursor and post input "
                           "(requires OS permission grants)")
    mode.add_argument("--dry-run", action="store_true",
                      help="show the plan without executing (default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_observe(sub)
    sub.add_parser("list_apps", help="list running applications")
    lw = sub.add_parser("list_windows", help="list windows of one app")
    lw.add_argument("--app", default="")
    sub.add_parser("active-window", help="print the focused application")
    f = sub.add_parser("focus_app", help="bring an app to the foreground and verify")
    f.add_argument("--app", required=True)
    p_move(sub)
    p_click(sub, "click", "click the left button at x,y")
    p_click(sub, "double-click", "double-click the left button at x,y")
    p_click(sub, "right_click", "click the right button at x,y")
    p_drag(sub)
    s = sub.add_parser("scroll", help="scroll the wheel")
    s.add_argument("--direction", default="down", choices=["up", "down", "left", "right"])
    s.add_argument("--amount", type=int, default=3)
    _add_safety(s)
    t = p_type(sub, "type", "type text into the verified app", required_app=False)
    _add_timing(t)
    ct = p_type(sub, "click_type", "click a control then type into it",
                required_app=True)
    _add_timing(ct)
    p_keys(sub, "press", "press one key")
    p_keys(sub, "hotkey", "press a key combination")
    w = sub.add_parser("wait", help="wait for UI work to settle")
    w.add_argument("--seconds", type=float, default=1.0)
    ln = sub.add_parser("launch", help="open an app and verify it is foreground")
    ln.add_argument("--app", required=True, help="installed app name or path")
    b = sub.add_parser("batch", help="run validated actions in order with receipts")
    b.add_argument("--json", required=True,
                   help="JSON object: {actions: [...], deadline_ms?: n}")
    sub.add_parser("doctor", help="report platform, permissions, and backend state")
    sub.add_parser("stop", help="cancel any running/batched work (emergency stop)")
    return p


# -- dispatch table: CLI args -> controller params --------------------------------

def to_params(args) -> tuple:
    """Return (command_name, params) from parsed CLI args."""
    c = args.cmd
    if c == "observe":
        return c, {"region": args.region,
                   "metadata_only": args.metadata_only,
                   "path_mode": args.to_file}
    if c == "list_windows":
        return c, {"app": args.app}
    if c == "focus_app":
        return c, {"app": args.app}
    if c == "move":
        return c, {"x": args.x, "y": args.y, "seed": args.seed,
                   "timing": args.timing, "risk": args.risk,
                   "confirm": args.confirm}
    if c in ("click", "double-click", "right_click"):
        return c, {"x": args.x, "y": args.y, "risk": args.risk,
                   "confirm": args.confirm,
                   **({"frame_id": args.frame_id} if args.frame_id else {})}
    if c == "drag":
        try:
            fx, fy = (int(v) for v in args.frm.split(","))
            tx, ty = (int(v) for v in args.to.split(","))
        except ValueError:
            return "__bad_drag__", {}
        return c, {"from_x": fx, "from_y": fy, "to_x": tx, "to_y": ty,
                   "risk": args.risk, "confirm": args.confirm,
                   **({"frame_id": args.frame_id} if args.frame_id else {})}
    if c == "scroll":
        return c, {"direction": args.direction, "amount": args.amount,
                   "risk": args.risk, "confirm": args.confirm}
    if c == "type":
        return c, {"text": args.text, "app": args.app, "timing": args.timing,
                   "risk": args.risk, "confirm": args.confirm}
    if c == "click_type":
        return c, {"text": args.text, "app": args.app, "x": args.x, "y": args.y,
                   "timing": args.timing, "risk": args.risk,
                   "confirm": args.confirm,
                   **({"frame_id": args.frame_id} if args.frame_id else {})}
    if c in ("press", "hotkey"):
        return c, {"keys": args.keys, "app": args.app,
                   "risk": args.risk, "confirm": args.confirm}
    if c == "wait":
        return c, {"seconds": args.seconds}
    if c == "launch":
        return c, {"app": args.app}
    if c == "batch":
        try:
            spec = json.loads(args.json)
        except json.JSONDecodeError as e:
            return "__bad_batch__", {"parse_error": str(e)}
        if not isinstance(spec, dict):
            return "__bad_batch__", {"parse_error": "batch JSON must be an object"}
        return c, spec
    return c, {}


def _normalize_global_flags(argv):
    values = list(sys.argv[1:] if argv is None else argv)
    sentinel = values.index("--") if "--" in values else len(values)
    option_values = values[:sentinel]
    literal_values = values[sentinel:]
    flags = [
        value for value in option_values
        if value in {"--execute", "--dry-run"}
    ]
    rest = [
        value for value in option_values
        if value not in {"--execute", "--dry-run"}
    ] + literal_values
    return flags + rest


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(_normalize_global_flags(argv))
    except CliUsageError as exc:
        return out(protocol.fail(
            "bad_arg", str(exc), "run desktop --help for valid arguments"
        ))
    if args.cmd == "stop":
        return out(protocol.ok({
            "stopped": False,
            "reason": "one-shot CLI has no persistent work to cancel",
            "recover": "send notifications/cancelled with the active requestId "
                       "to the running computer-mcp process",
        }))

    if args.execute and args.cmd in {
        "move", "click", "double-click", "right_click", "drag", "click_type",
    }:
        return out(protocol.fail(
            "unsupported",
            "one-shot CLI coordinate input cannot reuse an observed frame",
            "use one persistent computer-mcp session for observe then coordinate input",
        ))
    if args.execute and args.cmd == "observe" and args.to_file:
        return out(protocol.fail(
            "unsupported",
            "one-shot path mode would expire when the process exits",
            "use observe path_mode in a persistent computer-mcp session",
        ))

    name, params = to_params(args)
    if name == "__bad_drag__":
        return out(protocol.fail("bad_arg", "drag coords must be x,y",
                                 "e.g. --from 10,20 --to 300,400"))
    if name == "__bad_batch__":
        return out(protocol.fail("bad_arg", f"invalid batch JSON: {params.get('parse_error')}",
                                 "pass a JSON object with an actions list"))
    ctl = build_controller(args.execute)
    try:
        return out(ctl.command(name, params))
    finally:
        ctl.close()


if __name__ == "__main__":
    raise SystemExit(main())
