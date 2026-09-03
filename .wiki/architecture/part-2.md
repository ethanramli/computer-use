# Architecture — Part 2: OS-Level Layout

Status: corrects part-1 paths. App lives in `.codebase/`. Any OS that installs it runs the same core.

## Layout

```text
.codebase/
  README.md
  pyproject.toml
  bin/desktop
  desktop/
    protocol.py
    state.py
    capture.py
    input.py
    move.py
    platforms/
      __init__.py
      macos.py
      windows.py
      linux.py
  tests/test_protocol.py
```

## Rules

- Core in `desktop/` is platform-neutral and has no network calls.
- OS code lives only in `desktop/platforms/`. macOS first, Windows next, Linux after.
- `move.py` is pure math. No I/O. Seeded cubic Bezier. Tested offline.
- `capture.py` uses MSS region grabs. Falls back to stub when MSS is absent.
- `input.py` validates then routes to the active platform adapter.
- Skills in `skills/` are instructions only.
