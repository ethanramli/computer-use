# Architecture — Part 5: Controller, MCP, Frames, Timing

Date: 2026-09-04. First new decision round after the research report in
`wiki.md`. Supersedes nothing; refines parts 1-4. Code matches this part.

## Shipped

0. **Effect verification** (`verify=focus|effect` on type/press/hotkey).
   `focus` re-checks the foreground app after the event; `effect` reads the
   focused element's value where the OS exposes it and reports
   `effect_verified` honestly (true/false, or no claim when the OS gives no
   value). Dispatch already happened, so this never fails the command — it
   only adds truthful reporting. Addresses the dispatch-vs-effect gap found
   in live smoke (see `live-smoke-2026-09-04.md`).

1. **Platform-neutral controller** (`desktop/controller.py`). One `Controller`
   owns one backend adapter, one capacity-one frame store, one cancellation
   flag. All commands enter through `command(name, params)` and return the
   protocol envelope. Policy (validation, focus verification, frame
   freshness, cancellation, receipts) lives here; OS work lives in adapters.
2. **MCP stdio server** (`desktop/mcp_server.py`). Newline-delimited
   JSON-RPC, one persistent process. Methods: initialize, ping, tools/list,
   tools/call (`desktop` tool with `command` + `params`),
   notifications/cancelled (out-of-band cancellation). Stdio only: no
   sockets, no daemon, localhost by construction. Entry point
   `computer-mcp`.
3. **Frame store** (`desktop/frames.py`). Capacity one. A new frame
   replaces and releases the old raw/encoded data. Byte limit with
   `too_large` rejection. Optional path mode keeps exactly one temp file
   (older file unlinked on replace). `fresh(frame_id, geometry)` gates all
   coordinate input; geometry mismatch or stale id returns `stale_frame`
   and zero events.
4. **Safety module** (`desktop/safety.py`). Single source of truth:
   coordinate/region/text/key validation, blocked combos, challenge hints,
   batch validation before the first action (ops whitelist, count ≤ 500,
   per-action gates).
5. **Timing modes** (`desktop/timing.py`). `human` (default; accepted
   Bezier/Fitts + measured gaps), `compatibility` (10 ms fixed),
   `native` (zero artificial delay). Invalid mode = `bad_arg`. Negative
   durations clamp to 0. Trailing sleeps after the final event are removed
   from cghelper (type, movebatch, scroll, clicktype); gaps apply between
   events only.
6. **CLI** (`desktop/cli.py`). Thin adapter over the controller. All 20
   commands with help text. Dry-run default, `--execute` to act. Exit
   codes: 0 ok, 2 bad_arg, 3 needs_attention/focus_required, 4
   blocked/unsupported, 5 exec/focus/stale_frame failures.
7. **Emergency stop**. `desktop stop` / MCP `notifications/cancelled` set a
   controller flag checked before every primitive and inside waits.
   Batched work reports `last_completed` and per-step receipts; executed
   events are never claimed as rolled back.
8. **Windows/Linux adapters** raise explicit `CapabilityError` for every
   operation. No placeholder success. Same contract tests run against all
   three backends (macOS live, Windows/Linux capability-honest).

## Exit code amendment

Protocol part-3 exit codes stand, plus: `focus_failed`, `stale_frame`, and
`exec_failed` all exit 5; `unsupported` exits 4.

## Verified

- 132 unit/contract/integration tests pass (`python3 -m pytest`).
- Contract tests prove: focus mismatch → zero events; stale frame → zero
  events; cancellation stops before next primitive; held keys released on
  failure; batches validated whole before first action; 10,000 frame
  replacements keep count at 1 with no temp-file accumulation; no socket
  creation during command cycles.
- Benchmark harness (`tests/bench.py`) records UTC timestamps,
  perf_counter_ns raw values, environment, cold vs warm, median/p95/p99,
  failure rates, `model_included: false`.

- `install` also builds `bin/receipt-window` (`csrc/receipt-window.c`) — a
  listen-only CGEventTap fixture that prints JSON receipts for received
  events. It is the macOS measurement vehicle for dispatch-vs-effect
  latency (see `.wiki/architecture/bench-receipt-window.md`). It never
  posts or modifies events.

- The receipts fixture ships in `install` too (see above).

## Open

- Windows SendInput, X11 XTEST, and Wayland portal implementations require
  live OS hosts; adapters are capability-honest until then.
- Persistent native helper (server-mode cghelper) and native AppKit focus
  lookup remain future rungs; one-shot helper cost is measured in the
  research report.
