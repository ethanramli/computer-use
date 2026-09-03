# Protocol — Part 3: Execution Codes

Status: amends part-2. Live since 2026-09-04.

## Modes

Dry-run is default. Nothing moves. Add `--execute` to act on the OS.

## Exit codes

- 0 ok. Dry-run plans and executed actions both return 0.
- 2 bad arg.
- 3 needs_attention. Challenge, password, permission, or payment text.
- 4 blocked or unimplemented. Blocked key combos fail here. Window verbs (`list_apps`, `list_windows`, `active-window`, `focus_app`) fail here with code `unimplemented` until built. They never return fake ok.
- 5 exec_failed. The helper failed. Recover hint names the Accessibility grant.

## Doctor shape

```json
{"ok": true, "data": {"platform": "Darwin", "helper": true, "trusted": false, "mss": true}}
```
