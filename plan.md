# Cross-device Computer Use Protocol — Implementation Plan

**Project:** `ethanramli/computer-use`
**Plan date:** 2026-09-14
**Status:** Proposed implementation plan; no implementation milestones completed
**Review baseline:** `c089d001c3c0eec267948d3dcb4587bfa59290e5`
**Initial protocol version:** `0.1` — proposed, not an existing standard

## 1. Goal and primary decision

Evolve the existing local desktop automation toolkit into a language-independent computer-use protocol, backed by a Rust reference agent and an MCP adapter.

The project should support both:

- **Cross-platform execution:** the same client contract works against different operating systems, subject to explicitly advertised capabilities.
- **Cross-device execution:** a client can observe and control another authorized device through an authenticated connection.

These are separate deliverables. Compiling the current implementation for several platforms is not sufficient to achieve either one.

**Do not begin with a line-by-line Python-to-Rust conversion.** First establish the protocol contract, test harness, and trust boundaries. Then migrate the working behavior behind those boundaries and prove interoperability on a second operating system.

Rust is the reference implementation language, not a requirement for protocol clients or alternative device agents. Platform-native bridges may remain in C, Kotlin, or other appropriate languages.

### Intended result

An AI client, CLI, or application should be able to discover a device, obtain an authorized session, capture an observation, execute a supported action, and inspect its result without knowing how the target OS implements capture or input.

The protocol must not claim identical capabilities on every device. A phone need not have a cursor, a capture-only target need not accept input, and a sandboxed application must not be advertised as providing unrestricted system control.

## 2. Scope

### First useful release

The first cross-device release should deliver:

1. A documented protocol v0.1 with schemas, examples, and a conformance suite.
2. A Rust device agent with bounded execution, explicit permissions, cancellation, and action receipts.
3. A working macOS backend migrated from the existing implementation.
4. A working Ubuntu/Wayland backend using the same client contract.
5. An MCP adapter and a diagnostic CLI.
6. An authenticated desktop-to-desktop demonstration with tested disconnect and retry behavior.

The first local Rust milestone can precede remote access. Windows follows the two-platform proof. X11 and mobile support are separate, capability-scoped milestones.

### Non-goals for v0.1

- An LLM, planner, browser-specific workflow engine, or hosted agent service inside the device agent.
- A new cryptographic protocol or custom video codec.
- A public internet relay, account system, device fleet manager, or automatic discovery service.
- Unrestricted mobile control or universal feature parity across operating systems.
- CAPTCHA bypass, credential extraction, hidden control, or bypassing OS permission boundaries.
- Arbitrary shell execution or filesystem access as implicit privileges of screen control.
- Unbounded screenshots, action history, work queues, or replay logs.
- Guaranteed exactly-once application effects or rollback of arbitrary GUI actions.
- A complete rewrite of all native integrations before a usable Rust agent exists.

## 3. Baseline and review findings

This plan is based on the source review at the pinned commit above. The earlier review did not execute the repository's tests or validate native behavior on each target OS. Implementation must begin by checking the current branch and confirming which findings still apply.

### Preserve the useful foundations

The current design already separates shared controller policy from platform adapters, validates batches before dispatch, tracks frame geometry, supports request-scoped cancellation, and reports partial execution. Preserve those intentions and their useful regression tests. See [R1], [R2], [R3], and [R4].

### Findings to verify and address

| Area | Behavior observed at the review baseline | Required direction |
|---|---|---|
| Platform coverage | The README describes macOS as implemented and Windows, X11, and Wayland as unsupported. | Publish capability-level support backed by native tests. [R1] |
| Safety inspection | `input_state_issue(None)` permits input; unavailable inspection can become `None`. | Represent normal, sensitive, and unknown states separately. Unknown must not silently mean safe. [R2], [R5] |
| Confirmation | Risk and `confirm: true` are supplied by the caller. | Separate declared intent from independently enforced authorization. [R5] |
| Admission control | Complete input lines are read before the request-size check; ordinary requests are submitted without an explicit queue-capacity gate. | Bound reads and queues before accepting work. [R6] |
| Stop and disconnect | Cancellation primarily targets active work; queued work and EOF behavior need an explicit session policy. | Distinguish action cancellation, session stop, disconnect, and shutdown. [R2], [R6] |
| Observation validity | Frame checks cover retained identity, layout, capture bounds, and foreground application, but not capture age or arbitrary content changes within an app. | Add session/epoch identity, server-measured age, target preconditions, and honest freshness semantics. [R2], [R4] |
| MCP integration | The server has a handwritten transport/lifecycle implementation and a hard-coded revision. | Use a maintained SDK and test actual version negotiation and client interoperability. Do not treat the advertised revision alone as compatibility evidence. [R6] |
| Releases | The inspected publishing workflow does not invoke the test suite. | Gate release artifacts on tests and package smoke checks. [R7] |

