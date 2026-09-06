# Windows and apps

Instructions for agents.

## Steps

- Active app: call `active-window`.
- Bring an app forward without launching again: call `focus_app` with `app`.
- Open an app and verify it is foreground: call `launch` with `app`.
- App/window listings: call `list_apps` or `list_windows` with optional `app`.
  (return `unsupported` with a structured error where the platform backend
  does not implement them — that is honest, not an outage).

## Rules

- Launch always brings the app foreground by design; that is the one
  sanctioned focus change.
- `focus_app` does NOT re-activate an already-foreground app, so the user's
  focused control (address bar, text field) is preserved.
- If focus cannot be verified, commands refuse to act. Never try to type
  into "whatever is focused" — the user may be in another app.

## Knowing whether it opened

- `launch`/`focus_app` return `active_window` plus `effect_verified`.
  True means the requested app is frontmost — then `observe` to see it.
  False (or `focus_failed`) means it did not open: stop, observe, retry.
  Never type after a failed verification.
- `list_apps` shows running apps; `active-window` shows the frontmost one.
  `observe` with `metadata_only: true` returns both `frame_id` and
  `active_window` with no image — the cheap check before every input.

## System UI (Spotlight etc.)

- System overlays are opened with normal keys, not `launch`. Recipe:
  `hotkey` with `keys: "cmd,space"` and `app` set to the current
  `active-window` value, then call `active-window` again and use THAT
  value as `app` for the following `type`/`press`.
- Never issue `move` to explore. Only move/click to coordinates read from
  a fresh `observe`. A wandering cursor means the plan has no target:
  stop and observe instead of moving.
