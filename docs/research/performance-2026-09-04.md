# Archived performance and project record — 2026-09-04

> Historical evidence only. Paths, status claims, and test counts below describe
> the 2026-09-04 worktree and are not the current product contract.

Source of truth for project decisions. Code must match this wiki. If code and wiki differ, fix the code or update the wiki in the same change.

## Overview

Computer Automation is an OS-level, cross-platform desktop-control toolkit for any OS that installs this repo. An agent observes the whole computer and operates it through real OS mouse and keyboard events. This is not a browser tool.

The controller is local and model-agnostic. It works offline. It controls browsers, terminals, editors, design tools, and native apps.

## Rules

- One domain per folder under `.wiki/`.
- One decision round per `part-N.md`. Never append to an existing part. New round = new file.
- Keep procedures as vertical lists.
- Record facts before implementation.
- Ask when requirements are unclear. Do not infer missing behavior.

## Directory tree

```text
.codebase/
  README.md
  pyproject.toml
  bin/desktop
  bin/cghelper
  csrc/cghelper.c
  desktop/
    protocol.py
    state.py
    capture.py
    input.py
    move.py
    platforms/
      macos.py
      windows.py
      linux.py
  tests/test_protocol.py
  tests/test_execute.py
.wiki/
|-- wiki.md
|-- protocol/
|   |-- part-1.md
|   |-- part-2.md
|   |-- part-3.md
|   `-- part-4.md
|-- safety/
|   `-- part-1.md
|-- architecture/
|   |-- part-1.md
|   |-- part-2.md
|   |-- part-3.md
|   `-- part-4.md
`-- research/
    |-- part-1.md
    |-- part-2.md
    |-- part-3.md
    |-- part-4.md
    `-- part-5.md
`-- goal/
    |-- part-1.md
    `-- part-2.md
```

## Domains

- `protocol/` — CLI commands, JSON results, exit codes.
- `safety/` — validation, stop control, confirmation gates, logging.
- `architecture/` — controller layout, platform adapters, skills and tests.
- `research/` — vendor-neutral findings with sources. Part 5 ports the distorted-Bezier mouse model (MIT).
- `goal/` — definite v0.1 target. Part 1 base goal, part 2 whole-computer scope. Challenge UI stops with `needs_attention`. No bypass.

## Project status

**FINAL (2026-09-04, completion ruling applied): macOS complete; Windows/
X11/Wayland blocked on unavailable hardware.**

- Verified test count: **137 passing** (three consecutive green runs).
- macOS scope fully implemented and live-smoked: controller, MCP stdio
  server (`computer-mcp`), CLI (20 verbs, dry-run default), capacity-one
  frame store, safety gates, confirmation gates, timing modes, batch with
  receipts, honest stop semantics, effect verification, receipt fixture.
- Traceability: `.wiki/architecture/traceability.md` (final).
- Decision records: `.wiki/architecture/controller-mcp-frames.md`, review logs under
  `.wiki/reviews/`, live smoke logs round 1-2, receipt-window benchmark doc.
- Cross-platform: adapters return structured `unsupported` capability
  errors (contract-tested); implementation is blocked on hosts — see
  traceability rows W1/L1/L2 for exact repro and unblock requirements.

Earlier milestones: live OS cursor via cghelper; move out-and-back verified
by position read; research report (below) unchanged.

## Performance research — 2026-09-04

### Executive summary

The largest current latency is deliberate waiting and process creation, not JSON.
Every `desktop` call starts Python. A macOS action then starts `cghelper`, and
focus lookup starts JXA through `osascript`; focus polling can repeat that spawn.
On the current M1 test host, a warmed one-shot no-op CLI call measured 41.910 ms
median, a one-shot trust check through `cghelper` measured 14.548 ms, and the
complete `desktop active-window` path measured 99.598 ms. Small JSON
encode/decode measured 0.005 ms median. These measurements are not competitor
benchmarks, but they establish the order of magnitude inside this repository.

The minimum architecture that removes the repeated overhead is one persistent
controller process. An MCP client should launch it once over stdio; that process
should own one capture backend, one ordered input executor, current focus state,
and cancellation state. Keep the one-shot CLI for compatibility. Do not add a
daemon, socket, named pipe, HTTP server, worker pool, or new serialization format
until a concrete client needs it and a benchmark proves it helps.

The other dominant latency is configured pacing. The movement formula adds about
0.72 seconds at 100 px and 1.14 seconds at 1,000 px. The configured typing
distribution has an expected gap of 123.37 ms per character. The native helper
also sleeps 80 ms after `click_type`, 50 ms after every scroll tick, and after the
last move and typed character. Pacing that exists for human appearance rather
than OS correctness should be explicit and opt-in. Compatibility pacing may
remain as a backend setting when measurements show a target drops events without
it. Safety delays, confirmation gates, focus checks, and emergency stop must not
be removed for speed.

The accepted v0.1 record currently requires Fitts/minimum-jerk human movement.
This report does not silently override that contract. The opt-in pacing proposal
must be adopted in a new decision part before implementation; until then,
benchmarks should measure both the accepted default and the proposed native-speed
mode.

For screenshots, retain MSS as the portable baseline, reuse one `mss.MSS()`
instance, capture the smallest verified region, and keep raw/encoded data in
memory until the protocol adapter decides its representation. The current path
converts BGRA to RGB, encodes PNG, writes and `fsync`s a file named `.jpg`, and
hides every capture error. On this host, a persistent 800x600 raw MSS grab
measured 5.426 ms median; default-level PNG encoding of one representative frame
measured 27.667 ms. Encoding and payload size must be optimized together.

No claim is made that this project is faster than PyAutoGUI, pynput, Playwright,
or any native API. A fair comparison suite is specified below.

### Scope and evidence labels

Audience: maintainers implementing the controller and platform adapters.

Placement: the research brief requires the complete cross-domain evaluation in
this root page. Its recommendations are not accepted architecture decisions;
adopting one requires a new `part-N.md` in the affected domain, preserving the
wiki rules above and the earlier decision record.

Decision: which latency work should be done first without weakening correctness,
safety, local-only operation, or the platform-neutral contract.

Included: process lifetime, capture, input, protocol, batching, focus,
verification, concurrency, platform backends, benchmarks, and result delivery.

Excluded: model inference, model token generation, host scheduling of a model
tool call, network time to a model provider, and visual reasoning inside the
calling agent.

Labels used in this report:

- **Fact** — directly observed in repository code, tests, or authoritative documentation.
- **Measured** — timed on the host described below; not generalized to other machines.
- **Inference** — conclusion drawn from facts or measurements but not yet tested end to end.
- **Recommendation** — proposed change, not current behavior.
- **Open question** — evidence is missing and must be resolved by a benchmark or platform test.

### Model latency versus controller latency

The controller clock begins when a complete request is available at the local
transport boundary and ends when its result is available at that boundary. It
includes parsing, validation, queuing, focus checks, input dispatch, required
verification, capture, encoding, and local delivery. It excludes all time before
the request arrives, including model reasoning and tool selection.

Record three independent spans in an agent integration:

1. `model_ms`: prompt ready to tool request ready. Owned by the model host; outside this project.
2. `transport_controller_ms`: request write start to response read complete. Owned by this project and its local client adapter.
3. `verified_effect_ms`: request write start to the target app or post-action capture proving the result. Shared by the controller, OS, and target app.

Never subtract an assumed model delay from a total. Instrument both boundaries
and report an unknown span as unknown. A persistent controller cannot improve
model latency, but it can make repeated local actions and observations much
cheaper after a model has chosen them.

### Current latency map

```text
model/host (excluded)
  |
  | complete local request
  v
