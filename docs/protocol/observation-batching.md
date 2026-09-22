# Batch final observation

Status: implemented and verified in the Python and Rust controllers and MCP
adapters. Dry-run returns metadata. Live macOS sessions capture at most one
final image and attach it directly to the same MCP response as the receipts.
Other platforms continue to report their native capture capability honestly.

## Goal

Allow an AI client to request an action sequence and receive one screenshot of
the final state in that same MCP tool response. This removes a client/tool
round trip. It does not remove capture or image-transfer time.

## Proposed request

Use optional `final_observe` parameters to `batch`. Omit it for action-only or
metadata-only batches. Request an image explicitly:

```json
{
  "command": "batch",
  "params": {
    "actions": [
      {"op": "click", "x": 640, "y": 420, "frame_id": "frame-1", "risk": "none"}
    ],
    "final_observe": {"image": true}
  }
}
```

The existing fresh-frame, focus, coordinate, risk, and confirmation checks
remain in force for the click. An observation after it does not retroactively
authorize it.

## Response behavior

- Execute and validate actions with existing ordered batch semantics and receipts.
- After the batch reaches a terminal state, attempt at most one requested final
  observation. Do not observe after every action by default.
- Return the observation descriptor at the top level of the batch result, next
  to `status`, `last_completed`, and `receipts`.
- When `image` is true, the MCP adapter removes image bytes from the text JSON
  and attaches one `image/png` content block to the same tool response, as it
  already does for standalone `observe`.
- Keep the screenshot in the bounded frame store/in-memory response. Do not
  write a screenshot file for this mode.
- Respect capture byte limits and transport backpressure. Return no more than
  one image per batch request.
- Preserve completed/partial action receipts if the observation fails; report
  the observation failure separately from action status.
- If actions were partially executed or cancelled, capture only after input
  cleanup, when the backend can safely do so. Bound cancellation cleanup and
  final capture time.
- Do not add a fixed sleep before capture. The screenshot shows the state at
  capture time; it does not guarantee that animations or asynchronous work have
  finished. Add a bounded condition-based wait only when a caller needs it.

This final observation is for verification and for deciding a subsequent
action. Coordinate actions later in the same batch must still be authorized
against valid observations and revalidated after UI-changing steps; the final
image cannot authorize earlier events.

## Implementation notes

The current MCP adapter extracts `image_b64` only from the top-level result's
`data`. Therefore, the batch controller must promote the final observation to
that top-level shape (rather than burying image data in a step receipt), or the
adapter must explicitly support the new response field. Keep image bytes out of
receipts and logs.

The current batch validator requires every in-batch `observe` to set
`metadata_only: true`. Update validation and tool descriptions together when
implementing this design. Do not describe final image delivery as available
until the MCP response contains an image block and the behavior has been
verified end to end.
