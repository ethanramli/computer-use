# Research — Part 1: Fast Local Stack, No APIs

Status: findings from web search 2026-09-04. All local, no cloud calls.

## Capture

- MSS is the default for cross-platform. 30-60 FPS. `sct.grab(monitor)` returns BGRA. Convert to PIL or numpy for matching.
- Source: https://screenshotone.com/blog/python-screen-capture/
- PyAutoGUI screenshot is slow. 1-5 FPS. Uses PIL internally. Use only for scripts, not loops.
- DXcam is fastest. 240+ FPS. Windows only. DirectX. Use for games or recording. Not cross-platform.
- PIL ImageGrab is 10-15 FPS. Fine for one-off captures.

Rule: capture region, not full screen. Full 1440p grab costs ~70ms even with MSS. Shrink the region to cut time.

## Input

- `pynput` monitors and controls input devices. Source: https://github.com/Omar-F-Rashed/pyauto-desktop
- `pydirectinput` sends direct input for games where PyAutoGUI fails.
- `pywinctl` controls windows cross-platform.
- Rust `enigo` simulates hardware input on Linux X11, macOS, Windows. 1778 stars. MIT. `move_mouse`, `button`, `text`. Source: https://github.com/enigo-rs/enigo
- Node `nut.js` uses native bindings. Claims 100x faster than `robotjs`. Prebuilt binaries. Mouse, keyboard, screen, window. Source: https://nutjs.dev/
- `robotjs` is older. Prebuilt binaries. Mac, Windows, Linux. Source: https://robotjs.dev/

## Choice for this project

- Capture: MSS first. Region grab. Overwrite one temp file.
- Input: PyAutoGUI or pynput first for speed of build. Enigo later if Python proves too slow.
- No APIs: no inference per step, no cloud OCR, no external screenshot service. Vision stays in the calling agent.
