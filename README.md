# Computer Automation

An OS-level, cross-platform desktop-control toolkit for any OS that installs this repo. It lets an AI agent observe and operate the whole computer through real OS mouse and keyboard events. This is not a browser tool. No WebDriver. No CDP primary. Browsers are driven the same way as terminals, editors, design tools, Finder, Explorer, Settings, dialogs, taskbars, and native apps.

The project works on any OS that installs it, starting with macOS and Windows, with Linux next. No browser-specific framework required. OS adapters live in `desktop/platforms/`. Core stays platform-neutral.

## Vision

Install the toolkit once, then let any compatible local agent use a small, predictable command set and a progressive skilltree:

```text
Agent → local desktop commands → mouse, keyboard, windows, screenshots
```

The controller is model-agnostic. The agent may use a local vision model or another model made available by its host environment. The desktop-control layer itself should remain local and usable offline.

## Planned capabilities

- Capture the current screen without building a permanent screenshot archive.
- Return the current frame plus compact metadata such as screen size and active window.
- Move the mouse, click, double-click, scroll, type, press keys, and use shortcuts.
- Inspect the active window and available desktop state where the operating system permits it.
- Work with browsers and native desktop applications through real OS input events.
- Verify the screen after actions and recover when the UI changes.
- Provide an emergency stop and confirmation gates for risky actions.

## Proposed CLI

The initial interface should be simple enough for any agent that can execute shell commands:

```bash
desktop observe
desktop click --x 640 --y 420
desktop double-click --x 640 --y 420
desktop type "hello"
desktop press enter
desktop hotkey command,s
desktop scroll --amount -5
desktop active-window
desktop stop
```

Commands should return structured JSON where practical. `observe` may return a temporary image path and metadata:

```json
{
  "image": "/tmp/desktop-current.jpg",
  "screen": {"width": 1920, "height": 1080},
  "active_window": "TextEdit"
}
```

The image is transient state, not long-term memory. Overwrite or discard old frames instead of accumulating them.

## Architecture

```text
desktop-agent/
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

The shared controller should expose platform-neutral operations:

```python
class ComputerController:
    def screenshot(self): ...
    def click(self, x, y): ...
    def type_text(self, text): ...
    def press_key(self, key): ...
    def hotkey(self, keys): ...
    def active_window(self): ...
```

Use cross-platform libraries for the first implementation, such as MSS for capture and PyAutoGUI or equivalent local input tooling. Add native adapters when accessibility or window inspection needs to be more reliable:

- macOS: Accessibility, Quartz, and AppleScript/JXA integration.
- Windows: UI Automation, Win32, and PowerShell integration.

The model should request platform-neutral actions such as `click target=Save`, while the adapter resolves the target using coordinates, image matching, keyboard navigation, or native accessibility information.

## Agent skilltree

Agents should learn the safest reliable workflow progressively:

1. Observe the current screen.
2. Identify the active application and task context.
3. Prefer keyboard navigation and shortcuts when reliable.
4. Locate a target using accessibility information or visual context.
5. Execute one small action or a short verified batch.
6. Observe again and verify the result.
7. Recover or ask for help when the expected state is not present.
8. Request confirmation before sending, deleting, purchasing, publishing, or changing account/security settings.

## Non-goals

- No stealth or evasion features.
- No remote-control server exposed to the network.
- No credential extraction or password logging.
- No unbounded screenshot or action history.
- No destructive action without explicit authorization.

## Development priorities

1. Build the local CLI and JSON action protocol.
2. Implement screen capture and real input events on macOS and Windows.
3. Add stop controls, validation, logging, and temporary-frame cleanup.
4. Add skill files that agents can load and follow.
5. Add unit tests plus manual cross-platform smoke tests.
6. Add optional accessibility and visual-target resolution.
