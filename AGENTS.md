# Agent Instructions

## Project purpose

This repository contains an OS-level, cross-platform desktop automation toolkit for any OS that installs it. It gives AI agents controlled access to whole-computer screen observation and real OS mouse/keyboard input. This is not a browser-only project. Browsers, terminals, editors, design tools, and native OS surfaces are all driven through the same OS input path.

## Core principles

- Keep the controller local and model-agnostic.
- Prefer explicit, small, inspectable commands over hidden behavior.
- Optimize for low latency: keep the controller/server process persistent and avoid
  spawning a new process for each desktop action.
- Support safe action batching so multiple deterministic input events can be sent in
  one command, while retaining verification checkpoints after meaningful state
  changes.
- Use structured JSON for command results and errors.
- Keep only the current screenshot in memory or a temporary file.
- Enforce a capacity-one latest-frame cache by default: discard stale frames and
  never build an unbounded screenshot or base64-result queue. Client history is
  separate and must replace or expire old image results where supported.
- Never persist screenshots, typed secrets, or credentials by default.
- Verify state after actions whenever possible.
- Treat app launching as a generic OS capability: never add app-specific branches for Chrome, Spotify, or any other named application.
- Every input action must move the cursor visibly along a human-like path before
  executing the click, type, or key event. The cursor does not teleport; it
  travels a seeded distorted-Bezier curve with Fitts-law timing so the user can
  see where input is going. This is non-negotiable.
- Preserve platform-neutral behavior in the core; isolate OS-specific code in adapters.
- Provide one platform-neutral command interface with interchangeable OS backends.
- Target broad OS support through shared cross-platform libraries plus native adapters
  where reliability or security APIs require them; do not duplicate task logic per OS.

## Performance requirements

- Prefer one long-lived local process/MCP server over repeated subprocess startup.
- Prefer in-memory screenshots and direct image results; use temporary files only when
  required by the client protocol.
- Bound screenshot bytes in memory and apply backpressure before accepting another
  encoded image; metadata-only observations are preferred when an image is not needed.
- Expose a batch action command for safe sequences such as multiple clicks, pointer
  moves, scrolling, and key presses.
- Do not add artificial delays between clicks or key events unless required by the
  selected backend or explicitly requested by the caller.
- Batches must support cancellation and must stop when a required focus or state
  verification fails.
- Keep verification configurable, but never skip required focus checks before typing
  or safety confirmations for consequential actions.
- Measure end-to-end latency for single actions, batches, screenshots, and verification
  separately so performance regressions are visible in tests.

## Safety requirements

Every implementation must include:

- An emergency stop command or hotkey.
- Input validation for coordinates, keys, text, and command arguments.
- Clear logs that do not include secrets.
- Confirmation gates for deletion, purchases, messages, publishing, permission changes, and account/security changes.
- Localhost-only behavior if any local IPC or server is introduced.
- No stealth, persistence, credential theft, or unauthorized access features.

## Architecture rules

- `desktop/` contains the controller and platform adapters.
- `skills/` contains instructions for agents, not executable control logic.
- `tests/` covers protocol validation, state handling, and platform-independent behavior.
- Keep model calls outside the controller so the toolkit can work with different agents and local models.
- Prefer accessibility/UI-tree targeting over hard-coded coordinates when available.
- Use coordinates only with an explicit screen-state verification step.
- Launching an app must bring it to the foreground through the platform adapter; do not assume that a successful launch command means subsequent input has the correct focus.
- Before browser or app input, explicitly focus/verify the target window and observe again after the action. If focus cannot be verified, stop rather than typing into the currently active app.
- The shared controller must select an appropriate backend at runtime. Basic operations
  may use cross-platform libraries such as `mss` and PyAutoGUI/pynput; enhanced focus,
  accessibility, and input injection may use native adapters.
- Backends must report unsupported capabilities clearly. Cross-platform support does not
  require identical capabilities on every OS, especially under Linux Wayland.

## Agent workflow

Before changing code:

1. Read `README.md` and the relevant skill files.
2. Inspect the current platform adapter and command protocol.
3. Keep changes narrow and testable.
4. Run unit tests and protocol smoke tests.
5. Manually verify input behavior on the target operating system.

Before executing desktop actions during development:

1. Confirm the active window and target screen.
2. Launch applications by generic name or path using the OS adapter, not by hard-coded UI coordinates.
3. Use a safe test application first.
4. Avoid real accounts, purchases, messages, and destructive operations.
5. Keep the stop control available.

## Quality bar

Code should be typed, small, and explicit. Public commands need help text and predictable exit codes. Errors should explain what failed and how an agent can recover. New platform-specific behavior must not silently change the contract on the other platform.