These findings are implementation tasks, not claims that a Rust rewrite alone resolves them. Regression fixtures must distinguish intended compatibility from deliberate fixes to unsafe or ambiguous behavior.

## 4. Architecture

```text
AI client / CLI / application
             |
      MCP adapter or SDK
             |
 Versioned computer-use contract
             |
 Local or authenticated transport
             |
       Rust device agent
  +--------------------------------+
  | Identity and authorization     |
  | Sessions and control ownership |
  | Observations and frame state   |
  | Ordered action execution       |
  | Cancellation and receipts      |
  +--------------------------------+
             |
       Platform adapters
       +-- macOS
       +-- Linux / Wayland
       +-- Windows
       +-- Linux / X11
       +-- Mobile capability profiles
```

### Boundaries

**Protocol:** Owns wire types, meanings, versioning, capabilities, errors, and compatibility rules. It must be usable without importing Rust code.

**Core:** Owns policy enforcement, authoritative session state, observation validation, action lifecycle, and resource budgets. It must not depend on MCP, model providers, or OS-specific APIs.

**Platform adapters:** Own capture, native input, focus inspection, accessibility inspection, and platform permission reporting. Unsupported behavior must be reported explicitly rather than simulated as success.

**Agent runtime:** Owns transports, bounded admission, worker lifecycles, and dispatch into the core. It runs in or connects explicitly to the intended graphical user session.

**MCP adapter:** Maps tools, images, errors, and cancellation to the computer-use contract. It is an integration layer, not the universal protocol itself.

**Client libraries:** Construct typed requests and expose receipts. They must not hide uncertain outcomes behind automatic retries of state-changing actions.

### Proposed repository structure

```text
spec/
  protocol.md
  security.md
  capabilities.md
  compatibility.md
  schemas/
  examples/
crates/
  cu-protocol/
  cu-core/
  cu-platform/
  cu-agent/
  cu-mcp/
  cu-cli/
backends/
  macos/
  linux-wayland/
  windows/
  linux-x11/
  mock/
native/
  macos/
conformance/
  fixtures/
  scenarios/
  runner/
integration/
  platform-fixtures/
  transport-tests/
docs/
  architecture/
  migration/
  development/
  operations/
```

Names are provisional. Avoid creating empty production backends merely to make the directory tree look complete.

## 5. Protocol v0.1

### 5.1 Specification and versioning

Commit the protocol specification, JSON schemas, valid examples, invalid examples, and expected outcomes together.

Use separate identifiers for:

- Computer-use protocol version.
- Agent implementation version.
- Backend implementation/version information.
- MCP protocol revision negotiated by the MCP adapter.

Begin with a small supported version set and explicit negotiation. Unsupported versions must fail clearly. Define extension namespaces and unknown-field handling rather than relying on permissive deserialization.

Use JSON for the initial contract. Use an existing framing/RPC mechanism rather than inventing an undocumented stream format. The example below uses a proposed JSON-RPC 2.0 binding; its domain payload must remain independent of the transport and MCP.

Rust types may generate schema candidates, but committed specifications and compatibility tests govern the public contract. A Rust refactor must not silently alter the wire format.

### 5.2 Core objects

| Object | Required meaning |
|---|---|
| Device | A target with an authenticated identity and a declared set of capabilities. A friendly name is not an authentication credential. |
| Runtime epoch | An opaque identifier that changes when authoritative agent state is restarted or reset. |
| Session | An authorization context bound to a client, device, runtime epoch, scopes, and lifetime. |
| Control lease | Time-bounded ownership of input for an interactive session/seat. It is distinct from read-only observation permission. |
| Surface | A display, window, or other explicitly identified capture/control region. |
| Observation | A capture plus the geometry, timestamps, and inspectable state needed to interpret it. |
| Action | A uniquely identified, ordered request to perform a state-changing operation. |
| Receipt | Evidence about validation, dispatch, partial progress, verification, and cleanup. |
| Approval | A narrowly scoped grant issued through a trusted authorization path, not a caller-supplied boolean. |

There must be one authoritative input owner per controlled interactive session/seat, including across different transports and processes. Separate stdio clients must not accidentally create independent controllers that race over the same desktop.

### 5.3 Capability discovery

A device description must distinguish:

- Whether a capability is implemented.
- Whether the current OS permissions allow it.
- Whether session policy grants access to it.
- Whether it is currently available.
- Its limits, supported modes, and verification guarantees.

Initial capability groups:

