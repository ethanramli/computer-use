# Typing and keys

Instructions for agents.

## Steps

1. Call `focus_app` with `app: "App Name"`; verify its result.
2. Call `type` with `text`, `app`, and explicit `risk`. A focus mismatch sends
   zero input events and returns `focus_failed`.
3. Use `press` for one key and `hotkey` for a combination; both require `app`
   and `risk`.
4. For `click_type`, first observe in the same persistent controller session,
   then provide `app`, `x`, `y`, its fresh `frame_id`, and `risk`. The
   controller clicks, rechecks focus and secure-field state, then types.

## Rules

- Keyboard input is impossible without an explicit target `app`. That is the safety gate,
  not a limitation to work around.
- Timing: `native` is the no-delay default. Request `human` for measured gaps
  or `compatibility` for a fixed interval when a target drops fast events.
- `executed: true` and a character count mean events were posted, not that text
  appeared. `effect_verified: null` is inconclusive: observe the target before
  submitting or retrying, so a partially delivered value is not duplicated.
- Every timing mode retains the visible Bezier cursor cue. Native typing removes
  character gaps; it does not disable pointer travel or backend delivery time.
- Never type passwords, card numbers, or secrets. If the task requires it,
  stop and ask the user to type it themselves.
- Deletion, purchase/payment, sending, publishing, permission, and account or
  security actions need the matching `risk` and literal `confirm: true`.
- Blocked combos (logout, lock screen, ctrl+alt+delete, alt+f4) return
  `blocked` and never execute.
