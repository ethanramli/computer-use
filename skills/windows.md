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
