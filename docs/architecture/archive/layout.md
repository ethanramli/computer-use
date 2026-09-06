# Architecture — Part 1: Layout

Status: proposed. Source: `README.md` and `AGENTS.md`.

## Layout

```text
desktop/
  bin/desktop
  desktop/
    capture.py
    input.py
    protocol.py
    state.py
    platforms/
      macos.py
      windows.py
  skills/
    observe.md
    click.md
    type.md
    windows.md
    recovery.md
    safety.md
  tests/
  AGENTS.md
```

## Rules

- `desktop/` holds the controller and platform adapters.
- `skills/` holds agent instructions, not executable control logic.
- `tests/` covers protocol validation, state handling, and platform-independent behavior.
- Keep model calls outside the controller.
- Core stays platform-neutral. Isolate OS code in adapters.
- Prefer accessibility or UI-tree targeting over hard-coded coordinates.
- Use coordinates only with an explicit screen-state verification step.
- Keep changes narrow and testable.

## Controller surface

```python
class ComputerController:
    def screenshot(self): ...
    def click(self, x, y): ...
    def type_text(self, text): ...
    def press_key(self, key): ...
    def hotkey(self, keys): ...
    def active_window(self): ...
```

First implementation: MSS for capture, PyAutoGUI or equivalent for input. Add native adapters later for macOS Accessibility/Quartz/AppleScript and Windows UI Automation/Win32/PowerShell.
