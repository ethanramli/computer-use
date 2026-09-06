# Computer Automation — Live Smoke Test Log (macOS, 2026-09-04)

Accessibility trust: `trusted=1` confirmed in agent shell (cghelper tap).

## Live results

- `launch --app TextEdit --execute` → TextEdit frontmost, verified by active-window. PASS
- `type --app TextEdit --timing native` (22 chars) → all chars landed in the
  TextEdit document (verified via AppleScript text read). PASS
- cghelper direct `type` with gaps 0/100000/200000 → chars landed within ~1s
  of helper exit. PASS
- cghelper `key` verb → landed (earlier "K" session). PASS (intermittent, see
  focus race below)
- `move` out-and-back with position-read verification. PASS (prior + re-run)
- `active-window`, `observe --metadata-only` through installed CLI shape. PASS
- Focus gate live proof: `type --app NonexistentApp` refused before any event
  with structured error. PASS

## Live finding: focus race (real, documented)

During battery runs the session's frontmost app flipped repeatedly to
`loginwindow` and to Google Chrome without user action. Consequences:

1. Synthetic keyboard events posted while focus flipped were dropped (no
   visible effect anywhere) — the helper returned success because CGEventPost
   is fire-and-forget. This is exactly the documented dispatch-vs-effect gap.
2. One test typed into the user's active Chrome tab because the controller
   verified focus correctly (Chrome WAS frontmost as requested) — test design
   error, not a code bug, but it proves live typing must target a throwaway
   window the agent owns.
3. `click_type` (atomic click+type inside one helper invocation) exists
   precisely to narrow this race; single-shot click-then-type spans two
   processes and is unreliable under focus churn.

## Actions taken

- TextEdit test documents closed without saving.
- Live typing against real user apps is banned in future batteries; the safe
  test fixture (tests/fixtures/safe-click-target.png in a fresh viewer window
  the agent opens) is the required target.
- Cursor parked at a neutral corner after tests.

## Follow-up engineering item

`type`/`press`/`hotkey` effects cannot be verified as delivered because
CGEventPost returns without proof of receipt. The wiki's benchmark plan
already specifies a native event-receipt test window (post → effect_ns).
Implementing that receipt window is the next rung: it converts "helper said
ok" into "the target app actually received the key", and lets the controller
return `effect_verified: true|false` instead of opaque success.
