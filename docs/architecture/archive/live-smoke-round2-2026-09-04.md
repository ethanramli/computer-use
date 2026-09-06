# Live Smoke Log — Round 2 (post-review-fixes), 2026-09-04

Accessibility trust: `trusted=1`. Fresh-shell venv install re-verified after
the Standards/Spec review fixes (132 tests).

## Round-2 environment finding (2026-09-04, post-fix)

Screen Recording permission was revoked mid-session: MSS began reporting a
0x0 virtual monitor. `MacosBackend.screen_size()` now raises an honest
`CapabilityError` ("display reports 0x0 … Screen Recording permission")
instead of returning fake dimensions; the live test accepts either a real
size or the honest capability error. Input events (move/click/type) still
work — Accessibility trust is separate from Screen Recording.

## Verified live this round

1. `type --app TextEdit --timing native` (9 chars) via installed CLI shape —
   chars landed (executed: true). Document closed unsaved after.
2. `verify=focus` live: `type` and `press` with post-event foreground
   re-check both returned `effect_verified: true` — the review's fake-true
   bug is fixed against the real OS, not just in unit tests.
3. Fresh-shell install: `pip install .` → `desktop doctor`, `observe
   --metadata-only`, `batch` dry-run, `computer-mcp` initialize+tools/list —
   all pass. Venv removed after.
4. Benchmark harness unchanged; `benchmark_results.json` still valid for the
   policy-layer cells (no controller hot-path changes affect timings; the
   focus re-check adds one `active_window()` call only under `verify=focus`).

## Review-fix verification (unit + live)

- Batch focus bypass: closed (batch-level app context + current-focus check;
  refuse when nothing verified). 3 unit tests.
- Fake verify=focus: closed (real active_window compare; live-verified).
- z keycode: closed (6 = kVK_ANSI_Z; uniqueness regression test).
- Dead confirmation gate: wired (`needs_attention` until `confirm: true`).
- doctor mss probe: real import check.
- Batch envelope: `protocol.partial()` single-sourced.
- In-memory observe: macOS returns real base64 PNG (1115 bytes live, valid
  PNG magic).
- Key separators: +, -, , unified via `key_parts()`; blocklist still exact.

## Status

All actionable Standards findings fixed. Spec findings re-verified and fixed.
Remaining blocker for goal completion: Windows/X11/Wayland live hosts
(documented capability-honest `unsupported`), per traceability rows 24-25.
