# Safety — Part 1: Gates and Validation

Status: required by `AGENTS.md`. No code implements this yet.

## Required

- Emergency stop command or hotkey.
- Input validation for coordinates, keys, text, and arguments.
- Clear logs with no secrets.
- Confirmation gates for deletion, purchases, messages, publishing, permission changes, and account or security changes.
- Localhost-only behavior for any local IPC or server.
- No stealth, persistence, credential theft, or unauthorized access.

## Agent workflow during development

- Confirm the active window and target screen first.
- Use a safe test app first.
- Avoid real accounts, purchases, messages, and destructive operations.
- Keep the stop control available.
- Observe again after each action and verify state.