| Group | Examples | v0.1 position |
|---|---|---|
| Session lifecycle | Open, renew, stop, close | Core |
| Observation | Describe surfaces, capture an image, report geometry | Required for the initial controlled-desktop profile |
| Pointer | Move, click, drag, scroll | Desktop profile; optional for other devices |
| Keyboard | Insert text, press a key, send a chord | Desktop profile; optional for other devices |
| Accessibility | Focus inspection, element metadata | Explicitly advertised; policy determines degraded-mode behavior |
| Application/window management | Enumerate, focus, launch | Optional capability group |
| Touch | Tap, swipe, bounded multi-contact gestures | Later mobile profile |
| Clipboard/files/shell | Separate privileges and threat models | Out of v0.1 unless separately approved |

Capability changes, especially permission revocation, must take effect at execution time. Startup discovery is not a permanent grant.

### 5.4 Proposed core operations

| Operation | Responsibility |
|---|---|
| `device.describe` | Negotiate/describe protocol support, surfaces, capabilities, and current permission status. |
| `session.open` | Request an observation or control session under server-enforced scopes. |
| `session.renew` | Renew an eligible lease without expanding its privileges. |
| `session.stop` | Latch the session into a stopped state, revoke input ownership, and cancel active and queued work. |
| `session.close` | End the session, release its resources, and invalidate its grants and observations. |
| `observation.capture` | Capture an authorized surface and return image content plus its descriptor. |
| `action.execute` | Validate and admit a supported action under the session and lease. |
| `action.status` | Retrieve known progress or a retained receipt without re-executing the action. |
| `action.cancel` | Cancel one queued or active action without implicitly stopping unrelated actions. |

The spec must state whether each operation returns synchronously or acknowledges admission. A practical first design is immediate action admission followed by a terminal receipt or status lookup; the MCP adapter may wait for the terminal result within its own request lifetime.

Do not introduce push events, subscriptions, or streaming video until polling/snapshot behavior and bounded resource ownership are stable.

### 5.5 Observations and coordinates

Each observation descriptor must include:

- Device/runtime/session/surface identity and an opaque observation ID.
- Capture start/end information and server-measured age information.
- Image width/height, format, crop, and orientation.
- Surface layout revision and an explicit image-to-input coordinate transform.
- Available focus/target metadata, with unknown values represented as unknown.
- Applicable validity limits and verification limitations.

Use server-local monotonic time to enforce age, timeouts, and leases. Wall-clock timestamps may aid diagnostics but must not require synchronized clocks between devices.

Specify image pixel coordinates separately from native input coordinates. Account for cropping, resizing, DPI scaling, signed display origins, rotation, and gaps between monitors. Define rounding and boundary behavior in the spec.

Start with one explicitly selected surface per capture/action. Add whole-desktop composites only when their transform and mixed-scale behavior are covered by tests.

Immediately before dispatch, validate observation ownership, epoch, age, layout, target bounds, lease, permissions, and available target preconditions. Invalidate observations on known incompatible changes.

A fresh screenshot is not proof that the application has remained unchanged. Pre-dispatch checks reduce risk but cannot make arbitrary desktop observation and input atomic. Receipts and documentation must not imply otherwise.

Metadata-only device inspection must not mint visual authorization. An image-free capture response may retain an observation descriptor only if an actual capture occurred and the same validation rules apply.

### 5.6 Input semantics

Keep these operations distinct:

- Text insertion, with explicit Unicode handling and a defined partial-progress unit.
- Logical key presses and chords, distinct from physical key positions where supported.
- Pointer movement, clicks, bounded drags, and scrolling with declared units.
- Touch gestures with contact IDs, timing, and bounded contact counts.

Do not silently translate unsupported text insertion into clipboard access or another privileged operation. Declare the mechanism and any extra permission requirements.

Visible cursor motion is a desktop presentation policy, not a universal protocol requirement. Preserve visible control status and accessible stopping, but do not make a touch-only device invent a mouse cursor.

Avoid externally exposed, indefinitely held key/button state in the first release. Composite key chords and drags should acquire and release their native state within a bounded action.

### 5.7 Proposed request example

This is a protocol-design example, not syntax supported by the existing Python implementation. Authentication belongs to the transport/session establishment and is intentionally absent from the payload.

```json
{
  "jsonrpc": "2.0",
  "id": "rpc-42",
  "method": "action.execute",
  "params": {
    "protocol_version": "0.1",
    "device_id": "office-ubuntu",
    "runtime_epoch": "epoch-9",
    "session_id": "session-7",
    "action_id": "action-42",
    "action_seq": 42,
    "action": {
      "type": "pointer.click",
      "surface_id": "display-1",
      "observation_id": "observation-218",
      "position": {
        "space": "observation_pixels",
        "x": 640,
        "y": 360
      },
      "button": "primary"
    },
    "preconditions": {
      "layout_revision": 12
    },
    "timeout_ms": 3000
  }
}
```

The timeout covers the accepted action's queue wait and execution according to the final spec. The server enforces the earliest applicable timeout, lease expiry, and policy limit. Caller preconditions may strengthen server policy; they may not relax it.

## 6. Authorization and user control

### 6.1 Trust boundaries

