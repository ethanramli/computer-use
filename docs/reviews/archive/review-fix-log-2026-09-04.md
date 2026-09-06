# Review Fix Log — Round 2 (2026-09-04)

All actionable findings from the Standards review (`.wiki/reviews/standardsreview-2026-09-04.md`) and Spec review, with fixes and regression tests. Suite: 132 passing.

## Fixed

| # | Finding | Fix | Test |
|---|---|---|---|
| S1/S2 (high) | Batch keyboard input bypassed focus verification entirely | `_keyboard_guard`: batch actions without `app` verify current frontmost; refuse if frontmost is loginwindow/empty; batch-level `app` context propagates | `test_batch_keyboard_without_app_verifies_current_focus`, `test_batch_type_app_mismatch_still_refuses`, `test_batch_uses_batch_app_context_when_action_lacks_app` |
| S3 (high) | `verify:"focus"` reported `effect_verified: true` unconditionally | `_effect_check` now performs a real `active_window()` compare (live-verified) | `test_effect_verify.py`, live round-2 smoke |
| S4 (high) | `z` keycode was 26 (the `7` key) | Corrected to 6 (kVK_ANSI_Z) + keycode-uniqueness regression test | `test_review_standards.py` |
| M1 | `needs_confirmation` dead code — no confirmation gate | Wired into `type`: risk-intent text returns `needs_attention` requiring `confirm: true` | verified via controller |
| M2 | `doctor` hardcoded `mss: True` | Real import probe | verified |
| M3 | Batch failure envelope deviated from protocol shape | `protocol.partial()` single-sources ok+error+data | covered |
| M4 | `observe` never returned image bytes on macOS | `capture_region` returns real base64 PNG (live: 1115 bytes, valid magic) | verified live |
| L1 | Key-separator inconsistency (`cmd-s` vs `cmd+s`) | Unified via `safety.key_parts()`; blocklist exact-match preserved (all separator variants verified) | `test_review_standards.py` |
| L2 | Ignored `--app` on observe | Removed from CLI + params | covered |
| Spec: op-name drift | `KNOWN_OPS` accepted `double_click`/`checkpoint` etc., disagreeing with dispatcher; mid-batch failure discarded receipts | `KNOWN_OPS` unified with dispatcher; `protocol.partial` receipts survive mid-batch failure | `test_batch_reports_last_completed_on_cancellation` |
| Spec: `desktop stop` could not cancel real work | Honest stop-file channel: CLI stop writes `/tmp/desktop-stop-flag`; a persistent MCP controller polls it in `_check_cancel` before every action. One-shot CLI with no running controller reports `unsupported` honestly instead of a fake `stopped: true`. Stale signals (>30s TTL) are ignored+cleaned so they cannot poison later commands. | `test_cancel_from_other_thread_stops_batch`, TTL verified |
| Spec: internal-param injection | `_in_batch`/`_batch_app` stripped from untrusted transport params at `command()` entry; `_batch()` re-adds them from trusted batch context; `_batch()` dispatches via `_dispatch` (stripping again per action) | `test_internal_params_stripped_from_batch_actions`, `test_batch_app_context_wins_over_action_internal_params`; dangerous `loginwindow` injection case verified refused |
| Spec: controller/adapter app-matching drift | `_keyboard_guard` now reuses the adapter `_app_matches` (basename + `.app`-strip + casefold) | existing focus tests pass |
| R2-1 (re-verify) | `_click_type` bypassed the confirmation gate | Same `needs_confirmation` / `confirm: true` gate wired before the click+type | `test_review_round2.py::test_click_type_confirmation_gate` |
| R2-2 (re-verify) | Internal params not sanitized — `_in_batch` injectable top-level via MCP/CLI | `_strip_internal` now strips ALL underscore-prefixed params at `command()` entry; verified top-level `_in_batch` injection returns `focus_required` with zero events | `test_review_round2.py::test_mcp_top_level_in_batch_injection_dead`, `test_cli_internal_params_stripped` |

## Kept with rationale

- `cancelled` → exit 0: one-shot stop semantics documented in README; not ambiguous for the agent (the envelope says `cancelled`).
- Catch-all `except Exception` recover text: acceptable for localhost tool; noted in safety docs.

## Dead code removed

- `desktop/capture.py` + `desktop/state.py` legacy parallel path retained but unused by controller — superseded by `frames.py` + `platforms.*.capture_region`. (Left in place for the legacy `bin/desktop` shim; flagged for deletion in next major.)
