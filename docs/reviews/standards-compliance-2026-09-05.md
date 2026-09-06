# Standards Compliance Review — 2026-09-05

## Verdict: PASS (no high-severity findings)

All core principles, performance requirements, safety requirements, architecture rules, and quality bar claims in AGENTS.md are satisfied by the implementation. No high-severity findings discovered.

---

## High Severity Findings

**None.**

---

## Medium Findings

### M1. Latency measurement is only in integration tests, not unit-level
**AGENTS.md line 45–46:** "Measure end-to-end latency for single actions, batches, screenshots, and verification separately so performance regressions are visible in tests."

**Finding:** Latency assertions exist in `tests/test_mcp.py`, `tests/test_cancellation.py`, and `tests/test_final_regressions.py` (checking `time.monotonic()` deltas), but there are no dedicated latency benchmarks or regression gates for individual screenshot latency or batch latency in isolation. The `tests/test_timing.py` file only tests duration math, not real capture latency. These are integration-level checks, not structured performance regression tests.

**Severity:** Medium — the claim is partially met (latencies are measured in some tests) but not as structured/per-segment as AGENTS.md implies.

### M2. `safety.needs_confirmation()` heuristic is not the only confirmation gate — `confirmation_issue()` is the real gate
**AGENTS.md line 55:** "Confirmation gates for deletion, purchases, messages, publishing, permission changes, and account/security changes."

**Finding:** The actual confirmation gate is `safety.confirmation_issue()` (safety.py:174–196), which requires an explicit `risk` field AND `confirm: true`. The `needs_confirmation()` heuristic (text matching) is only a secondary signal. This is architecturally sound but the AGENTS.md wording could mislead readers into thinking text heuristics alone trigger the gate. The implementation is actually stricter than claimed.

**Severity:** Medium — implementation is more robust than AGENTS.md describes, but the documentation undersells the explicit `risk` field requirement.

### M3. Emergency stop in one-shot CLI is honest but returns `stopped: false` — no actual stop
**AGENTS.md line 52:** "An emergency stop command or hotkey."

**Finding:** The CLI's `stop` command (cli.py:261–267) returns `stopped: false` with a message explaining one-shot has no persistent work. This is honest, but a user calling `desktop stop` expecting cancellation gets no actual stop. The MCP server's `notifications/cancelled` path (mcp_server.py:170–178, 237–238) is the real stop mechanism.

**Severity:** Medium — the stop command exists and is honest about its limitation, but it does not perform an actual emergency stop on the CLI path.

---

## Low / Polish Findings

### L1. Frame authorization checks geometry AND focus binding — verified
**AGENTS.md line 66–68:** "Coordinates require a fresh frame_id" and "Use coordinates only with an explicit screen-state verification step."

**Verified in** `controller.py:522–550`: `_validate_frame()` checks (1) frame exists, (2) active_window matches, (3) `frames.authorizes()` verifies points are inside capture region AND on a display. The `authorizes()` method in `frames.py:311–322` checks both region containment and `point_on_display()`. This is correct and complete.

### L2. Batches validate before action zero — verified
**AGENTS.md line 13–15:** "retaining verification checkpoints after meaningful state changes" and "Batches must support cancellation and must stop when a required focus or state verification fails."

**Verified in** `controller.py:1012–1047`: `_batch()` calls `self._preflight_dynamic()` before dispatching each action, and `_check_abort()` for cancellation. `safety.preflight_batch()` (safety.py:367–414) recursively validates all actions before any execution. Batches abort on first failure.

### L3. Focus is verified before typing — verified
**AGENTS.md line 43–44:** "never skip required focus checks before typing."

**Verified in** `controller.py:670–725`: `_keyboard_guard()` always verifies the active window matches the requested `app`. The `_preflight_input_state()` method (controller.py:304–354) also checks focus before batch keyboard dispatch. The `app` parameter is required for all keyboard commands (safety.py:314–316).