Treat the remote client, model output, observed application content, and action payload as untrusted inputs. The device agent is the authority for what may execute.

Observed text is data, not instructions granting privilege. Do not allow webpage content, accessibility labels, or a model's risk classification to authorize new capabilities.

Session grants must be bound to an authenticated client and constrained by device, graphical session, surface/capabilities where enforceable, and lifetime. State honestly when global OS input cannot provide hard application-level confinement.

### 6.2 Sensitive and unknown UI

Use explicit inspection states such as `known_normal`, `known_sensitive`, and `unknown`.

Default handling:

- Known sensitive/challenge UI: pause and require user attention under the declared policy; do not bypass protection.
- Unknown inspection state: do not silently approve input.
- Restricted visual-only mode: permit only through explicit local authorization with visible limitations and reduced scopes.

Heuristic text matching can be an additional signal, but it is not a complete safety classifier. Keep policy decisions separate from schema validation and backend mechanics.

### 6.3 Approval flow

For actions requiring approval:

1. Return an attention/approval-required result without dispatching input.
2. Present the operation through a trusted user-facing approval path.
3. Issue an opaque, short-lived grant bound to the client, session, target, and canonical action or clearly bounded operation.
4. Validate and consume that grant when the corresponding action executes.
5. Invalidate it on expiry, session stop, target changes that break its conditions, or reuse.

A caller-provided `confirm: true`, risk category, or approval description is never sufficient authority by itself. Approval does not override OS restrictions.

### 6.4 Visible control and stopping

Provide an obvious control indicator and an independent local stop mechanism. Stopping must remain reachable when the normal action queue is full or an action is waiting.

`session.stop` is latched: queued work is cancelled and new input is rejected until a fresh explicit authorization/control grant is obtained. Reconnecting must not silently resume old queued actions.

Enable remote access explicitly. Do not introduce hidden listeners or automatic background startup as an incidental side effect of installation.

## 7. Execution, cancellation, and retry semantics

### 7.1 Bounded admission and ordering

Before accepting work:

- Enforce frame/message sizes while reading, before unbounded allocation.
- Limit nesting depth, strings, batch sizes, decoded image sizes, and outstanding requests.
- Apply per-session and process-wide queue limits and rate/resource budgets.
- Validate identity, session, method, capability, and payload structure.
- Reserve an action identity and ordering position atomically with admission.

Use a serialized input executor per controlled seat/session, not one global executor for every device. Read-only work may run separately where backend thread-affinity and consistency requirements allow it.

Control messages must not wait behind the ordinary action queue. They still require authentication and bounded parsing.

### 7.2 Action lifecycle and receipts

Keep lifecycle, dispatch outcome, and effect verification separate.

| Field | Example values | Meaning |
|---|---|---|
| Lifecycle | Queued, running, finished, unknown | Whether the agent knows execution has reached a terminal state. |
| Dispatch outcome | Not started, partial, completed, unknown | What the agent knows about native input dispatch. |
| Terminal reason | Completed, rejected, cancelled, deadline exceeded, execution failed, connection lost | Why execution ended. |
| Verification | Verified, unverified, unsupported, not requested, unknown | Evidence about a specifically named observable effect. |
| Cleanup | Completed, failed, unknown | Whether held input state was released as intended. |

“Input dispatched” must never become an implicit claim that a message was sent, a purchase completed, or the intended business task succeeded. Name the effect that was actually verified.

For rejected actions, state that no input was dispatched. When a failure occurs after native dispatch may have started, preserve uncertainty instead of returning a misleading clean failure.

### 7.3 Retry and deduplication

The disconnect-after-click case is mandatory to solve before remote release.

Bind action identity to the runtime epoch and session. Use an ordered action sequence plus a bounded receipt/deduplication store so that an old sequence cannot become executable again when its detailed result is evicted.

Required behavior:

- Same retained action identity and payload: return status/result; do not dispatch again.
- Same identity with a different payload: reject the conflict.
- Old action sequence whose result has expired: return `result_expired` or an equivalent explicit result; never treat it as a new action.
- Agent restart or authoritative state loss: invalidate sessions and observations; report uncertainty for unverifiable previous effects.
- Client timeout after admission: query action status rather than automatically replaying the action.

Do not promise exactly-once application effects. A durable journal may improve post-crash knowledge later, but it does not make OS input and external application state transactional.

### 7.4 Cancellation, deadlines, and connection loss

Specify and test each case independently:

| Event | Required behavior |
|---|---|
| Cancel queued action | Remove/mark it cancelled without dispatch. |
| Cancel running action | Interrupt at supported boundaries, release held inputs, return partial progress or uncertainty. |
| Session stop | Revoke input ownership, cancel queued/active work, latch the session stopped. |
| Lease expiry | Prevent further dispatch and initiate cleanup. |
| Transport disconnect | Stop accepting work, cancel queued/active input, and do not resume it automatically. |
| EOF or agent shutdown | Apply the shutdown policy before waiting for workers; do not simply drain old GUI work. |
| Native worker crash | Record unknown progress when necessary and invoke an independent cleanup path where available. |

