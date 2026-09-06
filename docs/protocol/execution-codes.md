# Protocol — Part 3: Execution Codes

Status: amends part-2. Live since 2026-09-04.

## Modes

Dry-run is default. Nothing moves. Add `--execute` to act on the OS.

## Exit codes

- 0 ok. Dry-run plans and executed actions both return 0.
- 2 bad arg.
- 3 needs_attention. Challenge, password, permission, or payment text.
- 4 blocked or unimplemented. Blocked key combos fail here. `list_apps` and `list_windows` remain unimplemented and never return fake data.
- 5 exec_failed. The helper failed. Recover hint names the Accessibility grant.

`active-window` and `focus_app` are live on macOS. Executed keyboard commands
require `--app`; focus mismatch stops before input. `click_type` combines a
visually verified click and text delivery in one native operation.

## Doctor shape

```json
{"ok": true, "data": {"platform": "Darwin", "helper": true, "trusted": false, "mss": true}}
```
