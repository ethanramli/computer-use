# Observe

Instructions for agents. Load before using the `observe` controller command.

## When

First step of every task. Also after every meaningful action to verify state.
Use `--metadata-only` when you only need `frame_id`, active window, and screen
size — it skips pixel transfer.

## Steps

1. In a persistent `computer-mcp` session, call `observe` with an optional
   `region` (`x,y,w,h`). A smaller region is cheaper.
2. Read `data.frame_id`. Coordinate actions REQUIRE this fresh frame_id.
3. Read `data.active_window` to know where keyboard input would go.
4. After any click/type that changes UI state, observe again. Old frame_ids
   are rejected with `stale_frame`.

## Rules

- Capture the smallest region that answers your question.
- Never reuse a frame_id after any state change or app switch.
- After a user interruption, observe and verify focus again before resuming;
  the user may have switched applications while the controller remained live.
- Keep observation and every coordinate action in the same controller process.
- The screenshot lives in one memory slot only; nothing is archived.