fresh Python process
  -> argparse + imports
  -> validation + planning
  -> optional JXA process for focus
  -> optional cghelper process for native input/read
  -> optional MSS construction + capture
  -> BGRA-to-RGB copy -> PNG compression -> file write + fsync
  -> JSON serialization -> stdout
  |
  v
model/host receives result (controller boundary ends)
```

| Stage | Current evidence | Latency status |
|---|---|---|
| CLI startup | `bin/desktop:1-11` starts Python and imports the command surface for every call. | Measured: 41.910 ms median for `desktop stop`. |
| Dispatch | `bin/desktop:24-225` reparses the complete CLI and walks one large branch chain. | Included in CLI measurement; not isolated. |
| Native helper | `platforms/macos.py:55-68` uses blocking `subprocess.run()` per helper call. | Measured: 14.548 ms median for `cghelper trusted`. |
| Focus lookup | `platforms/macos.py:85-102` starts JXA; `focus_app` may repeat it every 50 ms. | Measured: 99.598 ms median end to end for `desktop active-window`. |
| Input pacing | `move.py:96-117`, `input.py:14-20`, and `cghelper.c:90-91,162-163,175-176,183,206` add waits. | Usually hundreds of ms or seconds; code-derived. |
| Capture | `capture.py:8-18` constructs MSS, uses virtual display 0, grabs, copies RGB, and writes PNG. | Raw persistent capture measured separately below. |
| Encoding/file | MSS 10.2 RGB and PNG paths allocate/copy; file output flushes and calls `fsync`. | Encoding measured; file time deliberately not measured because no screenshot was persisted. |
| JSON | `bin/desktop:14-16` serializes one result. | Measured: 0.005 ms for a representative small encode+decode. |
| Verification | Focus is checked before guarded keyboard input, but action effects are not re-observed by code. | Partial and currently process-heavy. |

### Local measurement snapshot

**Measured**, not a portable performance claim. Host: MacBookAir10,1, Apple M1,
8 GiB RAM, macOS 14.2 build 23C64, Darwin 23.2.0, arm64, Python 3.9.6,
MSS 10.2.0, one 1440x900 display. `Code` was the confirmed active app. All
screen samples remained in memory and were discarded; no screenshot was saved.
Input injection was not executed. Each row used `time.perf_counter_ns()`, dropped
one warm-up, collected 100 samples except JSON (10,000), and observed zero
failures. Model reasoning was excluded from every measurement. `Fresh` rows
started a new process per sample; `persistent` rows reused one initialized MSS
instance or one in-memory RGB buffer. Timestamps are UTC. No benchmark harness
or screenshot file was added; the inline measurement commands discarded their
data, and the temporary import-timing output was removed immediately.

| Benchmark | Start | End | Median | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Fresh `desktop stop` process | 11:35:17.847 | 11:35:22.379 | 41.910 ms | 60.408 ms | 73.577 ms |
| Fresh `cghelper trusted` process | 11:35:22.380 | 11:35:24.350 | 14.548 ms | 39.025 ms | 98.652 ms |
| Fresh `desktop active-window` process | 11:35:24.350 | 11:35:35.270 | 99.598 ms | 146.657 ms | 190.814 ms |
| Persistent MSS raw 200x200 | 11:35:35.321 | 11:35:35.709 | 3.330 ms | 5.185 ms | 5.785 ms |
| Persistent MSS raw 800x600 | 11:35:35.709 | 11:35:36.268 | 5.426 ms | 6.490 ms | 7.010 ms |
| Persistent MSS raw 1440x900 | 11:35:36.268 | 11:35:37.126 | 8.251 ms | 10.831 ms | 12.473 ms |
| PNG bytes 800x600, level 0 | 11:35:37.133 | 11:35:37.234 | 0.946 ms | 1.293 ms | 1.378 ms |
| PNG bytes 800x600, level 1 | 11:35:37.234 | 11:35:38.313 | 10.350 ms | 12.246 ms | 13.674 ms |
| PNG bytes 800x600, level 6 | 11:35:38.313 | 11:35:41.208 | 27.667 ms | 31.602 ms | 36.654 ms |
| Small JSON encode+decode, 109 bytes | 11:35:41.208 | 11:35:41.257 | 0.005 ms | 0.005 ms | 0.005 ms |

For this one screen image, median PNG sizes at levels 0, 1, and 6 were
1,440,773, 418,429, and 382,274 bytes. This demonstrates the tradeoff, not the
best setting: image content and transport change the result. Cold-process state
was not rigorously isolated by flushing OS caches, and these results must not be
used for cross-machine or competitor claims.

### Findings ranked by impact and effort

| Rank | Finding | Expected impact | Effort | Confidence |
|---:|---|---|---|---|
| 1 | Make MCP stdio controller persistent and reuse initialized backends. | Removes tens of ms from every warm command on this host. | Medium | High |
| 2 | Make human-like movement/typing pacing opt-in; remove sleeps after the final event. | Removes hundreds of ms to seconds where native-speed input is valid. | Low–medium | High |
| 3 | Replace repeated `osascript` focus lookup with a native in-process/persistent lookup and event cache, while rechecking immediately before typing. | Removes the largest measured fixed focus cost and narrows the focus race. | Medium | High |
| 4 | Keep screenshots in memory, correct the MIME/extension, and avoid file `fsync` unless a client requires a path. | Removes forced storage I/O and false-success behavior. | Low | High |
| 5 | Reuse one MSS instance; default to a verified region rather than virtual display 0. | Lowers warm capture setup and pixel work, especially with multiple displays. | Low | High |
| 6 | Add one ordered `batch` request with checkpoints and cooperative cancellation. | Amortizes transport/startup and improves throughput without dropping safety gates. | Medium | High |
| 7 | Add a real out-of-band emergency stop before enabling batches. | Safety prerequisite; prevents queued work continuing after abort. | Medium | High |
| 8 | Add platform-native capture/input only where portable backends miss a measured target or capability. | Potential large gain for streaming and accessibility-heavy workflows. | High | Medium |
| 9 | Separate capture, encode, transfer, focus, dispatch, effect, and verification spans in benchmarks. | Makes future optimization decisions reliable. | Medium | High |
| 10 | Change serializer or invent binary metadata framing. | Negligible for ordinary commands based on current JSON measurement. | Medium | High confidence that this is premature |

### Concrete bottlenecks and correctness constraints

1. **Repeated Python startup.** `.codebase/bin/desktop:1-11` loads the CLI and macOS adapter even for a no-op. The one-shot model also makes `desktop/state.py:5-20` process-local frame state disappear after every command.
2. **Repeated helper startup.** `.codebase/desktop/platforms/macos.py:55-68` creates and waits for a child process for every cursor read, click, drag, scroll, type, and key operation.
3. **Repeated JXA startup.** `.codebase/desktop/platforms/macos.py:85-102` starts `osascript` for one property read. `.codebase/desktop/platforms/macos.py:191-226` may repeat that full process inside a 50 ms polling loop. Apple defines `frontmostApplication` as the app receiving key events, so the semantic choice is sound; the process boundary is not.
4. **Race between focus and input.** Guarded typing checks focus, then starts a different helper process at `.codebase/desktop/platforms/macos.py:242-251,277-284`. Focus can change in that gap. App focus also does not prove the intended control has keyboard focus.
5. **Always-on movement delay.** `.codebase/desktop/move.py:96-117` yields about 0.72–1.27 seconds for 100–2,000 px. The formula becomes negative below roughly 2 px because the logarithm is not clamped to a nonnegative movement time.
6. **Always-on typing delay.** `.codebase/desktop/input.py:14-20` has a mathematically expected 123.37 ms gap per character. `.codebase/desktop/platforms/macos.py:148-151` collapses sampled per-key variation to one mean, so it pays latency without preserving the documented distribution. `cghelper.c:90-91` sleeps after the last character before acknowledging completion.
7. **Fixed native sleeps.** `.codebase/csrc/cghelper.c:175-176` delays between double clicks; line 183 waits after click before type; lines 198-206 wait 50 ms for every scroll tick, including the last; lines 160-164 wait after every move point, including the last. Some inter-event delay may be required, but the trailing sleeps cannot improve delivery of a next event that does not exist.
8. **Full virtual-screen default.** `.codebase/desktop/capture.py:10-15` selects `monitors[0]`, which MSS documents as all displays combined. Multi-monitor pixel volume and bounding-box gaps are paid even when the target is one window.
9. **Capture copies and synchronous disk.** `.codebase/desktop/capture.py:15-18` asks for `shot.rgb` then `to_png(output=...)`. MSS 10.2 allocates the RGB frame and its PNG writer flushes and `fsync`s file output. The filename defaults to `.jpg` although the bytes are PNG.
10. **False capture success.** `.codebase/desktop/capture.py:19-22` catches every exception and returns the requested path. A missing permission, malformed region, unavailable display, or encoder failure is therefore reported as success and cannot be distinguished from a slow capture.
11. **No application batch or cancellation.** There is one specialized `click_type`, but no ordered general batch. `.codebase/bin/desktop:79-80` implements `stop` as a success response only; there is no persistent executor to cancel and no emergency hotkey.
12. **Verification is incomplete.** Coordinate commands validate only nonnegative integers at `.codebase/desktop/input.py:23-24`; they do not bind coordinates to a recent frame or screen geometry. State-changing actions do not capture or test postconditions despite `.wiki/goal/whole-computer-scope.md:20`.
13. **Cross-platform dispatch is not implemented.** `.codebase/desktop/platforms/windows.py:1` and `linux.py:1` are placeholders, while `.codebase/bin/desktop:11` imports macOS and calls it directly. Unsupported capability and slow capability are not yet separable on other systems.
14. **Dependency state is not reproducible.** `.codebase/pyproject.toml:1-7` declares no runtime dependencies. The host has MSS 10.2.0, whose `mss.mss()` alias used at `capture.py:10` is deprecated in favor of `mss.MSS()`.

### Proposed low-latency architecture

```text
MCP host
  <-> one long-lived newline-JSON stdio process
        controller: validation, safety, ordering, cancellation, receipts
          |-- one input executor (strict FIFO; never concurrent)
          |     `-- persistent native adapter/handle
          |-- one focus/accessibility adapter + event cache
          `-- one capture owner + latest-frame slot
                 `-- encode/deliver only the requested representation
```

