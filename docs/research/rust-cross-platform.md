# Rust migration and cross-platform feasibility

Research date: 2026-09-19. Repository baseline inspected:
`c089d001c3c0eec267948d3dcb4587bfa59290e5`.
This is an architecture and migration research result, not an implemented or
natively verified Rust port.

## Answers to the six requirements

1. **Convert to Rust:** port the controller, validation, frame ownership,
   movement mathematics, CLI, and MCP service into a Cargo workspace. Replace
   native integrations incrementally behind provider interfaces. Preserve a
   compatibility facade while moving implementation; do not translate every
   subprocess invocation literally.
2. **Make the library flexible across OSes:** keep OS types outside the public
   domain API, compile native providers per target, and discover permissions and
   session capabilities at runtime. Linux must distinguish X11 from Wayland.
3. **Keep the functions:** retain all 20 existing commands and their documented
   safety semantics. A supported command can still return `unsupported` on a
   particular configuration, as the current backend contract already permits.
   Successful execution of every function on every OS is a stronger requirement
   that available platform APIs do not establish.
4. **Reduce dependence on one program:** separate capture, input, window/focus,
   and accessibility providers. Make the core usable as a Rust library and via
   a language-neutral local protocol. Optional persistent worker programs can
   implement providers; no single third-party automation program must implement
   everything.
5. **Keep a single backend:** one logical backend/service, command contract,
   policy engine, and scheduler is feasible. One identical native implementation
   or executable binary across all OSes is not. Platform-specific code remains
   behind the common backend, and builds are produced per OS/architecture.
6. **Research OS behavior:** the platform and dependency findings below use
   platform documentation, protocol specifications, and upstream projects.
   Recommendations are design inferences, not claims of native testing.

The practical constraint is therefore: **one shared Rust backend composed of
replaceable platform providers, with explicit capability reporting**. If “same
functions on all OSes” means guaranteed unrestricted success on every OS,
including mobile, that combination of constraints is infeasible. Returning an
honest unsupported result preserves the interface but does not constitute full
functional parity.

## What the repository actually contains

The source is more authoritative than the historical protocol documents, some
of which still describe proposals or obsolete implementation status.

| Current source | Rust responsibility |
|---|---|
| `desktop/controller.py` | Shared action orchestration, focus gates, observation, receipts, batching and cancellation |
| `desktop/safety.py` | Typed request validation, parameter limits, risk and confirmation gates |
| `desktop/protocol.py` | Compatible `ok`, `error`, and partial-result envelopes |
| `desktop/frames.py` | Capacity-one frame ownership, geometry, byte budgets, encoding and temporary-file lifecycle |
| `desktop/move.py`, `desktop/timing.py` | Seeded distorted-Bezier paths, Fitts timing and typing timing |
| `desktop/platforms/base.py` | Provider interfaces and explicit capability/focus/cancellation failures |
| `desktop/platforms/macos.py`, `native/cghelper.c` | Native macOS integration |
| `desktop/platforms/windows.py`, `desktop/platforms/linux.py` | Currently unsupported platform placeholders |
| `desktop/cli.py`, `desktop/mcp_server.py` | CLI and persistent MCP transports |
| `setup.py`, installer and release workflow | Target-specific Rust packaging and installation |
| `skills/` | Agent instructions retained as documentation |

The current dependency is not a single browser or application. macOS uses MSS
for capture, a bundled C helper for input/AX metadata, and `osascript`/`open`
for parts of app management. `_run()` starts a helper subprocess for each
invocation. The MCP controller is persistent, but native operations still incur
process startup. `setup.py` declares MSS on macOS; adding a broad automation
framework solely to replace it would not automatically simplify the system.

The untracked root `plan.md` already proposes a broader protocol redesign and
cross-device transport. Those are separate changes from this research request.
In particular, remote access conflicts with the current local-only project
scope, and deferring batches as an optional extension would fail existing
function parity. This report does not adopt those expansions as migration
requirements or modify that file.

