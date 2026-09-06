# Clicking

Instructions for agents. Real OS events — not DOM clicks.

## Steps

1. Use one persistent `computer-mcp` session.
2. Call `observe`; keep its `frame_id`, display layout, and pixel coordinates.
3. In that same session call `click`, `double-click`, or `right_click` with
   `x`, `y`, the fresh `frame_id`, and an explicit `risk`.
4. Observe again and verify the effect before the next dependent action.

## Rules

- Coordinates are only accepted with a fresh frame_id; a stale one returns
  `stale_frame` and zero events are sent.
- A frame ID belongs to its controller process. An executed coordinate action
  is intentionally rejected by the one-shot CLI because it cannot reuse that
  frame state.
- Verify the intended foreground app before dependent keyboard input.
- Buttons and links that trigger deletion, purchase, message sending,
  publishing, or permission changes require explicit user confirmation
  and `confirm: true` immediately before execution.
- If the UI shows a password, payment, permission, CAPTCHA, or
  "verify you are human" challenge: STOP. Return `needs_attention` to the
  user. Never attempt to bypass or solve it.
