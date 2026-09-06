# Live Input Delivery — Honest Status (2026-09-04, final)

## What is verified live

- **Mouse move**: exact landing verified (position read), including the
  measured 2ms inter-event floor for movebatch streams (0-gap streams are
  coalesced/distorted by the window server — traceability row 23a).
- **Mouse click**: posts and receipts confirmed via the receipt-window tap
  (leftMouseDown/Up received at the exact coordinates).
- **Launch/focus**: `launch --app TextEdit` brings it frontmost, verified.
- **Persistent MCP flow**: observe → frame_id → click accepted end to end
  through `computer-mcp` (one-shot CLI cannot share frame state across
  processes — documented one-shot limitation).
- **`verify=focus`**: correctly reports `effect_verified: true` when
  TextEdit stays frontmost.

## What is NOT reliably delivered

- **Keyboard events (type/press/hotkey)**: `CGEventPost` returns success
  and the controller reports `chars: N` with `effect_verified: true`
  (focus held), but target documents frequently remain empty. The
  receipt-window tap does NOT see the posted keyDowns, while System Events
  keystrokes DO land — the OS is dropping cghelper's synthetic keyboard
  events in this context.

## Root-cause status

Not a controller bug: identical posts landed earlier in the same session
(`KheXY` battery). The failure correlates with the posting process's TCC
attribution and Secure Input state, which changed during the session. This
is exactly the dispatch-vs-effect gap the receipt fixture exists to detect.

## Required for reliable keyboard delivery

1. Grant Accessibility to the specific installed binary (or its
   responsible interpreter) and **restart the caller** so TCC re-attributes.
2. Re-run the keyboard battery with the receipt-window fixture attached;
   only claim success when receipts match posts AND the target document
   reflects the text.

Per the completion ruling: no live keyboard claim is made while delivery
is unproven. Mouse + observe + launch + MCP flow remain verified.