Use server monotonic deadlines. Every wait and native loop must have a bounded interruption strategy. RAII guards help normal error paths but are not a guarantee after process termination; test watchdog/worker-failure cleanup separately.

### 7.5 Batches

Preserve the current batch command and its whole-batch structural validation. Enforce bounded size/duration and revalidate dynamic conditions before each step. A batch remains one MCP request, so the client does not need a separate tool round trip for a final visual check.

Add an optional `final_observe` request to the batch parameters. When requested,
capture exactly one observation after the action sequence reaches a terminal
state and return its descriptor in the batch result. For `final_observe.image: true`,
attach the screenshot as MCP image content in the same tool response; do not
embed base64 in JSON text or write an image file. Put the final observation at
the top level of the batch result so the MCP adapter can extract it without
walking step receipts. Keep only one bounded image buffer/result and apply
existing capture budgets and backpressure.

The final observation is optional so metadata-only or action-only batches do
not pay image capture/transfer cost. Capture once after the batch, never after
every step by default. Attempt the explicitly requested final observation after
successful or partial execution, including cancellation after cleanup where
the backend can safely observe; preserve action receipts if capture fails and
report the observation error separately. Bound the capture and cancellation
cleanup time. Do not insert a fixed sleep before capture. If an application
needs time to render, allow an explicit bounded condition/wait policy rather
than imposing latency on every action.

A batch that changes the UI must not authorize all later coordinate actions
using the original screenshot merely because its syntax was preflighted. Return
step receipts and stop on failed preconditions. The final screenshot verifies
the terminal visible state; it does not authorize prior or later actions and
does not prove that an animation or asynchronous application operation has
settled. Do not promise atomicity or rollback.

## 8. Rust implementation strategy

### 8.1 Candidate foundations

Evaluate Tokio for asynchronous runtime work, Serde for typed serialization, a schema-generation tool such as `schemars`, and the official `rmcp` Rust SDK for MCP integration.

These are implementation candidates, not pinned version recommendations. Verify supported versions, features, maintenance, and platform compatibility during the dependency-selection task. Commit dependency versions and the lockfile for reproducible agent builds.

Use typed validated domain objects instead of passing unrestricted JSON maps through the core. Keep transport metadata and internal execution context separate from caller-controlled parameters.

### 8.2 Worker and native-code boundaries

Keep blocking and thread-affine OS calls outside ordinary asynchronous transport tasks. Document each backend's threading/run-loop requirements.

Concentrate FFI and unsafe operations inside small audited wrappers. Preserve errors, partial counts, and permission failures across the boundary. Do not map every native error to a generic success/failure boolean.

### 8.3 Migrate macOS incrementally

Initially retain the working native helper behind a Rust backend adapter. Preserve its reproducible build and native receipt fixture where useful. The reviewed implementation already has a helper-process boundary suitable for staged migration. [R8], [R9]

Then evaluate a persistent native worker or direct native integration using measurements. Do not change language, wire format, native mechanism, and transport simultaneously without compatibility tests separating the changes.

### 8.4 Screenshot ownership and performance

Preserve bounded screenshot ownership. Separate large image buffers from small observation descriptors and receipts.

Negotiate authorized capture regions and output dimensions. Specify image formats and maximum decoded dimensions. Account for temporary buffers and encoding copies, not only the final compressed image size.

Use image content through the MCP adapter rather than embedding image bytes inside a textual JSON description. For a remote transport, select a bounded image-delivery binding; local filesystem paths must not be assumed accessible on another device.

The MCP adapter must extract images both from standalone observations and from
the batch result's top-level `final_observation`, returning image content in the
same MCP tool response. Keep `image_b64` out of the accompanying text envelope.
The initial batch design supports at most one final image per request; clients
that want an image after every step must issue separate observations deliberately
and remain subject to image memory and transport backpressure limits.

Benchmark capture, encoding, validation, queue wait, native dispatch, cancellation, and observed effect separately. Report cold/warm state, platform, failures, and distributions. Do not promise a speedup based solely on choosing Rust.

## 9. Platform and transport strategy

### 9.1 Backend order

