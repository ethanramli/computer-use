# Protocol — Part 1: CLI and JSON

Status: proposed. No code implements this yet. Source: `README.md`.

## Commands

```bash
desktop observe
desktop click --x 640 --y 420
desktop double-click --x 640 --y 420
desktop type "hello"
desktop press enter
desktop hotkey command,s
desktop scroll --amount -5
desktop active-window
desktop stop
```

## Rules

- Every command returns structured JSON where practical.
- `observe` returns a transient image path plus metadata:

```json
{
  "image": "/tmp/desktop-current.jpg",
  "screen": {"width": 1920, "height": 1080},
  "active_window": "TextEdit"
}
```

- Keep only the current frame. Overwrite or discard old frames.
- Public commands need help text and predictable exit codes.
- Errors explain what failed and how an agent recovers.

## Open

- Exact JSON error shape not decided.
- Exit code table not decided.
