# Agent Instructions

## Project purpose

This repository contains an OS-level, cross-platform desktop automation toolkit for any OS that installs it. It gives AI agents controlled access to whole-computer screen observation and real OS mouse/keyboard input. This is not a browser-only project. Browsers, terminals, editors, design tools, and native OS surfaces are all driven through the same OS input path.

## Core principles

- Keep the controller local and model-agnostic.
- Prefer explicit, small, inspectable commands over hidden behavior.
- Use structured JSON for command results and errors.
- Keep only the current screenshot in memory or a temporary file.
- Never persist screenshots, typed secrets, or credentials by default.
- Verify state after actions whenever possible.
- Make dangerous actions visibly confirmable and easy to cancel.
- Preserve platform-neutral behavior in the core; isolate OS-specific code in adapters.

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

## Agent workflow

Before changing code:

1. Read `README.md` and the relevant skill files.
2. Inspect the current platform adapter and command protocol.
3. Keep changes narrow and testable.
4. Run unit tests and protocol smoke tests.
5. Manually verify input behavior on the target operating system.

Before executing desktop actions during development:

1. Confirm the active window and target screen.
2. Use a safe test application first.
3. Avoid real accounts, purchases, messages, and destructive operations.
4. Keep the stop control available.

## Quality bar

Code should be typed, small, and explicit. Public commands need help text and predictable exit codes. Errors should explain what failed and how an agent can recover. New platform-specific behavior must not silently change the contract on the other platform.
