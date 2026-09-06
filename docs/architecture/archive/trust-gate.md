# Architecture — Part 4: Trust Gate Finding

Date: 2026-09-04. Verified live. Moves land, clicks and keys do not, in this shell.

## Evidence

- `move` out-and-back verified by position read twice. Same binary, same tap.
- `click`, `press`, `hotkey`, Spotlight open: exit 0 from the helper, zero visible effect across six attempts on forgiving targets.
- `doctor` reports `trusted: false` here.
- `launch` works regardless. `open -a` needs no Accessibility grant.

## Reading

macOS delivers synthetic mouse-move events from any process. Button and keyboard events require the posting binary to hold Accessibility trust. The code posts all types through the same tap with standard construction. Nothing to fix in code.

## Unblock

System Settings, Privacy and Security, Accessibility, enable the terminal app or installed binary. Rerun `desktop doctor` until `trusted: true`. Then rerun the click, type, and hotkey battery. One human toggle unlocks the rest.
