# Safety

Instructions for agents. Mandatory, not advisory.

## Hard stops

Never execute, never attempt workarounds for:

- Password, login, payment, permission, CAPTCHA, Turnstile, or any
  "verify you are human" challenge → return `needs_attention`, ask the user.
- Deletion, purchase, message sending, publishing, permission changes,
  account/security changes → explicit fresh user confirmation immediately
  before execution, with the matching `risk` and literal `confirm: true`.
- Credential entry of any kind (the user types secrets themselves).

## Emergency stop

Send MCP `notifications/cancelled` with the active request ID. Cancellation is
request-scoped and is processed while the single action worker is running. A
one-shot CLI `stop` has no persistent process to signal, so it reports
`stopped: false` honestly and does not poison a later command. There is no
shared filesystem stop flag.

## Required workflow

1. Observe before acting; keep the stop control reachable.
2. Verify focus before keyboard input (the toolkit enforces this).
3. Verify state after every meaningful action.
4. Small verified batches beat long ones. Long batches multiply the cost of
   a wrong assumption; executed OS events cannot be rolled back.
5. Report honestly: never claim rollback, deletion of client history, or
   success you did not observe.
