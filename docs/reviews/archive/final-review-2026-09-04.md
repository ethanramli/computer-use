# Final Dual-Axis Review — computer-automation (2026-09-04, pre-handoff)

Scope: `.codebase/` against AGENTS.md (Standards axis) and README.md promises
(Spec axis). Suite: **137 passed** (1.11s). Prior rounds: standards-review +
round-2 fix log; all fixes were re-verified in source, not just via tests.

## Verdict

**Handoff-ready.** No high-severity findings. Both previously-flagged safety
defects are genuinely fixed in code, and every README spec promise traced to
an implementation and a test.

## Standards axis (AGENTS.md)

- **Batch focus guard** — `_keyboard_guard` (controller.py ~339) no longer
  bypasses on `_in_batch`: batch actions without `app` verify the current
  frontmost and refuse loginwindow/empty; batch-level `app` context is set
  only by `_batch()` (trusted path). ✔
- **`verify:"focus"` is a real re-check** — `_effect_check` re-queries
  `active_window()` and reports honestly; failure yields
  `effect_verified: false`, no unconditional true. ✔ (live-verified in
  round-2 smoke log)
- **`z` keycode** — `macos.py` has `"z": 6` (kVK_ANSI_Z). Residual "duplicate
  value" hits in KEYCODES are legitimate aliases (return/enter, escape/esc,
  delete/backspace). ✔
- **Confirmation gates wired** — `needs_confirmation` gates `_type` and
  `_click_type` with `confirm: true`; challenge text still hard-stops. ✔
- **Doctor honest** — real `import mss` probe; `trusted()` probed with error
  capture. ✔
- **Stop channel** — stop-file (`/tmp/desktop-stop-flag`, 30s TTL, consumed
  one-shot, stale signals cleaned) polled in `_check_cancel` and the `wait`
  loop; CLI one-shot reports honestly when no controller runs. ✔
- **Internal-param injection dead** — `_strip_internal` removes ALL
  underscore-prefixed keys at `command()` entry; `_batch()` re-adds trusted
  context. ✔
- **Envelope contract** — `protocol.partial()` single-sources the
  ok+error+data batch shape; receipts survive mid-batch failure. ✔
- Clean: platform-neutral core, no app-specific branches, capacity-one frame
  store, blocked combos, no network (stdio only), KNOWN_OPS exactly matches
  the dispatcher, key-separator normalization unified via `key_parts()`.
- Kept-with-rationale (unchanged): `cancelled` → exit 0; catch-all exec
  message. Minor, documented drift only.

## Spec axis (README promises)

- Dry-run default, stale_frame on fresh `frame_id` requirement, focus_failed
  with zero events, blocked combos, `needs_attention` for consequential text,
  emergency stop — all present and contract-tested. ✔
- `observe` returns real base64 PNG (`macos.py` ~357) plus metadata-only
  mode. ✔
- Exit-code table in README matches `EXIT_CODES` and cli.py header. ✔
- `unsupported` capability honesty for Windows/Linux maintained. ✔
- Benchmarks: `benchmark_results.json` valid for policy-layer cells; round-2
  note that focus re-check adds cost only under `verify=focus`. ✔

## Handoff notes (non-blocking)

1. `desktop/capture.py` + `desktop/state.py` are dead legacy shims — flagged
   in the fix log for deletion next major; do it first thing post-handoff.
2. `_effect_check` focus compare uses casefold equality rather than
   `_app_matches`; acceptable (post-event report, not a gate) but worth
   unifying if it ever becomes a guard.
3. `batch` deadline cap (600s) is enforced but not mentioned in README —
   one line to add.
4. Windows/X11/Wayland remain capability-honest stubs; unblock requirements
   are recorded in `.wiki/architecture/traceability.md`.
