# Rust migration audit

Updated: 2026-09-22. This is a live audit of the imported `plan.md` against
the repository instructions, `README.md`, the Rust research, and the current
worktree. The plan remains proposed and has not been edited.

## Baseline

- Repository: `computer-automation`; baseline commit: `c089d001c3c0eec267948d3dcb4587bfa59290e5`.
- Existing user changes were present in `AGENTS.md`, `README.md`,
  `docs/protocol/README.md`, and `docs/research/README.md`; imported user
  documents included `plan.md`, `docs/protocol/observation-batching.md`, and
  `docs/research/rust-cross-platform.md`. They were preserved and are now
  tracked with the migration.
- No Rust workspace or Rust source existed at the start of this migration.
- Baseline Python suite: `python3 -m pytest -q` — 301 passed before the
  migration safety correction.
- Current Python suite after the fail-closed safety correction:
  `python3 -m pytest -q` — 311 passed after the Python final-observation
  implementation (one opt-in live desktop test is skipped by default).

## Scope decisions

| Plan proposal | Repository contract | Migration decision |
|---|---|---|
| Authenticated cross-device transport and device pairing (M3) | Local-only controller; no remote-control listener or implicit network access. | Out of scope. Do not open sockets, add remote pairing, leases, client ownership, or cross-device protocol. |
| New language-neutral protocol v0.1 replacing the command contract | Preserve the existing 20 CLI/MCP commands, names, parameters, JSON behavior, dry-run defaults, and cancellation semantics. | Preserve the live CLI/MCP contract. New internal Rust types may be typed, but no public replacement protocol without a documented, justified compatibility change. |
| Project metadata names `ethanramli/computer-use` | Current repository is `computer-automation`. | Treat the plan as an imported proposal, not authoritative project identity. |
| Authenticated Ubuntu/Wayland cross-device proof (M3) | Native Linux/X11/Wayland adapters remain explicitly unsupported until implemented and verified. | Local native adapter work and honest capability reporting are applicable; remote proof is excluded. Another developer owns non-macOS host testing. |
| Batch `final_observe` is placed under optional extensions (M5). | Current `AGENTS.md` and `docs/protocol/observation-batching.md` explicitly request this local MCP behavior. | In scope; implemented in Python and Rust with one optional final image, no fixed delay, and same-response MCP image delivery verified. |
| Remove Python once Rust is ready | Python remains the usable implementation during migration. | Keep Python commands/install path intact until Rust CLI/MCP and required native behavior pass compatibility and host verification. |

## Current implementation evidence

- Python already implements the full local 20-command contract and local
  stdio MCP server, with macOS as its only implemented native adapter.
- The one-shot CLI is dry-run by default; the persistent MCP server executes.
- Coordinate authorization, batch preflight, visible seeded Bezier movement,
  safety confirmation, request cancellation, partial receipts, and capacity-one
  frame ownership live in the Python controller/policy modules.
- Standalone and batch-final MCP observations carry PNG content in memory.
  The batch captures once after terminal action status; observation failure is
  separately reported without erasing action receipts. Python controller/MCP
  tests verify successful, partial-action-failure, and capture-failure behavior.
- The existing safety policy allowed `None` focused-element metadata after app
  focus verification. That contradicts the current requirement that unknown
  state is not safe. A public-controller regression now rejects this state
  before any input; Python and Rust must retain this fail-closed rule.
- A conversion-level regression exposed batch risk/confirmation fallback being
  applied to non-input actions during whole-batch preflight, even though those
  fields are only valid for input actions and runtime applies them there. A
  `wait` followed by `scroll` with batch-level `risk: none` reproducibly failed
  preflight three times in Python before the fix. Both Python and Rust now scope
  the inherited fields to input commands and nested batches, with public
  controller and Rust conformance regressions.
- Rust now implements the shared local controller contract, all 20 public
  command names, validation, confirmation gates, focus and accessibility
  checks, signed multi-display geometry, capacity-one frame ownership, private
  path mode, seeded motion and timing, native action dispatch, honest partial
  receipts, deadlines, request cancellation, CLI parsing, and the bounded
  persistent stdio MCP adapter. Standalone observation and batch
  `final_observe` return direct MCP image content without retaining an image
  queue.
- Rust conformance covers every pointer variant, including `double-click` and
  `right_click`, and asserts that dispatch follows the visible travel event.
- The macOS provider uses the existing native helper for permissions,
  accessibility metadata, capture, cursor movement, pointer input, Unicode
  typing, key chords, and cleanup. Generic AppKit/JXA calls provide active app,
  application listing, focus, and launch behavior. Windows, X11, and Wayland
  select the explicit unavailable provider.
- A live macOS check initially reproduced a host-specific Accessibility failure:
  the system-wide focused-application AX query returned `kAXErrorCannotComplete`
  while an app-scoped query succeeded. The native helper now falls back to the
  frontmost window owner for that query and still fails closed when both paths
  are unavailable. Strict C compilation and live focused-element inspection
  pass after the change.