| Backend | Initial approach to evaluate | Release gate |
|---|---|---|
| macOS | Rust adapter around existing native helper, then measured native-worker improvements. | Native capture/input/focus/permission tests and parity fixtures pass. |
| Ubuntu / Wayland | XDG desktop portals for authorized capture/remote desktop, PipeWire for capture, EIS/libei input where supported. | Real Ubuntu graphical-session tests pass; capability and permission behavior are documented. |
| Windows | Native capture, input, and accessibility facilities with explicit desktop/session and privilege handling. | Tested combinations have documented limitations; no unsupported secure-desktop behavior is claimed. |
| X11 | Separate native backend rather than a Wayland fallback claim. | Actual X11 integration evidence and a clear capability profile. |
| Android | Platform-native service layer plus shared Rust components where useful. | Technical feasibility, permission lifecycle, deployment mode, and distribution-policy review are complete. |
| iOS / iPadOS | Controller application role first; assess target-control modes separately. | Only supported, verified roles/capabilities are advertised. |

Platform APIs and mobile distribution policies must be checked against current official documentation during implementation. Do not equate a successful build with permission to perform system-wide control or distribute that behavior.

Keep “device as controller” and “device as controlled target” distinct in the support matrix.

### 9.2 Initial remote transport

Prefer an existing authenticated transport for the first proof. Evaluate explicitly configured SSH/stdin forwarding into the correct user graphical session before building a new listener or relay.

If SSH does not fit the intended deployment, record that decision and implement a narrow authenticated, encrypted transport with explicit pairing/trust establishment. Do not invent cryptography or treat loopback binding as sufficient authorization.

In either case:

- The device agent remains authoritative for session policy.
- Network identity must map to an authorized local control context.
- Client connection loss must propagate into cancellation/lease policy.
- Do not run the entire agent as root merely to obtain capture or input access.
- A relay, if introduced later, must not automatically receive authority to impersonate clients.

Finalize the remote threat model before exposing any listener. Remote access is a deliberate change from the baseline repository's local-only non-goal and requires updated documentation. [R1]

## 10. Milestones and work items

All boxes are intentionally unchecked. Completing a source review or writing this plan does not complete implementation work.

### M0 — Establish baseline and freeze the first contract

**Dependencies:** None.

- [ ] **M0.1** Inspect the current branch, record the actual baseline commit, and identify differences from this review.
- [ ] **M0.2** Run the existing tests in an appropriate environment; record commands, outcomes, platform, and skips.
- [ ] **M0.3** Inventory current commands, schemas, safety behavior, native integrations, packaging, and repository licensing/attribution files.
- [ ] **M0.4** Decide core/profile/extension boundaries and write protocol v0.1, security, compatibility, and capability documents.
- [ ] **M0.5** Commit proposed request/response schemas and valid/invalid examples.
- [ ] **M0.6** Extract representative Python fixtures; explicitly mark expected behavior changes for the review findings.
- [ ] **M0.7** Build a deterministic mock backend with controllable focus, geometry, permissions, time, cancellation, and native-failure simulation.

**Acceptance criteria:** A developer can implement a non-Rust client from the specification. Mock scenarios describe expected outcomes without requiring a real desktop. Known ambiguities have recorded decisions rather than silent defaults.

### M1 — Rust runtime with mock backend

**Dependencies:** M0 contract and fixtures.

- [ ] **M1.1** Create the Rust workspace, protocol types, validated domain types, and shared backend interfaces.
- [ ] **M1.2** Implement session identity, runtime epochs, capability checks, scopes, leases, and exclusive input ownership.
- [ ] **M1.3** Implement bounded message framing, admission, queues, action ordering, and deduplication.
- [ ] **M1.4** Implement observations, coordinate transforms, age/layout checks, and target preconditions.
- [ ] **M1.5** Implement action lifecycle, receipts, cancellation, session stop, timeout, disconnect, and shutdown behavior.
- [ ] **M1.6** Implement the local CLI and the MCP adapter through a verified SDK/version combination.
- [ ] **M1.7** Add mock conformance tests and schema-validation gates to CI.

**Acceptance criteria:** A local client can open a mock session, observe, act, and inspect a receipt. Queue saturation cannot block stopping. Duplicate actions do not execute twice. Malformed input causes no native work and stays within configured resource budgets.

### M2 — Working macOS Rust agent

**Dependencies:** M1; authorized macOS integration environment.

- [ ] **M2.1** Implement the Rust macOS adapter around the existing helper and verified capture integration.
- [ ] **M2.2** Reproduce permission diagnostics and declare sensitive/unknown inspection behavior.
- [ ] **M2.3** Validate capture geometry, focus changes, Unicode input, pointer actions, and native partial progress.
- [ ] **M2.4** Verify cleanup under cancelled drag/chord, helper failure, disconnect, and shutdown.
- [ ] **M2.5** Run Python/Rust fixtures, separating intended parity from documented safety changes.
- [ ] **M2.6** Package a usable local agent and smoke-test the installed artifact and MCP integration.

**Acceptance criteria:** Real local observe–act–verify scenarios succeed in a harmless test application. Receipts do not overclaim effects. Installation and permission recovery work on the declared macOS configurations.

### M3 — Ubuntu/Wayland and authenticated cross-device proof

