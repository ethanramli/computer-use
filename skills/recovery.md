# Recovery

Instructions for agents when a command fails.

## Error codes and what to do

- `bad_arg` — your arguments were invalid. Fix them from the message and retry.
- `focus_required` / `focus_failed` — pass `--app`, run `focus_app`, verify
  with `active-window`, then retry. Zero events were sent; nothing to undo.
- `stale_frame` — the screen changed. Observe again, use the new `frame_id`.
- `blocked` — the key combo or action is prohibited. Do not retry variants;
  ask the user.
- `needs_attention` — challenge/password/payment/permission UI. Hand the
  task to the user.
- `unsupported` — the platform backend cannot do this. Do not fake it.
  Use an alternative interface or report the limitation.
- `exec_failed` — the OS refused (permissions, missing helper). Run
  `desktop doctor`, follow its recover hint, then retry once.

## After any failure

If macOS observation reports `display layout unavailable` and `doctor` reports
missing permissions inside an agent execution sandbox, do not immediately
change OS grants or patch the adapter. Request the host's execution approval
and rerun `doctor` outside that sandbox. If checks pass there, run the persistent
controller in that approved context. If they still fail, follow the reported
permission recovery instructions; never bypass an OS permission gate.

1. Run `desktop observe` (metadata-only is enough) to see actual state.
2. Compare against what you expected before re-issuing commands.
3. Batch results carry `last_completed` and per-step receipts. Actions
   already executed CANNOT be rolled back — never claim they were.