- A Python/Rust differential check produced exact JSON and exit-code matches
  for the 19 non-`doctor` dry-run commands. `doctor` keeps the same four check
  keys but deliberately reports native Rust capture in the `mss` check message
  because MSS is not a Rust dependency.
- `cargo test --workspace` passes 43 Rust unit, contract, CLI, MCP, provider,
  cancellation, and path-lifecycle tests. `python3 -m pytest -q` passes all 311
  Python tests. Clippy with warnings denied, rustfmt, Python compilation, strict
  C syntax checks, the Python wheel smoke, the side-by-side Rust release
  installer, live read-only macOS capture, live MCP image delivery, and private
  path cleanup all pass on this host.
- GitHub Actions Ubuntu regression run `35724606118` passes the Python suite,
  Python compilation, Rust formatting, Clippy, and the locked Rust workspace
  tests. Its predecessor exposed a Python-version difference in deeply nested
  JSON parsing; the MCP server now applies an explicit structural depth bound
  before deserialization and returns the documented parse error consistently.
- `install-rust-preview` packages optimized Rust binaries and `cghelper` under
  separate `desktop-rust` and `computer-mcp-rust` names. The regular Python
  commands remain the default while external non-macOS host evidence is
  collected.

## Milestone status

- **M0.1** Current branch/worktree/baseline inspection: done; this note records
  the scope conflicts and current differences.
- **M0.2** Existing Python tests: 301 passed at baseline; 302 passed after the
  fail-closed correction; 311 passed after the Python final-observation slice.
  Rerun at each compatibility milestone.
- **M0.3–M0.7** Contract inventory and deterministic provider work: complete for
  the existing local command contract.
- **M1** Rust runtime and mock backend: complete for the applicable local scope.
  Remote session identities, leases, deduplication, and cross-device admission
  remain excluded because they would change the authorized local-only scope.
- **M2** Rust macOS provider, native parity, installed package and MCP smoke:
  complete on this host. The approved live check exercised Rust launch/focus,
  metadata observation, visible move/click/drag/scroll, Unicode typing,
  `click_type`, `press`, `hotkey`, request cancellation, emergency `stop`, and
  batch `final_observe` image delivery. Python remains the installed default
  until the non-macOS handoff is complete.
- **M3** Remote transport and pairing: excluded. Local native-provider work and
  non-macOS host evidence remain separately required and unverified.
- **M4** Cross-platform native implementations and release hardening: the local
  Rust release preview and release-test gates exist. Non-macOS native adapters
  and host evidence remain assigned to the other platform developer.
- **M5** `final_observe`: complete in Python and Rust, including terminal capture
  after successful or partial batches and same-response MCP image delivery.

## Required remaining evidence

1. On each non-macOS target host, run the commands below, implement the provider
   behind `DesktopBackend`, and add native receipts before changing its support
   status. Compilation and mock results alone do not establish support:

   ```bash
   cargo test --workspace --locked
   cargo fmt --all -- --check
   cargo clippy --workspace --all-targets -- -D warnings
   python3 -m pytest -q
   cargo run --bin desktop -- doctor --execute
   DESKTOP_FAKE_BACKEND=1 cargo run --bin desktop -- active-window
   ```

2. Record the host OS/session type, permission state, commands exercised,
   receipts, cancellation result, and unsupported capabilities. Linux Wayland
   must be tested through its real compositor/portal session; Windows and X11
   require their own native sessions. Do not report any of them as supported
   from the current macOS evidence.
3. Keep the local-only scope. Cross-device transport, listeners, pairing,
   leases, and remote authorization remain unresolved proposal work and were
   intentionally not added.

## Live macOS evidence (2026-09-22)

- Created a `0600` temporary TextEdit document and confirmed `active-window`
  plus `doctor` before input. Rust `launch` and `focus_app` reported verified
  TextEdit focus.
- Through one persistent Rust MCP process, `move`, `click`, `drag`, `scroll`,
  `type`, `click_type`, `press`, and `hotkey` returned successful receipts after
  visible cursor travel. `verify:"focus"` returned `true`; TextEdit's
  accessibility element did not expose a value, so effect verification remained
  `null` rather than claiming proof.
- A matching `notifications/cancelled` sent after the request became active
  returned `cancelled`; an out-of-band `stop` returned `stopped:true` and
  cancelled its active wait. A cancellation sent before a queued request began
  was intentionally not treated as an active-request cancellation, matching the
  request-scoped controller behavior.
- A batch with one coordinate action and `final_observe:{"image":true}` returned
  completed receipts plus exactly one PNG MCP image block in the same response.
- The temporary document, screenshot, and MCP process were cleaned up. No user
  document was saved or modified.
- The opt-in regression command
  `COMPUTER_AUTOMATION_LIVE_TEST=1 python3 -m pytest -q tests/test_final_regressions.py -k live_native_helper`
  passed after opening and closing its own temporary document; the default test
  suite keeps that desktop check skipped unless explicitly enabled.