**Dependencies:** M1 contract; M2 establishes the first native reference; remote threat model approved before network exposure.

- [ ] **M3.1** Implement authorized capture and input for a declared Ubuntu/Wayland configuration.
- [ ] **M3.2** Expose real capability/permission state, including unsupported and revoked states.
- [ ] **M3.3** Select and implement the initial authenticated transport with graphical-session attachment documented.
- [ ] **M3.4** Implement trusted pairing/authorization UX as needed for that transport and enforce device-side policy.
- [ ] **M3.5** Run the same client scenarios against macOS and Ubuntu without changing OS-specific request semantics.
- [ ] **M3.6** Test network interruption before dispatch, during input, and after dispatch but before receipt delivery.
- [ ] **M3.7** Test lease expiry, stopped-session reconnection, stale observations, duplicate actions, and remote queue saturation.
- [ ] **M3.8** Publish the exact capability/support matrix and remote setup/stop instructions.

**Acceptance criteria:** An authenticated client on another device can control both native backends through the same protocol. Unknown outcomes require status inspection or re-observation rather than blind retries. Disconnect cannot leave queued input scheduled for later automatic execution.

### M4 — Windows, SDKs, and release hardening

**Dependencies:** M3 cross-device proof.

- [ ] **M4.1** Implement and test the Windows capability profile in real interactive sessions.
- [ ] **M4.2** Add X11 only if required by the supported deployment matrix.
- [ ] **M4.3** Provide a TypeScript client and a Python client with typed requests, receipt handling, and safe retry behavior.
- [ ] **M4.4** Add signed/reproducible release procedures as appropriate, dependency review, and artifact checksums/provenance.
- [ ] **M4.5** Gate publication on schema compatibility, conformance, native evidence, and installed-package smoke tests.
- [ ] **M4.6** Document upgrade/downgrade behavior, protocol mismatch handling, and session invalidation after restart.
- [ ] **M4.7** Publish migration guidance and retire legacy paths only after the replacement is usable.

**Acceptance criteria:** Every advertised backend/capability has test evidence and clear limitations. SDKs expose uncertainty and do not silently replay non-idempotent actions. Release artifacts, not just source builds, pass smoke checks.

### M5 — Optional extensions after v0.1

**Dependencies:** Stable desktop contract; separate design approval for each extension.

- [ ] Touch/mobile capability profiles and Android feasibility implementation.
- [ ] iOS/iPadOS controller client; separately scoped controlled-target research.
- [ ] Accessibility element trees and element-targeted actions with handle lifetime rules.
- [ ] Bounded, dynamically revalidated batches and condition-based waiting.
- [ ] Bounded final screenshot delivery for a batch in the same MCP response, with no fixed post-action wait; capability and partial-failure behavior are tested.
- [ ] Change notifications or video streaming justified by measurements.
- [ ] Device registry/discovery or relay transport with a separate threat model.
- [ ] Durable action journaling, with explicit post-crash uncertainty semantics.

Do not let optional extensions delay the two-desktop interoperability proof.

## 11. Test strategy

### 11.1 Protocol and policy conformance

Run these against the mock backend on every change:

- Valid and invalid requests, unsupported versions/methods/capabilities, and unknown fields.
- Oversized/truncated framing, excessive nesting, queue saturation, and conflicting action IDs.
- Session/epoch mismatches, expired leases, denied permissions, and approval reuse.
- Unknown safety metadata, sensitive UI, and explicit restricted-mode behavior.
- Stale observations, mismatched layouts, display gaps, out-of-bounds points, and transform rounding.
- Cancellation in queued/running states, stop under load, EOF, shutdown, and worker failure.
- Receipt eviction without permitting old action re-execution.

Use deterministic clocks and synchronization in tests wherever possible instead of fragile timing sleeps.

### 11.2 Native integration

Use harmless test applications and authorized interactive environments. Validate capture dimensions, coordinate mapping, focus transitions, keyboard layouts, Unicode insertion, pointer behavior, permission revocation, and input release.

Include mixed-scale displays, negative origins, rotation, a disconnected monitor, display locking, and application state changes between capture and dispatch where the platform supports these configurations.

Headless/mock tests do not qualify a backend as natively supported. CI builds, virtual display tests, and real interactive tests must be labelled separately.

### 11.3 Remote fault injection

Exercise drops before admission, while queued, while holding input, and after possible dispatch but before response delivery. Test reconnection to a stopped session, restart with a new epoch, slow clients, and one client attempting to control another client's session.

### 11.4 Performance and observability

Measure bounded memory under sustained capture/request load, queue wait, dispatch latency, cancellation latency, and capture/encoding costs. Define release thresholds after collecting a baseline; do not invent speedup claims.

Logs should contain correlated IDs, error categories, lifecycle transitions, and timings—not typed text, credentials, approval secrets, screenshots, or raw accessibility content by default. Minimize/redact window titles and other potentially sensitive metadata.

