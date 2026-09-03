# Protocol — Part 2: OS-Level Verb Table

Status: replaces part-1 command list. OS-level only. No browser driver.

## Verbs

```bash
desktop observe [--region x,y,w,h] [--app NAME]
desktop list_apps
desktop list_windows [--app NAME]
desktop active-window
desktop focus_app --app NAME
desktop move --x 640 --y 420 [--seed 7]
desktop click --x 640 --y 420
desktop double-click --x 640 --y 420
desktop right_click --x 640 --y 420
desktop drag --from x,y --to x,y
desktop scroll --direction down --amount 3
desktop type "hello"
desktop press enter
desktop hotkey cmd,s
desktop wait --seconds 1
desktop doctor
desktop stop
```

## Exit codes

- 0 ok.
- 2 bad arg. Prints `{ok:false, error:{code:bad_arg, message, recover}}`.
- 3 needs_attention. Challenge, password, permission, or payment UI. Stop and ask.
- 4 blocked. Destructive without `--yes` or hard-blocked combo.

## JSON

Every command prints one JSON object. `observe` includes transient `image`, `screen`, `active_window`. `move` includes `points` count plus final `x,y`. Errors carry `code`, `message`, `recover`.
