# Computer Automation

A local, model-agnostic toolkit that lets AI agents observe and control the
whole desktop through real operating-system input. Browsers, terminals,
editors, native applications, and OS surfaces use the same command contract.

The macOS backend is implemented. Windows, X11, and Wayland adapters currently
return structured `unsupported` errors until they can be implemented and
verified on those operating systems.

## Install

```bash
git clone https://github.com/ethanramli/computer-automation.git
cd computer-automation
./install
desktop doctor
```

When the fallback `pip --user` install puts scripts outside `PATH`, the
installer exposes `desktop` and `computer-mcp` through `~/.local/bin` if that
directory is already on `PATH`. It never replaces an unrelated existing file.

On macOS, `doctor` reports the native helper, Accessibility permission, Screen
Recording permission, and MSS separately, with recovery guidance for each.

Configure any MCP client to keep `computer-mcp` running as a local stdio
process:
```json
{
  "mcpServers": {
    "computer": {
      "command": "computer-mcp"
    }
  }
}
```

The installed `desktop` CLI defaults to dry-run. `computer-mcp` is the normal
execution path because one persistent process preserves frame state, serializes
input, and can process request-scoped cancellation while work runs.

## Update

```bash
git pull
./install
```

Then restart the MCP client so the new `computer-mcp` process loads.
Compare `desktop doctor`'s reported version against the latest GitHub
release to see whether an update exists.

The Rust migration can be installed beside the Python commands while native
verification is underway:

```bash
./install-rust-preview
desktop-rust doctor --execute
```

This preview uses separate `desktop-rust` and `computer-mcp-rust` names. The
regular install remains available throughout the migration.

## Agent workflow

1. Call `observe` in a persistent MCP session.
2. Check the active window and retain the returned `frame_id` and display
   layout.
3. Send one small action or a fully preflighted batch through that same
   session. A batch can request one final screenshot in the same MCP response
   as its action receipts with `final_observe: {"image": true}`.
4. Use the observation to verify the result. Request another one only when
   needed to choose or authorize a later action.

Coordinate input requires a fresh frame from the same controller process. The
one-shot CLI therefore refuses executed coordinate actions rather than
pretending that an earlier process's frame ID is valid.

Every input command carries an explicit `risk`:

```json
{
  "command": "type",
  "params": {
    "text": "hello",
    "app": "TextEdit",
    "risk": "none"
  }
}
```

Allowed risk categories are `none`, `deletion`, `purchase`, `message`,
`publishing`, `permission`, and `account_security`. Consequential actions need
the matching category and literal `"confirm": true`. Keyboard input also needs
an explicit target application and a verifiable, non-secure focused UI state.

## Safety and lifecycle

- Every input action moves the cursor visibly along a human-like path before
  executing. The cursor never teleports.
- Whole batches, including nested batches, are validated before action zero.
- Coordinates are authorized against a fresh capture region and complete
  display geometry, including signed origins, scale, and rotation.
- Password, payment, permission, CAPTCHA, challenge, and other secure UI stops
  with `needs_attention`; the controller never guesses or bypasses it.
- MCP `notifications/cancelled` targets the active request and interrupts waits
  and native primitive loops. Held keys and buttons are released on failures.
- The controller opens no socket and has no filesystem stop flag.
- One capacity-one screenshot store owns capture bytes. Path mode atomically
  replaces one owner-private temporary file and removes it at shutdown.
- MCP observations return screenshots as direct image content, keeping image
  bytes out of the JSON text envelope.
- Batch `final_observe` can return one final screenshot as MCP image content;
  observations within the action sequence remain metadata-only.
- Logs and receipts omit typed text, secrets, credentials, and screenshot data.

## Repository layout

```text
desktop/       controller, protocol, MCP/CLI adapters, frame store
  platforms/   platform contract and OS-specific adapters
native/        reproducible macOS helper and receipt-fixture sources
skills/        agent instructions only; no executable control logic
tests/         protocol, safety, lifecycle, and platform-contract tests
tools/         development and benchmark utilities
benchmarks/    generated benchmark output (ignored by Git)
docs/          current guides plus dated design and review records
```

The shared controller imports only the platform contract. OS-specific focus,
accessibility, capture, and input behavior stays inside adapters.

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q desktop tests
python3 tools/benchmark.py --samples 200 --runs 5
```

See [the development guide](docs/development.md) for packaging, protocol smoke
tests, and the native receipt fixture. The test total is intentionally not
copied into documentation; the test runner is the source of truth.

## Non-goals

- No stealth, persistence, remote-control listener, or credential collection.
- No app-specific automation branches.
- No CAPTCHA or challenge bypass.
- No unbounded screenshot or action history.
- No claim of successful effects that the controller could not verify.