This is the first Ponytail rung that holds:

1. **Primary path:** a persistent MCP stdio server owns the controller directly. The current MCP specification defines stdio as newline-delimited JSON-RPC to one client-launched subprocess. No listening port is needed.
2. **CLI compatibility:** retain one-shot commands, and add a `desktop session` newline-JSON mode only if non-MCP agents need repeated commands in one process.
3. **No daemon by default:** add a broker only when unrelated CLI invocations must share state. Then use an owner-only Unix-domain socket on macOS/Linux and a current-user Windows named pipe that denies network access. Measure first.
4. **No HTTP by default:** Streamable HTTP creates an independent server and one POST per message. If interoperability requires it, bind only `127.0.0.1`, validate `Origin`, and authenticate as required by the [current MCP transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).
5. **One protocol:** keep compact structured JSON for commands and results. Do not put large image bytes inside ordinary action metadata. MCP image content is base64, which expands binary by about one third before JSON overhead; still prefer it to disk when the host accepts direct image content.
6. **One input owner:** queue commands FIFO. JSON-RPC batch itself is not suitable because the [JSON-RPC specification](https://www.jsonrpc.org/specification) permits concurrent, out-of-order processing.
7. **One latest frame:** capture requests are ordered relative to input barriers. Encoding can run separately, but an older encoded result must never replace a newer frame.

The [MCP stdio binding](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
already provides the persistent channel and cancellation message. Custom reliable
byte streams should reuse the same newline framing. This makes a custom binary
protocol, message bus, and database unnecessary.

For macOS, the smallest useful native change is a server mode in the existing
helper rather than a new dependency. It can retain CoreGraphics state and accept
validated framed commands. Correct `NSWorkspace.frontmostApplication` lookup
requires AppKit; implement it in the native adapter so JXA is not started for
every check. Keep Python as the platform-neutral policy layer.

### Safe batching API

One application-level request owns order, checkpoints, and receipts:

```json
{
  "id": "batch-42",
  "method": "desktop.batch",
  "params": {
    "deadline_ms": 2000,
    "verification": "required",
    "actions": [
      {"op": "focus", "app": "TextEdit"},
      {"op": "checkpoint", "focus": {"app": "TextEdit"}},
      {"op": "click", "x": 640, "y": 420, "frame_id": "frame-91"},
      {"op": "checkpoint", "focus": {"app": "TextEdit"}},
      {"op": "type", "text": "hello", "timing": "native"},
      {"op": "checkpoint", "capture": "region"}
    ]
  }
}
```

Result shape:

```json
{
  "ok": true,
  "data": {
    "id": "batch-42",
    "status": "completed",
    "last_completed": 5,
    "receipts": [
      {"index": 0, "status": "ok", "dispatch_ns": 120000},
      {"index": 1, "status": "ok", "focus": "TextEdit"},
      {"index": 2, "status": "ok", "dispatch_ns": 95000},
      {"index": 3, "status": "ok", "focus": "TextEdit"},
      {"index": 4, "status": "ok", "characters": 5},
      {"index": 5, "status": "ok", "frame_id": "frame-92"}
    ]
  }
}
```

Rules:

1. Validate the whole batch before the first event: action count, byte limit, deadline, keys, text length, coordinates, frame geometry, risk classification, and confirmation token.
2. Execute on one FIFO input owner. Do not run two batches against one desktop seat concurrently.
3. Check cancellation and emergency-stop state before every primitive and checkpoint.
4. Treat `focus`, `observe`, `checkpoint`, app switch, and confirmation as barriers.
5. Immediately stop on failed focus, stale frame, changed display geometry, failed expected state, expired deadline, lost permission, backend error, or cancellation.
6. Return `last_completed` and per-step receipts. Never claim rollback: OS events already posted cannot be undone.
7. On every exit path, release controller-held keys, buttons, touches, and drag state.
8. Emergency stop is out of band, not queued behind the work it must stop. Native event loops must check a shared cancellation flag between events and use interruptible waits.
9. Consequential actions—deletion, purchase, message, publish, permission, account, or security changes—still require a fresh confirmation gate at the exact action. A batch cannot pre-authorize an unknown future UI state.
10. Coordinates require a fresh `frame_id` whose display geometry still matches. A batch crossing a visual state change requires another checkpoint.

Safe to combine within one verified state: pointer moves, click down/up pairs,
known scroll ticks, key down/up pairs, a validated hotkey, text events, and an
atomic drag. Focus changes, waits for external work, dialogs, navigation,
cross-app transitions, and consequential actions require barriers. Batching
reduces reliability when the UI can animate, reflow, steal focus, show an
unexpected modal, accept events more slowly than posted, or change coordinate
mapping. Smaller verified batches are faster than recovering from a long stale
batch.

### Focus and verification policy

`verification` selects extra checks; it never disables mandatory ones.

| Level | Intended use | Checks |
|---|---|---|
| `dispatch` | Read-only calls and dry runs only. | Validate request and backend capability. Not allowed for clicks, coordinates, or keyboard input. |
| `required` | Default state-changing actions. | Fresh frame/geometry for coordinates; foreground app immediately before keyboard; post-action focus or requested capture/state predicate. |
| `strict` | Fragile UI and higher-risk workflows. | `required` plus focused element/accessibility identity, state predicate after each meaningful transition, and confirmation gate when consequential. |

Maintain a focus cache from native OS notifications to avoid repeated discovery,
but treat it as a hint. Re-read the authoritative foreground app immediately
before typing. Where available, verify the focused element too. Apple documents
`frontmostApplication` as the app receiving key events, while its activation API
is a request rather than a guarantee. Windows likewise restricts
`SetForegroundWindow`; a zero return or temporary `GetForegroundWindow == NULL`
is a focus failure, not a reason to type into the current app.

Measure these separately:

1. Read already-cached active app.
2. Authoritative active-app lookup.
3. Accessibility focused-element lookup.
4. Focus request dispatch.
5. Time until the target becomes authoritative foreground.
6. Final immediate pre-input verification.

### Screenshot path

Keep MSS as the portable first rung. Its [official usage documentation](https://python-mss.readthedocs.io/latest/usage.html)
supports all-monitor, monitor, and region grabs and says one shared instance
serializes its `grab()` calls. Its [examples](https://python-mss.readthedocs.io/latest/examples.html)
show persistent capture loops, in-memory PNG bytes, and compression control.

Recommended path:

1. Initialize one `mss.MSS()` in the persistent capture owner.
2. Resolve an app/window or verified frame region before capture. Use virtual display 0 only when explicitly requested.
3. Keep the native BGRA buffer as long as the next consumer can accept it; avoid RGB conversion solely as an intermediate.
4. Encode in memory only when the client needs PNG/JPEG. Correctly report MIME and extension.
5. Benchmark PNG levels using encode time plus transferred bytes. Level 0 was fastest locally but produced a much larger payload.
6. Use a temporary current-frame file only for clients that require a path; atomically replace it and never keep history.
7. Return capture failures as structured errors with permission/backend recovery. Never return a nonexistent path as success.
8. Record monitor ID, origin, size, scale, rotation, and capture region with each frame. Negative origins are valid in multi-monitor layouts even though action coordinates need contract-level normalization.

### Screenshot retention and cache budget

This is a hard resource and privacy constraint, not merely an optimization:

- The controller owns a capacity-one latest-frame slot by default. A new frame
  replaces the old one; stale raw buffers, encoded images, and base64 payloads are
  released before another optional observation is accepted.
- Every frame/result path has a byte limit and backpressure. Do not queue an
  unbounded capture loop, image-result list, or retry buffer. Prefer metadata-only
  responses when pixels are not needed.
- Disk is not a history store. If a client requires a path, atomically replace one
  temporary current-frame file and discard it on expiry; never generate
  timestamped screenshot archives by default.
- Observations are explicit requests. Continuous capture is opt-in and must use a
  bounded latest-frame stream with dropped-frame counters and a documented memory
  budget.
- Agent/client conversation history is a separate store outside the controller.
  The client should replace or expire old image results, but the controller must
  not claim to delete history it cannot access.

This policy prevents hundreds of screenshots from accumulating in the local
process while making the external client-retention limitation explicit.

On macOS, MSS 10.2 uses `CGWindowListCreateImage` and copies provider data.
Benchmark a persistent ScreenCaptureKit adapter only after the portable path is
measured. Apple describes [ScreenCaptureKit](https://developer.apple.com/videos/play/wwdc2022/10156/)
as GPU-backed with lower CPU overhead than earlier capture methods, IOSurface
buffers, content filters, and continuous callbacks. Measure its cold stream
setup separately from warm latest-frame retrieval; do not infer still-image
latency from streaming claims.

### Cross-platform backend recommendations

| Platform | Portable first rung | Native rung when justified | Unsupported versus slow |
|---|---|---|---|
| macOS | Persistent MSS for capture; existing helper for CoreGraphics input. | ScreenCaptureKit for measured streaming/copy needs; AppKit/Accessibility for focus and elements; persistent CoreGraphics helper for input. | Missing Screen Recording or Accessibility trust is unavailable. App activation may be denied and must be verified. |
| Windows | MSS/GDI baseline; a small native adapter for foreground state and input. | `SendInput` arrays; UI Automation with bulk caching; Windows Graphics Capture for a window/display; DXGI Desktop Duplication for monitor streams and dirty rectangles. | UIPI, secure desktop, integrity mismatch, unsupported capture, and protected content are capability failures. |
| Linux X11 | MSS 10.2 XShm where available; XTEST for input; EWMH/AT-SPI for window and element state. | Direct XShm/XTEST only if wrapper overhead is measured; keep one Display connection. | Missing XTEST/XShm is unavailable and should fall back; remote X may use slower XGetImage. |
| Linux Wayland | XDG RemoteDesktop + ScreenCast portal, PipeWire, and recommended EIS/libei path. | Compositor-specific support only behind an explicit capability, never in core task logic. | Core Wayland intentionally lacks global cross-client control. Missing portal/EIS grant is unsupported, not “slow.” XWayland control is limited to Xwayland apps. |

Windows `SendInput` accepts an array and inserts those events serially without
interspersing user or other `SendInput` events, but its return only proves
insertion, not target processing. Microsoft documents [UI Automation bulk caching](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-cachingforclients)
because individual property calls cross process and are slow. [DXGI Desktop Duplication](https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api)
provides GPU surfaces plus dirty/move/cursor metadata along monitor boundaries;
it is not a per-window replacement for Windows Graphics Capture.

On X11, Xlib buffers requests asynchronously; an explicit `XSync` is a round
trip. XTEST can submit zero-delay input on one connection, and MIT-SHM avoids
sending large image data through ordinary Xlib IPC when supported. On Wayland,
the [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
requires a user-approved session, recommends `ConnectToEIS`, and can pair with a
[ScreenCast PipeWire stream](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html).
Reuse the approved session; never bypass its consent UI.

### Protocol and transport tradeoffs

| Transport | Use | Advantage | Cost/risk | Decision |
|---|---|---|---|---|
| Persistent MCP stdio | Default MCP integration | Already standard, local, no listener, one server startup. | One shared channel; controller must explicitly serialize desktop work. | Build first. |
| `desktop session` stdio | Repeated non-MCP actions from one parent | Same framing and process lifetime, minimal code. | Parent must keep pipes open. | Add only for a real client. |
| Unix-domain socket | Independent POSIX CLI clients | Local byte stream and filesystem namespace. | Lifecycle, permissions, stale socket cleanup, broker process. | Defer until required. |
| Windows named pipe | Independent Windows CLI clients | Native duplex IPC, ACLs, overlapped I/O. | Windows-specific server code; deny remote access explicitly. | Defer until required. |
| Loopback Streamable HTTP | Clients that only speak HTTP MCP | Multiple independent requests and familiar tooling. | POST/header overhead plus Origin validation, auth, lifecycle, and DNS-rebinding protection. | Optional interoperability path, not fastest-by-assumption. |
| One-shot CLI | Shell compatibility and recovery | Simple and inspectable. | Repeats startup and cannot hold cancellation/current-frame state. | Keep, do not optimize first. |

No source proves a universal latency ordering among stdio, Unix sockets, named
pipes, and loopback HTTP for this workload. Benchmark equal payloads over warm
connections before selecting on speed. Python documents Unix sockets and Windows
supports AF_UNIX, while Microsoft documents named pipes as duplex IPC and warns
that local-only instances must deny network access. HTTP must remain localhost
only per project rules and the MCP security requirements.

### Concurrency, ordering, and backpressure

Use an event loop for stdio reads/writes, deadlines, cancellation, and queue
coordination; it must not run blocking capture or encoding work. One dedicated
capture-owner thread may hold MSS and perform grabs, while a bounded one-job
worker may encode the newest frame. The ordered input actor should talk to the
persistent native helper over a nonblocking pipe; retain one-shot subprocesses
only for CLI compatibility. A separately installed native daemon adds lifecycle
and authentication risk and is not recommended unless independent clients prove
they need shared state. This keeps blocking libraries off the event loop without
introducing a general worker pool.

1. Input and focus mutation are a single ordered actor per desktop seat. Never overlap two input sequences.
2. Capture may run on a separate owner, but a verification frame must be known to follow the relevant input barrier. Injection return is not proof of rendered state.
3. Encoding and result delivery may overlap later controller work only when frame IDs and generation IDs prevent stale publication.
4. Use a bounded FIFO command queue. Reserve an out-of-band stop channel so queue pressure cannot delay emergency stop.
5. Use a capacity-one latest-frame slot for optional observations. Drop an unconsumed stale frame rather than building screenshot history.
6. Apply output backpressure: do not allocate an unbounded number of base64 images or JSON results. Await transport drain/high-water marks.
7. Cancellation is cooperative. Stop before the next primitive, discard only unsubmitted actions, release held input state, and report the last completed index.
8. A native atomic unit cannot be rolled back. On Windows that may be one `SendInput` array; on libei it may be one logical frame; on X11 it is already-flushed XTEST requests.
9. Use monotonic sequence and generation IDs. Reject results captured under an old focus, monitor, or permission generation.

### Benchmark and profiling plan

#### Required record for every benchmark cell

1. Store UTC RFC 3339 `start_at` and `end_at` wall timestamps.
2. Measure durations with `time.perf_counter_ns()` around explicit start/end events. Python defines it as the highest-resolution performance counter for short durations.
3. Record OS name/version/build/kernel, CPU/model/cores, RAM, power source/mode, thermal state, virtualization/remote-session state, Python/runtime, dependency versions, backend name, permissions, and Git commit/worktree state.
4. Record monitor count, resolution, logical/physical coordinates, scale/DPI, rotation, refresh/HDR, cursor inclusion, region, and pixel format where capture is involved.
5. Run separate cold and warm cells. Cold means a newly launched controller/backend; warm means an already initialized process and handles.
6. Use at least 20 unreported warm-ups and 200 reported samples per cell so p99 is not one accidental maximum. Repeat across at least five independent runs. Increase samples if the distribution is unstable.
7. Report median, p95, p99, minimum, maximum, failure rate, and semantic failure/recovery rate. Retain raw values in benchmark artifacts, not this wiki.
8. Mark `model_included: false`. The request-start clock begins only when the complete local request is written.
9. Record payload bytes and output bytes. For images, distinguish raw, encoded, base64, and file path.
10. Keep equivalent safety, focus, pacing, target app, and verification semantics across competitors. If they differ, label the row a microbenchmark, not a winner.

The [pyperf methodology](https://github.com/psf/pyperf/blob/main/doc/run_benchmark.rst)
separates processes, values, warm-ups, outer loops, and inner loops and recommends
enough runs to reduce random effects. Use its approach for pure computation and
serialization. Real input/capture harnesses need the same discipline but custom
event receipts.

#### Benchmark definitions

| Benchmark | Start timestamp | End timestamp | Method and cases |
|---|---|---|---|
| Single click latency | Immediately before client writes request. | Record both target test-app mouse-down receipt and complete response receipt. | Safe local test app; fixed coordinate/frame; dispatch-only and verified-effect spans; 200 cold + 200 warm per backend. |
| Batched click latency | Before one application-level batch write. | Last target receipt, final checkpoint, and response complete. | 1, 2, 5, 10 clicks; report per-click gaps, batch total, clicks/s, and failures. Do not use JSON-RPC batch. |
| Keypress latency | Before request write. | Target key-down receipt and response complete. | Plain key and modifier chord; focus already correct versus focus transition; ensure key-up cleanup. |
| Text-entry latency | Before request write. | Target receives last text/key event and response completes. | 1, 20, 200 characters; ASCII and Unicode; native, compatibility, and explicitly human timing; report chars/s. |
| Screenshot capture | Immediately before backend capture call. | Raw buffer and metadata available. | 200x200, 800x600, one display, virtual desktop, one window; cold setup and warm capture separate. |
| Encode and transfer | Before RGB conversion or encoder call; then before transport write. | Encoded bytes ready; then client has complete decoded result. | BGRA pass-through where possible, PNG levels 0/1/6, JPEG only if added, direct MCP image, and temp-file path. Report size and fidelity checks. |
| Focus verification | Before cached or authoritative lookup. | App ID/name available; separately, focused element available. | Cache, native lookup, accessibility lookup, already-focused, focus request success/failure, and user focus-steal race. |
| End-to-end command | Before request write. | Structured response fully read; separately, verified effect. | One-shot CLI, warm MCP stdio, and any proposed local IPC under identical action semantics. Break down child spans. |
| Safe-batch throughput | Before batch write. | Last verified checkpoint and response read. | Deterministic click/keypress/scroll mixes, batch sizes 1–100, configured checkpoint intervals; actions/s and queue delay. |
| Failure and recovery | Before deliberately induced safe failure request. | Refusal received and next known-good verified command completes. | Wrong focus, stale frame, permission absent, unsupported backend, expired deadline, cancellation, queue full, target closed. Report unsafe events (must be zero), recovery ms, and success rate. |

Use a purpose-built local test window that timestamps received events with the
same system monotonic clock as the controller. A native post call returning is
only `dispatch_ns`; the test window receipt is `effect_ns`; a captured/predicate
postcondition is `verified_ns`. On macOS and Windows, the documented performance
clocks are system-wide. For visual verification, use frame timestamps where the
native backend provides them and a clear state-changing test control.

Profiling tools by phase:

1. `python -X importtime` for diagnostic import attribution only; instrumentation affects timing.
2. `pyperf` for pure path generation, validation, JSON, and encoding microbenchmarks.
3. OS process tracing for spawn/wait counts and CPU/time attribution.
4. Per-command structured spans in the controller: `queue`, `validate`, `focus`, `dispatch`, `effect`, `capture`, `encode`, `transfer`, `verify`.
5. Backend counters: frames dropped, stale generations, cancellations observed, queue high-water, permission failures, and retries.

### Fair comparison plan

| Comparator | Fair scope | Required normalization |
|---|---|---|
| Direct native APIs | Lower-bound dispatch and native capture path per OS. | Add the same validation, focus check, pacing, and verification or label as raw microbenchmark. |
| PyAutoGUI | Cross-platform scripted mouse/keyboard and screenshot. | Report defaults and explicitly tuned settings separately. Its docs specify a default 0.1 s pause after calls and 0.01 s macOS catch-up; keep its failsafe or provide the same emergency-stop semantics. |
| pynput | Mouse/keyboard wrapper only. | Exclude screenshot/focus; pin version/backend. Its docs say Xwayland support is limited and uinput requires root. |
| MSS | Raw capture baseline. | Pin 10.2.0/backend; same region, pixel format, cursor, monitor, raw/encoded boundary, and instance lifetime. |
| Playwright | Browser-only task cohort. | Same browser/task and success condition; do not compare a DOM locator directly to a raw OS event. Include its actionability/auto-wait behavior. |
| Accessibility/UI tree | Semantic desktop control where providers expose it. | Same target and postcondition; report missing/opaque controls separately from latency. |

[PyAutoGUI documents](https://pyautogui.readthedocs.io/en/latest/index.html)
its safety pause and an old illustrative roughly-100-ms 1920x1080 screenshot,
not a universal current benchmark. [pynput documents](https://pynput.readthedocs.io/en/latest/limitations.html)
different backends and significant Wayland limits. [Playwright locators](https://playwright.dev/docs/actionability)
auto-wait for DOM visibility, stability, event reception, and enabled state.
Those semantics can improve reliability while adding waits, so compare complete
browser tasks, not isolated click dispatch.

### Risks and tradeoffs

- A persistent controller reduces startup but introduces lifecycle, stale-state, crash-recovery, and permission-attribution work. Keep state explicit and small.
- Longer batches improve throughput but increase stale-screen exposure and the number of irreversible events after a mistaken assumption.
- Removing human pacing can expose target apps that drop or coalesce events. Provide measured compatibility pacing, not global sleeps.
- Native backends improve capability and may reduce copies, but multiply packaging, signing, permission, and platform test burden. Add only after the portable path fails a target.
- Region capture reduces bytes but can miss popovers, menus, notifications, or monitor changes outside the region. Strict verification may require a wider capture.
- Lossy JPEG can be faster/smaller but can damage small text and visual targeting. It requires model-accuracy and UI-fidelity tests before adoption.
- Lower PNG compression can move cost from CPU to transport. Optimize end to end, not encoder time alone.
- Parallel capture may contend with the compositor and produce stale frames. More threads do not guarantee lower latency; MSS serializes same-instance grabs.
- Focus caches are fast but stale. Mandatory immediate pre-key verification stays authoritative.
- Portal consent, macOS trust, UIPI, secure desktops, protected content, and unavailable compositor interfaces are hard capability limits. Never retry them as if they were transient slowness.
- Direct image delivery avoids disk but MCP base64 allocates and expands the payload. Bound queues and image sizes.
- Benchmark instrumentation and an event-receiving test app can perturb timing. Keep instrumentation identical across candidates and retain raw distributions.

### Phased implementation roadmap

#### Phase 0 — trustworthy measurements and safety gates

1. Add benchmark span definitions and the safe local event-receipt test app.
2. Make capture errors honest; record exact backend and capability.
3. Implement real emergency stop/cancellation and confirmation gates before a general batch.
4. Establish one-shot baselines on macOS and capability-only smoke tests for placeholders.

Gate: all required metadata and median/p95/p99/failure fields are produced;
unsafe events in failure tests are zero.

#### Phase 1 — remove waits that buy nothing

1. Stop sleeping after the last move, scroll tick, and character.
2. Add explicit `native`, `compatibility`, and opt-in `human` timing policies.
3. Clamp movement duration to a valid nonnegative value.
4. Keep required double-click and target compatibility intervals configurable and measured.

Gate: lower verified-effect latency without increased event loss; safety tests unchanged.

#### Phase 2 — persistent controller and capture

1. Put the controller directly in one persistent MCP stdio process.
2. Reuse one `mss.MSS()` instance and return correct in-memory PNG content.
3. Preserve one-shot CLI compatibility; add no daemon yet.
4. Add ordered command IDs, deadlines, bounded queues, and structured timing receipts.

Gate: warm command p95 materially beats one-shot baseline; crash/restart and EOF shutdown recover cleanly.

#### Phase 3 — safe batch and persistent macOS native path

1. Add `desktop.batch` with validation, barriers, receipts, and cancellation.
2. Add persistent server mode to the existing native helper.
3. Replace JXA polling with native AppKit/Accessibility lookup and notifications.
4. Keep an immediate authoritative check before keyboard input and verified regions before coordinates.

Gate: safe-batch throughput improves with zero unsafe post-cancel events beyond the currently executing primitive.

#### Phase 4 — platform adapters

1. Windows: `SendInput`, foreground verification, UI Automation bulk cache, MSS baseline.
2. X11: persistent Display, XTEST, MSS XShm capability/fallback reporting.
3. Wayland: persistent portal session, PipeWire, EIS/libei, explicit unsupported results.
4. Run the same contract and failure suite on every platform.

Gate: unsupported capabilities are explicit; supported commands keep identical JSON semantics and safety rules.

#### Phase 5 — native capture only where proved

1. Compare ScreenCaptureKit with persistent MSS on supported macOS versions.
2. Compare Windows Graphics Capture/DXGI with MSS for equivalent window/monitor workloads.
3. Evaluate zero/low-copy downstream paths only if capture/encode profiles remain dominant.

Gate: a native path ships only with measured end-to-end benefit, acceptable reliability, and a maintained portable fallback.

### Optimization matrix

| Optimization | Expected benefit | Effort | Confidence | Evidence needed before shipping |
|---|---|---:|---:|---|
| Persistent MCP stdio controller | Remove repeated Python/import cost: tens of ms per command locally. | Medium | High | Warm end-to-end benchmark and restart test. |
| Persistent macOS helper | Remove one helper spawn per native operation and narrow focus/input race. | Medium | High | Dispatch/effect latency and cancellation test. |
| Native focus lookup/event cache | Remove repeated JXA process; likely largest fixed focus win. | Medium | High | Authoritative lookup and focus-steal failure suite. |
| Opt-in human pacing | Remove 0.7–1.3 s movement and ~123 ms/char default gaps when not required. | Low | High | Target event-loss and compatibility matrix. |
| No trailing event sleep | Remove one interval from move/type/scroll acknowledgements. | Low | High | Receipt-order and no-drop test. |
| Persistent MSS instance | Reuse native setup and monitor cache. | Low | High | Cold versus warm capture spans. |
| Verified region capture | Fewer pixels; local 800x600 median was 5.426 ms versus 8.251 ms for 1440x900. | Low | High | Multi-monitor/scale/popover correctness. |
| In-memory image delivery | Avoid file flush/`fsync`; prevent screenshot persistence. | Low | High | Encode + base64 + transfer benchmark. |
| PNG compression tuning | Potential large CPU change; payload tradeoff is content-dependent. | Low | High | Representative UI corpus and end-to-end transfer. |
| JPEG mode | Potential size/encode gain but lossy. | Medium | Low | Text fidelity and model targeting accuracy. |
| Ordered safe batch | Amortize fixed costs and improve throughput. | Medium | High | Checkpoint interval, cancellation, and recovery curves. |
| Async encode/latest-frame slot | Hide encoding behind independent work and bound memory. | Medium | Medium | Generation/staleness stress test. |
| ScreenCaptureKit | Potential lower CPU/copies and warm-frame latency on macOS. | High | Medium | Cold/warm equivalent-output comparison. |
| WGC/DXGI | Potential GPU/dirty-region gains on Windows. | High | Medium | Equivalent window/monitor comparison and support matrix. |
| UDS/named-pipe broker | Share warm controller across unrelated CLI processes. | High | Low until needed | Real client requirement and equal-payload transport benchmark. |
| Loopback HTTP | Interoperability, not a presumed speed gain. | High | High | Client requirement, security audit, transport benchmark. |
| Faster JSON/binary metadata | Current 0.005 ms JSON result leaves almost no useful ceiling. | Medium | High confidence to skip | Only revisit if profiles show serialization dominance. |

### Open questions

1. What are dispatch, target-receipt, and verified-effect p95/p99 for real safe clicks and keys after Accessibility trust is enabled?
2. How much time does the current file output and forced `fsync` add on each supported filesystem?
3. Which target apps require compatibility pacing, and at what minimum interval?
4. Does a persistent native helper materially outperform one-shot `posix_spawn` after all validation and verification are equal?
5. Can the model host consume direct MCP image content efficiently, or does it require a file path?
6. What frame timestamp/barrier reliably proves “after action” on each capture backend?
7. At what batch length/checkpoint interval does recovery cost exceed throughput gain for common workflows?
8. Which Windows versions and Wayland compositors form the supported baseline?
9. Does ScreenCaptureKit/WGC/DXGI improve the one-shot observation workload enough to justify packaging and permission complexity?
10. How should a controller authenticate independent local clients if a daemon becomes necessary?

### Sources and stopping point

Primary sources consulted and checked on 2026-09-04 include:

- Repository code, tests, READMEs, AGENTS instructions, and all existing wiki architecture, protocol, safety, research, and goal pages.
- [MSS usage](https://python-mss.readthedocs.io/latest/usage.html), [examples](https://python-mss.readthedocs.io/latest/examples.html), and tagged [10.2.0 source](https://github.com/BoboTiG/python-mss/tree/v10.2.0/src/mss), python-mss maintainers, release 2026-04-23.
- [MCP 2026-07-28 transport overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), stdio, Streamable HTTP, schema, and cancellation pages, Model Context Protocol project, 2026-07-28.
- [JSON-RPC 2.0](https://www.jsonrpc.org/specification), JSON-RPC Working Group, updated 2013-01-04; [RFC 4648](https://www.rfc-editor.org/info/rfc4648/), Simon Josefsson/IETF, 2006-10.
- [Python time](https://docs.python.org/3/library/time.html), subprocess, JSON, socket, asyncio stream/queue, and zlib documentation, Python Software Foundation.
- [ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit), `CGEventPost`, `NSWorkspace.frontmostApplication`, activation, and Accessibility documentation, Apple; WWDC22 ScreenCaptureKit sessions, 2022.
- [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput), foreground-window, UI Automation, Windows Graphics Capture, Desktop Duplication, and named-pipe documentation, Microsoft Learn.
- [XTEST](https://www.x.org/releases/current/doc/libXtst/xtestlib.pdf), Xlib, MIT-SHM, and ICCCM specifications, X.Org/X Consortium.
- [Wayland protocol](https://wayland.freedesktop.org/docs/book/Protocol.html), XDG RemoteDesktop/ScreenCast portal, PipeWire DMA-BUF, and [libei](https://libinput.pages.freedesktop.org/libei/) documentation, Freedesktop projects.
- [PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/), [pynput](https://pynput.readthedocs.io/en/latest/), and [Playwright](https://playwright.dev/docs/intro) official project documentation.

Research stopped when each requested report section had repository evidence and
consequential recommendations had primary support or an explicit empirical gap.
Further web searching would add weaker duplicates; the remaining questions need
the benchmark harness and real platform runs, not more documentation.