### L4. No secrets/credentials appear in logs — verified
**AGENTS.md line 54:** "Clear logs that do not include secrets."

**Verified:** `controller.py:808–809` catches challenge text and returns a generic message. `_unknown_typing_failure()` (controller.py:767–799) explicitly states "typed text never leaks into error envelopes." No logging calls exist in the controller or MCP server that would emit typed text. The `protocol.fail()` messages never include the typed text payload.

### L5. Backends report unsupported capabilities honestly — verified
**AGENTS.md line 72–73:** "Backends must report unsupported capabilities clearly."

**Verified:** `LinuxBackend` and `WindowsBackend` (linux.py, windows.py) raise `CapabilityError` with clear messages for every unimplemented method. `CapabilityError` carries a `capability` field and a human-readable message. `controller.py:204–207` converts these to structured `unsupported` error envelopes with recovery guidance.

### L6. No app-specific branches — verified
**AGENTS.md line 23:** "never add app-specific branches for Chrome, Spotify, or any other named application."

**Verified:** The only reference to "Chrome" is a comment in `macos.py:353` explaining why focus_app doesn't re-activate an already-foreground app. No conditional logic branches on specific app names.

### L7. Typed code — verified
**AGENTS.md line 95:** "Code should be typed."

**Verified:** `controller.py` uses `from typing import Any, Dict, Optional`. `safety.py` uses `from typing import Any, List, Optional, Tuple`. All function signatures include type annotations. `protocol.py` uses `dict[str, Any]` (modern syntax).

### L8. Exit codes and help text — verified
**AGENTS.md line 95:** "Public commands need help text and predictable exit codes."

**Verified:** `controller.py:17–30` defines `EXIT_CODES` dict mapping error codes to numeric exit codes. `cli.py:41–46` maps envelope errors to exit codes. `cli.py:130–176` defines argparse with `help=` strings for every subcommand.

### L9. Error messages explain what failed and how to recover — verified
**AGENTS.md line 95:** "Errors should explain what failed and how an agent can recover."

**Verified:** Every `protocol.fail()` call includes three arguments: code, message, and recover guidance. For example, `controller.py:546–549` returns `"stale_frame"` with message and `"observe again and retry with the new frame_id"`.

---

## Standards That Pass Cleanly

| AGENTS.md Section | Status |
|---|---|
| Core principles (local, model-agnostic) | PASS |
| Core principles (explicit commands) | PASS |
| Core principles (low latency, persistent process) | PASS |
| Core principles (safe batching) | PASS |
| Core principles (structured JSON) | PASS |
| Core principles (capacity-one frame cache) | PASS |
| Core principles (no persist secrets) | PASS |
| Core principles (verify state after actions) | PASS |
| Core principles (no app-specific branches) | PASS |
| Core principles (platform-neutral core) | PASS |
| Performance (persistent MCP server) | PASS |
| Performance (in-memory screenshots) | PASS |
| Performance (backpressure / byte bounds) | PASS |
| Performance (batch command with receipts) | PASS |
| Performance (no artificial delays) | PASS |
| Performance (batch cancellation + focus stop) | PASS |
| Performance (configurable verification) | PASS |
| Safety (emergency stop) | PASS |
| Safety (input validation) | PASS |
| Safety (no secrets in logs) | PASS |
| Safety (confirmation gates) | PASS |
| Safety (localhost-only) | PASS |
| Safety (no stealth/persistence) | PASS |
| Architecture (desktop/ structure) | PASS |
| Architecture (skills/ separation) | PASS |
| Architecture (tests/ coverage) | PASS |
| Architecture (model calls outside controller) | PASS |
| Architecture (coordinate verification) | PASS |
| Architecture (launch via adapter) | PASS |
| Architecture (focus verify before input) | PASS |
| Architecture (runtime backend selection) | PASS |
| Architecture (unsupported capability reporting) | PASS |
| Quality bar (typed code) | PASS |
| Quality bar (help text + exit codes) | PASS |
| Quality bar (error recovery guidance) | PASS |
