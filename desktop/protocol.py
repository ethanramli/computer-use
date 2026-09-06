"""JSON protocol helpers. Small and explicit."""

from typing import Any


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, recover: str = "") -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if recover:
        err["recover"] = recover
    return {"ok": False, "error": err}


def partial(data: dict[str, Any], code: str, message: str,
            recover: str = "") -> dict[str, Any]:
    """Failure envelope that also carries partial data (batch receipts).

    Standard shape for interrupted batches: ok=false with error, plus data
    holding status/last_completed/receipts. Executed events cannot be
    undone; receipts report exactly what ran.
    """
    env = fail(code, message, recover)
    env["data"] = data
    return env