## 12. Migration and compatibility rules

Keep the Python implementation available until the Rust replacement passes the required milestones. Do not delete tests simply because they reveal a migration difference.

Maintain a compatibility table mapping existing commands to the new contract and documenting intentional changes. Where useful, add a legacy CLI/MCP facade that translates old requests into the new core without bypassing policy.

Examples of deliberate changes that must be documented:

- Unknown focused-element inspection no longer silently authorizes input.
- Caller confirmation flags do not constitute independent approval.
- Session stop cancels pending work and stays stopped.
- Observations are bound to a session and runtime epoch and have explicit validity limits.
- Unsupported platform behavior remains explicit rather than being emulated as success.

Version legacy facades separately from the protocol. Do not make new clients depend on old command names or process-local frame IDs.

## 13. Definition of done for the first cross-device release

The release is ready only when all of the following are demonstrated:

- [ ] Protocol v0.1 is documented with schemas, examples, capability profiles, errors, and compatibility rules.
- [ ] A non-Rust client can execute the documented observe–act–inspect workflow.
- [ ] The same client controls macOS and Ubuntu/Wayland through the same domain contract.
- [ ] Authentication and device-side authorization are enforced before remote input.
- [ ] Only one client owns input per controlled seat/session, across all active transports.
- [ ] Sensitive/unknown UI behavior is explicit and matches documentation.
- [ ] Coordinates are traceable to authorized observations and tested transforms.
- [ ] Cancellation, session stop, lease expiry, disconnect, EOF, and native failure are tested separately.
- [ ] Duplicate actions do not dispatch twice within the stated guarantees; uncertainty is preserved across state loss.
- [ ] Message reading, queues, image memory, descriptors, and receipts are bounded.
- [ ] Native input delivery is not presented as proof of an unverified application/business effect.
- [ ] MCP compatibility is demonstrated with declared clients/revisions, not inferred from a version string.
- [ ] Installed release artifacts pass diagnostics and smoke tests.
- [ ] No screenshots, credentials, typed secrets, or approval tokens appear in default logs.
- [ ] Supported configurations and known limitations are published honestly.

## 14. Instructions for the implementing agent

Start with **M0**, then implement the smallest vertical slice of **M1**: protocol types, a mock device, session opening, observation, one pointer action, a receipt, and cancellation.

Do not start by translating every Python file. Do not expose a network listener, broaden permissions, remove the Python implementation, or declare a backend supported merely to complete a checklist.

Before each milestone, record its dependencies and acceptance tests. After each milestone, record changed files, commands actually run, results, skips, known limitations, and decisions requiring review. Mark checkboxes complete only when the corresponding evidence exists.

Keep working changes small enough to distinguish protocol changes, policy fixes, Rust migration, native backend work, and transport work. Add a regression test for every verified review finding that is fixed.

**First development task:** Define protocol v0.1 and implement a Rust agent skeleton with a deterministic mock backend and conformance tests.

## 15. Source references

Repository references are pinned to the reviewed commit. They describe the baseline, not a guarantee about the current branch. External documentation links are implementation starting points; supported APIs, versions, and platform policies must be verified when work begins.

### Reviewed repository

- [R1 — README and current scope](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/README.md)
- [R2 — Shared controller](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/controller.py)
- [R3 — Backend contract](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/platforms/base.py)
- [R4 — Frame ownership and geometry](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/frames.py)
- [R5 — Safety validation](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/safety.py)
- [R6 — MCP server and request handling](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/mcp_server.py)
- [R7 — Publishing workflow](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/.github/workflows/publish.yml)
- [R8 — macOS adapter](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/desktop/platforms/macos.py)
- [R9 — Development and native fixture guidance](https://github.com/ethanramli/computer-use/blob/c089d001c3c0eec267948d3dcb4587bfa59290e5/docs/development.md)
- [R10 — Existing tests](https://github.com/ethanramli/computer-use/tree/c089d001c3c0eec267948d3dcb4587bfa59290e5/tests)

### Official implementation documentation to consult

- [MCP specification](https://modelcontextprotocol.io/specification/)
- [MCP Rust SDK](https://github.com/modelcontextprotocol/rust-sdk)
- [Tokio](https://docs.rs/tokio/latest/tokio/)
- [Serde](https://serde.rs/)
- [XDG RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
- [XDG ScreenCast portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
- [Windows screen capture](https://learn.microsoft.com/en-us/windows/uwp/audio-video-camera/screen-capture)
- [Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- [Android AccessibilityService](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService)
- [Android MediaProjection](https://developer.android.com/media/grow/media-projection)
- [Google Play accessibility API policy](https://support.google.com/googleplay/android-developer/answer/10964491)
- [Apple runtime process security](https://support.apple.com/guide/security/security-of-runtime-process-sec15bfe098e/web)
