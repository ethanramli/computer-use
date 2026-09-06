# Scrolling

Instructions for agents. Scrolling uses real OS wheel events at the current
pointer location; it is not browser- or DOM-specific.

## Steps

1. Focus the intended application and verify it is foreground.
2. If the window has multiple scrollable panes, observe in the persistent MCP
   session and use `move` with that fresh `frame_id` to place the pointer over
   the intended pane.
3. Call `scroll` with `direction` (`up`, `down`, `left`, or `right`), an
   `amount` from 1 to 100, and explicit `risk`.
4. Observe again and verify that the intended viewport moved in the requested
   direction.

## Rules

- Every scroll command performs the mandatory visible Bezier cursor cue before
  posting wheel events.
- Wheel events go to the surface under the pointer. Focus alone does not choose
  between multiple scrollable panes in one window.
- Use small verified scrolls. Do not assume a reported dispatch means the page
  moved; content may already be at an edge.
- On macOS, vertical directions use the vertical wheel axis and horizontal
  directions use the horizontal wheel axis.