## Recommended module and process boundaries

```text
Rust callers       CLI / MCP / other language clients
      \                        /
       shared controller and command contract
       validation, focus policy, motion, frames,
       ordered input, cancellation, result verification
                           |
                  composed DesktopBackend
             /          /         \          \
         Capture      Input      Windows   Accessibility
                           |
          macOS | Windows | Linux X11 | Linux Wayland
```

Keep the workspace under `desktop/` to preserve the repository's architecture
rule. Suggested crates are `desktop-protocol`, `desktop-core`,
`desktop-platform`, and `desktop-service`; split platform crates when their
dependency graphs justify it. Pure policy and motion modules belong in core.
The CLI and MCP binaries can live in the service crate.

Expose domain types such as `DisplayLayout`, `ObservationId`, `Target`,
`InputEvent`, `CapabilityState`, and `ActionReceipt`. Provider traits should
cover capture, input, windows/focus, and accessibility. Keep native handles,
COM objects, Objective-C objects, PipeWire buffers, and X11 connection details
inside providers. Do not require every native object to be `Send + Sync`;
dedicated threads can own thread-affine objects and process bounded messages.

Use one ordered input executor per controlled graphical session. Capture may
run concurrently only with explicit synchronization around frame ownership and
action verification. Give cancellation a separate control path so a saturated
action queue cannot delay stop. Preflight the whole batch before action zero,
then recheck dynamic focus, permissions, frame validity and cancellation at
each required boundary.

Default to linked provider libraries within one persistent process. If a native
API can hang or crash, isolate that provider in a persistent child process with
inherited local pipes, bounded messages, request IDs, deadlines and explicit
shutdown. Do not spawn one helper per click. Do not split each verb into an
independent daemon with its own input state.

A worker restart invalidates its observations and pending input. If it dies
after dispatch, report partial or unknown delivery and require re-observation;
never replay an uncertain click or text operation automatically. Track held
input and release it on ordinary cancellation/failure. A process kill can defeat
cleanup, so test that separately and report recovery needs honestly.

Several programs can use the same core through the protocol, but they must not
create competing input controllers for the same desktop. Start with the current
single-owner stdio deployment. A future local broker requires explicit client
ownership and an emergency-stop path. It does not require a remote listener.

## OS behavior and resulting constraints

| Platform | Capture/input direction | Focus and inspection | Required limitation |
|---|---|---|---|
| macOS | ScreenCaptureKit or qualified capture provider; CoreGraphics events | AppKit application management and AXUIElement | Screen Recording and Accessibility permissions; preserve secure-input and unknown-state refusal |
| Windows | Windows Graphics Capture; SendInput | Foreground-window APIs and UI Automation | Foreground activation can be denied; injection is constrained by integrity levels |
| Linux X11 | X11 capture and XTEST input | Window-manager integration plus AT-SPI where available | Requires an authorized X session and the relevant extensions; toolkit accessibility coverage varies |
| Linux Wayland | ScreenCast/RemoteDesktop portals, PipeWire, EIS where available | AT-SPI and supported compositor integration | Session grant alone does not prove focus, global cursor position, or inspection availability |
| Other desktop systems/BSD | Potential X11/Wayland providers | Must qualify each environment | Reuse is possible; support is unverified |
| Android | MediaProjection and AccessibilityService through a native bridge | Android accessibility model | A separate touch capability profile; desktop cursor semantics are not automatically available |
| iOS/iPadOS | Platform-specific permitted capture/client capabilities | Sandboxed application environment | No basis for advertising unrestricted cross-app desktop-style control |

### macOS

