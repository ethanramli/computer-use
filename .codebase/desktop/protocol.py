"""JSON protocol helpers. Small and explicit."""

from typing import Any


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, recover: str = "") -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if recover:
        err["recover"] = recover
    return {"ok": False, "error": err}
