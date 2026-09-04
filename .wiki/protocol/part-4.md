# Protocol — Part 4: Launch Verb

Status: shipped 2026-09-04. Foreground by design.

## Verb

```bash
desktop launch --app "Google Chrome"   # dry-run plans, --execute opens it
```

Routes to `open -a` on macOS. Other platforms fail `unimplemented` until their adapters land.

## Rule correction

Goal part-2 said no focus steal by default. Launch is the exception. Opening an app means bringing it forward, like Playwright opening a browser. Input verbs keep backgroundability as a later rung. Launch never hides.

## Verified

- `launch --app "Google Chrome"` opened Chrome frontmost. Confirmed by screenshot.
- `launch --app Spotify` on a machine without Spotify fails exit 5 with `Unable to find application`. No silent ok.