Apple documents [ScreenCaptureKit capture](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos)
and [AXUIElement inspection](https://developer.apple.com/documentation/applicationservices/axuielement_h).
The inspected `cghelper.c` already posts CoreGraphics events and reads AX
attributes. Retaining that helper temporarily is a migration bridge; an entirely
Rust-owned implementation would replace it with Rust bindings to those system
frameworks. [objc2](https://github.com/madsmtm/objc2) supplies Apple framework
bindings, rather than making Apple's APIs platform-neutral.

Resolve applications generically through native application services and verify
foreground identity after activation. Test permission attribution for the final
installed binary/helper identity; permissions of the Python development setup
do not establish permissions for the new artifact. Apple web pages were partly
JavaScript-only in this research environment, so exact deployment-version and
entitlement choices remain implementation qualification work.

### Windows

[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
returns inserted-event counts and permits injection only into equal or lower
integrity applications. Its error reporting does not identify UIPI as the cause.
Do not interpret successful submission as proof of an application effect.

[SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
has explicit restrictions and may deny activation. Recheck the foreground
window before sending input. Stop when the target cannot be verified; do not
escalate the whole service to evade this constraint.

[Windows Graphics Capture](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture)
and [UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32)
provide separate capture and inspection facilities.
[windows-rs](https://github.com/microsoft/windows-rs) is the native binding option.
Qualify physical/logical pixel transforms, mixed DPI, negative display origins,
keyboard layouts, protected content, locked sessions, and secure desktop
failures. UI Automation is used for targeting/verification; directly setting a
control value would change the real-input contract.

### X11

The [XTEST protocol](https://www.x.org/docs/Xext/xtest.pdf) supports simulated
key, button and pointer events. [x11rb](https://docs.rs/x11rb/latest/x11rb/)
offers Rust X11 protocol access. These allow a provider without requiring an
`xdotool` executable. Keep the X connection alive and check extension support.
X11 support does not establish control of native Wayland applications through
XWayland.

### Wayland: the most important qualification gate

The [ScreenCast portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
provides selected streams through PipeWire and stream metadata. Preserve stream
identity and coordinate transforms; do not assume stream pixels equal global
desktop coordinates.

The [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
negotiates devices and session access. `ConnectToEIS` is available from interface
version 2 and follows session start. Once connected, use EIS exclusively for
input; the portal's older Notify methods then reject input. Coordinate capture
and input within the same authorized session rather than independently creating
unrelated sessions through two libraries.

[EIS/libei](https://libinput.pages.freedesktop.org/libei/) is an input protocol,
not a replacement for focus and accessibility. The
[xdg-activation specification](https://raw.githubusercontent.com/wayland-mirror/wayland-protocols/main/staging/xdg-activation/xdg-activation-v1.xml)
allows the compositor to reject activation, including ineffective tokens.
[AT-SPI state information](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/enum.StateType.html)
can expose active and focused state in participating applications.

Design inference: a portable portal-only provider cannot promise the current
toolkit's complete verified-input contract. Qualify GNOME, KDE and any other
supported compositor independently. Require evidence of target focus, safe
inspection, capture-to-input mapping, current cursor location, and visibly
delivered motion. If those cannot be established, advertise capture or a
restricted capability set and return `unsupported`/`needs_attention` for input.
A cursor drawn into a screenshot is not proof that the real cursor traveled.

### “All OSes” beyond desktops

Android's [MediaProjection](https://developer.android.com/media/grow/media-projection)
requires user consent for capture sessions and handles revocation through its
lifecycle. [AccessibilityService](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService)
can dispatch gestures when the service declares the appropriate capability.
This suggests a Kotlin/JNI bridge to reusable Rust core logic, not automatic
desktop parity. Under the existing mandatory cursor requirement, touch-only
operation needs an explicitly different contract; do not silently substitute it.

Apple documents [sandboxing of iOS/iPadOS apps](https://support.apple.com/en-nz/guide/security/sec15bfe098e/web).
Inference: sharing Rust code does not establish permission for unrestricted
cross-app input. Treat a mobile controller client, a test-harness deployment,
and a generally installable controlled-device agent as different products.
Do not claim universal mobile support from Rust target availability.

## Dependencies: what to use and what to avoid depending on

| Candidate | Role | Decision |
|---|---|---|
| [Enigo](https://github.com/enigo-rs/enigo) | Cross-platform input primitives | Evaluate behind InputProvider; its Wayland/libei support is explicitly experimental |
| [XCap](https://github.com/nashaofu/xcap) | Capture | Evaluate behind CaptureProvider; upstream lists Wayland caveats and recording gaps |
| [ashpd](https://docs.rs/ashpd/latest/ashpd/) | Rust portal access | Candidate for owning the shared Wayland permission/session lifecycle |
| [Official MCP Rust SDK](https://github.com/modelcontextprotocol/rust-sdk) | MCP transport | Prefer over carrying forward the handwritten server; qualify supported clients and protocol negotiation |
| windows-rs, objc2, x11rb | Native API access | Keep target-specific dependencies inside providers |

Enigo does not solve capture, focus policy or accessibility. Its optional xdo
path adds a Linux native dependency; choose features deliberately. XCap's broad
platform description is not a guarantee of every capture scenario. Neither
library removes native permission or session requirements.

Keep third-party types out of public interfaces, pin tested versions and
features, commit the lockfile for shipped binaries, and maintain license
attribution. Evaluate replacements against the same provider tests. Do not
automatically switch input providers after uncertain delivery. Do not use an
alternative provider to bypass denied permissions.

Rust removes the Python runtime requirement only once all production paths have
been migrated. It does not remove OS frameworks, graphical-session services,
portal backends or PipeWire. Separate binaries can reduce crash coupling but
increase packaging and IPC costs. Prefer modular libraries first; split processes
when measurements or native API isolation justify them.

## Complete existing-command preservation map

Inventory taken from `Controller._dispatch`, `safety.KNOWN_OPS`, and the MCP
schema. These are 20 public commands, including `stop` handled separately.

| Commands | Rust implementation and acceptance evidence |
|---|---|
| `observe` | Capture/frame store; regions, metadata-only and path modes, direct MCP image content, bounded memory and stale-frame rejection |
| `list_apps`, `list_windows`, `active-window` | Window provider; genuine data or explicit unsupported result; preserve current distinction between implemented and optional operations |
| `focus_app`, `launch` | Generic app lookup/activation plus verified foreground identity; a spawned process alone is insufficient |
| `move`, `click`, `double-click`, `right_click` | Shared motion and input provider; fresh coordinate authorization and visible travel before dispatch |
| `drag`, `scroll` | Same motion requirement; ordered events, correct button lifecycle, direction and units |
| `type`, `click_type` | Focus and sensitive-state gates, Unicode, explicit risk, timing, and honest insertion/effect receipts |
| `press`, `hotkey` | Key names/aliases, blocked combinations, visible cue, verified target, release on interruption |
| `wait` | Cancellable monotonic wait; no arbitrary sleeps added elsewhere |
| `batch` | Complete validation before dispatch, nested limits, deadlines, dynamic checks, partial receipts and cancellation |
| `stop` | Reachable cancellation control; preserve honest distinction between persistent service and standalone CLI |
| `doctor` | Actual provider availability, permissions and recovery instructions; do not make MSS/helper presence a universal requirement |

Preserve request names, parameter validation, JSON envelopes, CLI dry-run
defaults and exit-code meanings through a compatibility layer. Extract exact
response fixtures from the current implementation rather than old prose.
Stronger safety behavior or revised schemas require explicitly recorded changes.

The shared core must retain all repository invariants: no model calls, no
app-specific branches, local-only operation, confirmation gates, secret-free
logs, emergency stop, focus checks, capacity-one image retention, and visible
seeded distorted-Bezier movement before every input category. Inspection
unavailable must not silently mean safe. Accessibility targeting still resolves
to OS input rather than skipping the required physical-input path.

Seed compatibility requires care: Python's `random.Random`, integer sampling,
and rounding are not automatically equivalent to Rust `rand` and `round`.
Freeze representative path outputs. Either reproduce the existing generator
and rounding behavior for legacy seeds or version the movement algorithm and
document changed trajectories. Keep the existing movement-model attribution.

## Migration sequence and release evidence

1. **Freeze the actual contract.** Inventory every command, parameters, errors,
   result fields, helper responsibilities and safety invariant. Use existing
   tests as behavior evidence, separating intended behavior from defects.
2. **Port pure logic.** Add Rust types, validation, motion, timing, geometry and
   frame budgeting. Use checked arithmetic for image dimensions and allocation
   budgets. Test parity with synthetic, non-sensitive fixtures.
3. **Build the persistent runtime with a fake provider.** Implement bounded
   admission, ordered execution, cancellation, frame ownership, all commands,
   partial receipts and CLI/MCP facades. Keep stop independent of the work queue.
4. **Migrate macOS end to end.** A temporary adapter can reuse cghelper for
   comparison. Replace subprocess hot paths with persistent workers or direct
   bindings, then remove Python/MSS/JXA dependencies only after native parity.
5. **Implement Windows and X11; qualify Wayland early.** Keep the same core and
   provider conformance suite. For Wayland, test focus/cursor feasibility before
   promising full parity; capture-only success cannot qualify input support.
6. **Ship native artifacts and retire legacy execution.** Build per supported
   OS/architecture, declare minimum OS versions from tested APIs, provide
   diagnostics and permission recovery, and smoke-test installed artifacts.
   Keep skills and model clients independent of the implementation language.

Required evidence before calling the migration complete:

- All 20 commands exercised against Rust; compatible envelopes and deliberate
  behavior changes recorded.
- Protocol unit/smoke tests plus current relevant regression tests; malformed
  batches execute no native work.
- Native safe-application tests for every advertised OS/session, including
  focus refusal, Unicode/layouts, visible movement, cancellation mid-drag/chord,
  permission revocation and helper failure.
- Geometry tests for negative origins, mixed scaling, rotation and display
  removal; invalidate affected frames before input.
- Bounded capture/encoding/transmission memory and slow-client backpressure;
  no stale screenshot queue or default persistence.
- Separate cold/warm latency measurements for capture, encoding, single input,
  batches, focus verification and cancellation; report distributions and
  failures. Rust alone is not evidence of a speedup, and required motion time
  remains part of latency.
- Release artifacts, not just cross-compilation, demonstrate the advertised
  support matrix. A mock test does not prove native behavior.

This research changed documentation only. No Rust code, desktop actions, native
verification or performance benchmarks were executed. Exact crate versions,
minimum OS releases and compositor support are qualification decisions for the
implementation phase; their absence does not justify a claim of verified parity.

## Requested OpenAI research skill

No `Deepresearch` skill was found in the available skill catalog, local skill
directories, installed plugin paths, or the queried public `openai/plugins`
repository tree. This is a scoped discovery result, not proof that no such
private or separately distributed skill exists. OpenAI documents
[Deep Research via the Responses API](https://developers.openai.com/api/docs/guides/deep-research),
but that API is not an available research tool in this session. The available
OpenAI Docs skill was used to check this distinction. Research here used direct
web searches, upstream source material and local repository inspection; it does
not claim to have run an OpenAI Deep Research job or a Google-specific tool.

## Research completion audit

| User requirement | Evidence delivered | Finding |
|---|---|---|
| How to convert the whole toolkit to Rust | Source-to-module map, 20-command inventory, migration sequence and release gates | Feasible with incremental native replacement |
| Flexible across OSes | Platform matrix, provider boundaries and permission/session behavior | Feasible as an extensible capability-based library |
| Same functions | Complete preservation map and compatibility requirements | Same interface feasible; universal successful execution is not established |
| Less dependence on one program | Dependency evaluation, library/protocol access and persistent-worker design | Feasible without independent competing controllers |
| Single backend | One shared controller with target-specific providers | Feasible logically; identical native implementation everywhere is infeasible |
| Research unknown OS behavior | Linked primary specifications/vendor/upstream sources, explicit limitations | Research complete; native implementation qualification remains future work |
