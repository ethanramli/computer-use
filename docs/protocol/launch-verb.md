# Protocol — Part 4: Launch Verb

Status: shipped 2026-09-04. Foreground by design.

## Verb

```bash
desktop launch --app "Google Chrome"   # dry-run plans, --execute opens it
```

Routes to generic macOS application activation and verifies the focused
application before returning. `open -a` remains a fallback when activation
cannot initially resolve the app. Other platforms remain adapter work.

## Rule correction

Goal part-2 said no focus steal by default. Launch is the exception. Opening an app means bringing it forward, like Playwright opening a browser. Input verbs keep backgroundability as a later rung. Launch never hides.

## Verified

- `launch --app "Google Chrome"` opened Chrome frontmost. Confirmed by screenshot.
- `launch --app Spotify` on a machine without Spotify fails exit 5 with `Unable to find application`. No silent ok.
- Follow-up live test: a transparent automation overlay appeared above Chrome.
  `NSWorkspace.frontmostApplication` correctly reported Chrome while raw window
  ordering reported the overlay; input verification now uses the former.
