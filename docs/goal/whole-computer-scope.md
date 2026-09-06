# Goal — Part 2: Whole Computer, Not Just Browser

Date: 2026-09-04. Clarifies v0.1 scope: real OS control across apps.

## Scope

Targets: browsers, terminals, editors, design tools, Finder and Explorer, System Settings, native dialogs, menu bar, taskbar, desktop icons.

No WebDriver. No CDP as primary path. Real OS input events only. Browser work uses the same OS clicks and keys as any other app. `osascript` URL nav is a fallback, not the core.

## Verb set v0.1

- `observe --region --app` — MSS region or window grab plus active window name.
- `list_apps`, `list_windows`, `active-window`, `focus_app --app` — no focus steal by default.
- `click --x --y`, `double-click`, `right_click`, `drag --from --to`, `scroll --direction --amount`.
- `move --x --y --seed` — seeded Bezier travel plus exact land.
- `type "text"`, `press enter`, `hotkey cmd,s`.
- `wait --seconds`, `stop`, `doctor`.

All print JSON. All verify after state-changing acts with re-observe or `capture_after`.

## Rules

- Prefer AX tree or window target over raw coords. Coords need a fresh observe first.
- One temp frame only. Overwrite `/tmp/desktop-current.jpg`.
- Destructive acts need `--yes`. Challenge, password, permission, and payment UI stop with `needs_attention`.
- macOS perms belong to the installed binary. Windows uses SendInput plus UI Automation later.

## Not in v0.1

No file API. Files change only through app UI. No daemon. No remote port. No bypass.
