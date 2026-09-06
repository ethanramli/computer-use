# Architecture

Design decisions, live-test evidence, and verification records for the controller, platform adapters, and native execution layer.

## Decision records

- `archive/layout.md` — Initial layout and controller surface.
- `archive/os-layout.md` — OS-level directory structure and platform-neutral rules.
- `archive/native-execution.md` — Native C execution layer (`cghelper`) and why it was needed.
- `archive/trust-gate.md` — Trust gate finding: mouse moves land, clicks/keys require Accessibility.
- `archive/controller-mcp-frames.md` — Controller, MCP server, frame store, safety, timing, and CLI.

## Live-test evidence

- `archive/live-smoke-2026-09-04.md` — Round 1 macOS live smoke test results.
- `archive/live-smoke-round2-2026-09-04.md` — Round 2 post-review-fix verification.
- `archive/live-input-status.md` — Honest status of input delivery (mouse verified, keyboard unproven).

## Measurement

- `receipt-fixture.md` — Dispatch-vs-effect benchmark using the receipt-window fixture.

## Verification

- `traceability.md` — Full requirement-to-implementation traceability matrix (137 tests).
