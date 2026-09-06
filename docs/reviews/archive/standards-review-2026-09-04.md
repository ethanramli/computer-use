# Independent Standards Review — computer-automation (2026-09-04)

Reviewer scope: `.codebase/` (controller, adapters, protocol, safety, tests) against `AGENTS.md` (core principles, performance, safety, architecture, quality bar). All 119 tests pass (1.06s).

## Verdict

**Largely compliant.** The controller is platform-neutral, model-free, dry-run-by-default, has a real emergency stop, a capacity-one frame store, whole-batch pre-validation, and honest receipts ("executed events cannot be undone"). Two genuine safety/behavior defects and several standards deviations are listed below, in priority order.

## High priority

1. **Batch bypasses mandatory keyboard focus check** — `controller.py` `_keyboard_guard` skips the `--app`-required error when `p.get("_in_batch")` (line ~293), and a batched `type/press/hotkey` action with no `"app"` key gets **no focus verification at all**. AGENTS.md: "never skip required focus checks before typing". Fix: batch keyboard actions must either carry `app` or inherit a batch-level `app` that is verified before the first keyboard action.

2. **`verify: "focus"` always reports `effect_verified: true`** — `controller.py` `_effect_check` wraps `out["effect_verified"] = True` in a try/except that cannot fail. It performs no re-check. This violates the honesty/verification principles (claims verification without verifying). The `_keys_impl` path does a real re-check; `_type` does not. Fix: re-run `backend.active_window()`/focus compare, same as `_keys_impl`.

3. **Wrong keycode for `z`** — `platforms/macos.py` KEYCODES has `"z": 26` (26 is the `7` key; kVK_ANSI_Z = 6), so `press z`/`hotkey ...,z` posts `7`. Duplicate mapping confirmed against the digit table in the same dict. Add a regression test asserting KEYCODES values are unique.

## Medium

4. **Risk-intent confirmation gate is dead code** — `safety.needs_confirmation` / RISK_HINTS ("send", "purchase", "delete"…) is never called by controller, CLI, or MCP. AGENTS.md requires confirmation gates for purchases/messages/publishing. Either wire it (return `needs_attention` requiring an explicit `confirm: true` param) or delete it; unused safety code is worse than none because it implies coverage that doesn't exist.

5. **`doctor` hardcodes `{"mss": True}`** — `controller.py` `_doctor` asserts mss availability without probing. Dishonest diagnostics. Probe the import or drop the key.

6. **Batch envelope violates the protocol shape** — `_batch` failure returns `{"ok": false, "error": …, "data": …}`; `protocol.fail()` envelopes carry no `data` sibling, and `cli.out`/MCP consumers assume the standard shape. Define the mixed envelope in `protocol.py` so the contract is single-sourced.

7. **`observe` never returns image bytes on macOS** — `capture_region` returns `b64: None`, so `image_b64` is always `""`; only `--to-file` (path_mode) yields a usable image. README promises "in-memory screenshots and direct image results" as the preferred path. Either base64-encode the PNG (bounded by the frame limit) or fix README.

## Low / polish

8. **`cancelled` maps to exit code 0** in `EXIT_CODES` — debatable; stop semantics ("one-shot") are documented, but an agent polling exit codes cannot distinguish "stopped cleanly" from "my work was cancelled". Consider 4 or a dedicated code.
9. **Key separator inconsistency** — `is_blocked_keys` normalizes `+`/`-`; `validate_keys` only normalizes `+` and `,`, so `cmd-s` fails validation while `cmd+s` is checked against the blocklist. Unify.
10. **`observe` accepts `--app` but ignores it** (cli → params → unused). Remove or document.
11. **Catch-all `except Exception` in `command()`** recovers with "grant OS permissions…" which may mislead for unrelated bugs; consider a distinct `internal` code with honest message.
12. **Broad excepts in mcp `handle_line`** truncate error strings to 500 chars — fine, but errors can leak local paths in `message`; acceptable for a localhost tool, worth a note in the safety docs.

## Standards that pass cleanly

- Architecture: `desktop/` controller+adapters, `skills/` instructions-only, tests cover protocol/safety/batching; no app-specific branches (grep-verified: only generic `open`/`activate`).
- Frame discipline: capacity-one `FrameStore`, geometry-verified freshness, `FrameTooLarge` backpressure, one temp file max in path mode.
- Stop control: `desktop stop` works even if backend init fails (cli.py), `notifications/cancelled` wired in MCP; `wait` polls cancellation.
- Input validation: coordinates (bool-safe), regions, batch pre-validated whole, blocked combos (cmd+shift+q, win+l, ctrl+alt+del, alt+f4), challenge-text gate before any input.
- No network, no model calls, no persistence of frames beyond the single current one.
- Exit codes and JSON envelopes documented and consistent in CLI + MCP tool description.
