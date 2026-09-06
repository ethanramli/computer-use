# Independent FAIL Review — Remediation Log (2026-09-06)

This is the current evidence record for the independent FAIL review. The work
was performed in narrow red/green slices against public controller, CLI, MCP,
package, and native-source seams. Test totals are deliberately not copied into
this document; the final pytest output is the source of truth.

No real mouse or keyboard input, real accounts, credentials, network services,
or destructive actions were used. Windows, X11, and Wayland remain explicit
hardware-blocked adapters rather than unverified implementations.

## Finding-to-fix traceability

| Review finding / root cause | Shared fix | Principal regression evidence |
|---|---|---|
| Individual and batch validation diverged, allowing a bad later action to follow a valid action | `safety.preflight_command` and recursive `preflight_batch` validate the complete immutable copy before action zero | `test_goal_regressions.py`: invalid later op, risk, frame, timing, size, and nested-batch cases |
| Batch input could lack a target app | Action-level or inherited batch-level app is mandatory and rechecked at dispatch | `test_review_fixes.py`, `test_nested_batch_inherits_outer_keyboard_target_before_and_during_dispatch` |
| Batch caller mutation could race preflight | `Controller.command` deep-copies untrusted params before validation and dispatch | `test_batch_copies_nested_input_before_preflight_and_dispatch` |
| Risk and confirmation were heuristic/truthy | Every input requires a canonical explicit risk; consequential categories require literal boolean `True`; text matching is only an additional signal | `test_goal_regressions.py` confirmation/risk matrix, CLI risk regression |
| Modifier aliases/order/separators diverged | One canonical key parser normalizes command/control, option/alt, ctrl, win, and `+`/`-`/`,` ordering | `test_review_standards.py`, `test_final_regressions.py` key-shape cases |
| Secure, payment, permission, and challenge UI could be typed into | Focused-element and coordinate-element metadata are mandatory; empty/unreadable metadata fails closed; secure fields and dialog window subroles stop | `test_goal_regressions.py`, `test_safety.py::test_dialog_window_metadata_fails_closed` |
| macOS used private contract errors and incomplete optional methods | `MacosBackend` implements the platform-neutral `Backend` contract and shared `CapabilityError`, `FocusError`, and `InputCancelled` | `test_platforms.py`, macOS contract regressions in `test_goal_regressions.py` |
| App matching leaked macOS assumptions into the controller | Matching is a backend seam; macOS alone handles basename and `.app` normalization | app matching regressions in `test_goal_regressions.py` |
| macOS could report input success without current Accessibility trust | The native helper checks `AXIsProcessTrusted()` immediately before every input command; Python maps the dedicated exit to `accessibility` | trust regressions in `test_goal_regressions.py` and `test_final_regressions.py` |
| Helper absence and permission absence were conflated | Helper, Accessibility, Screen Recording, and MSS are separate doctor capabilities with specific recovery text | doctor and helper regressions in `test_goal_regressions.py` |
| Frames lacked complete display authorization | One frame guard checks current frame ID, capture region, full display layout, signed origin, scale, rotation, display gaps, and all drag endpoints | `test_frames.py` and frame matrix in `test_goal_regressions.py` |
| A focus switch could leave coordinates apparently fresh | Frames are bound to the observed foreground app; focus is checked again after capture and before every coordinate action | focus/frame regressions in `test_final_regressions.py` |
| Screenshot allocation/output accounting was incomplete | `FrameStore` preflights raw capture, RGB normalization, encoder working copies, PNG, base64, and actual result metadata before capture | `test_frames.py`, `test_observe_budgets_actual_result_metadata_before_capture` |
| Screenshot ownership was split and files accumulated | Adapters return packed RGB; `FrameStore` alone encodes, keeps capacity one, atomically replaces one owner-private stable path, and cleans it on replacement/shutdown | lifecycle and 10,000-replacement tests in `test_frames.py` and `test_goal_regressions.py` |
| MCP duplicated screenshot base64 inside text | MCP removes image bytes from the text envelope and emits one direct `image/png` content block | `test_observe_uses_direct_mcp_image_content_without_text_duplication` |
| Shared `/tmp/desktop-stop-flag` was unsafe and cross-request | The file channel was removed; stop/cancel uses only the live controller's request-scoped event and generation | cancellation suite plus stale-artifact hygiene checks |
| Cancellation could not be read while a command ran | MCP continuously reads stdin while one action executor serializes desktop work; cancel and stop bypass that queue | concurrent run-loop tests in `test_mcp.py` |
| Waits and native loops were not cooperatively interruptible | Deadlines/cancellation flow into waits and adapter primitives; native batches report completed primitive counts and release held input | `test_cancellation.py`, deadline cases in `test_final_regressions.py` |
| Cancelled native drag released at the requested endpoint | The helper releases at the last completed drag point; key dispatch prints a completion receipt | native source regressions in `test_final_regressions.py`; strict C compilation |
| Backend failures after dispatch erased uncertainty | Pointer, keyboard, scroll, drag, and type paths return partial/unknown receipts without echoing typed text; completed click/type prefixes remain visible | receipt regressions in `test_final_regressions.py` and `test_goal_regressions.py` |
| Post-input verification could claim effects or erase dispatch on probe failure | Text verification proves exactly one insertion; key effects remain null; focus verification proves only focus; probe errors leave successful dispatch unverified | `test_effect_verify.py` |
| Native default timing still incurred shaped-path delay | Native move dispatches one exact target point and native typing uses zero gaps; human/compatibility pacing remains explicit | timing regressions in `test_final_regressions.py` and `test_timing.py` |
| MCP limits counted characters, accepted malformed structures/constants, and could run id-less calls | UTF-8 bytes are bounded; request/command params, IDs, methods, and JSON constants are structurally checked; notifications do not execute tools | adversarial cases in `test_mcp.py` and `test_final_regressions.py` |
| CLI parse errors and global-flag placement were inconsistent | The parser emits one JSON failure envelope; global mode flags are normalized before `--`, while literals after `--` remain text | `test_cli.py` and CLI regressions in `test_final_regressions.py` |
| One-shot coordinate examples implied frame state survived processes | Executed coordinate actions and path observations are refused by the one-shot CLI; persistent MCP is the documented session interface | one-shot contradiction tests in `test_cli.py` |
| Clean packages could omit `cghelper` or expose broken entry points | The macOS wheel builds a universal helper from `native/cghelper.c`; an exact clean stage is built, installed into a fresh venv, and probes both entry points and helper | `test_packaging.py` |
| Repository mixed implementation, wiki, binaries, and generated output | Runtime code, native sources, tests, agent skills, tools, benchmarks, current docs, and dated archives now have separate top-level categories; generated binaries/results are ignored | package-stage test, artifact scans, and final `git add -n -A` inspection |

## Final verification record

Final three-run suite, compile, protocol smoke, package-stage, artifact, and
three-review results are appended only after those gates complete. Until then,
this log is remediation evidence, not a handoff verdict.
