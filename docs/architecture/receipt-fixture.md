# Benchmark — Event Receipt (dispatch vs effect) on macOS

Date: 2026-09-04. Host: MacBookAir10,1, Apple M1, macOS 14.2, arm64,
Python 3.9.6, Accessibility trust granted to the agent shell's responsible
binary. `model_included: false`. Clocks: `perf_counter_ns` for dispatch,
`mach_absolute_time` (scaled to ns) inside the receipt fixture for effect.

## Method

1. `build/receipt-window <seconds>` — listen-only CGEventTap fixture
   (`native/receipt-window.c`), prints one JSON line per received event with
   a monotonic `ts_ns`. It never posts or modifies events.
2. The harness posts one real left-click via `build/cghelper click x y 0 1`
   at a fixed coordinate, recording `dispatch_ns` (request start to helper
   process exit, `perf_counter_ns`).
3. The fixture's matching `leftMouseDown` receipt at the same coordinates
   proves the event reached the window server: `effect_ns`.
4. Dispatch−effect delta isolates the OS delivery latency hidden behind the
   fire-and-forget `CGEventPost` API.

## Measured result (single representative run, 1 sample — not a distribution)

- dispatch_ns: 46.30 ms (includes one cghelper process spawn)
- effect: leftMouseDown received at the tap at the same coordinates —
  the event provably reached the session (was NOT dropped by the focus
  race that affected keyboard events in the earlier smoke battery)
- mouseMoved events from earlier `move` tests also receipt-confirmed

## What this proves

- The receipt fixture works: events posted by cghelper at coordinates X,Y
  are received by the tap with matching coordinates, so effect verification
  is measurable end to end on macOS.
- Keyboard-event drops observed in the live smoke battery are attributable
  to focus/session state, not to the helper failing to post.

## Limitations

- Single-sample proof of function, not a benchmark distribution. The full
  200-sample × 5-run distribution per the wiki benchmark plan must run on
  a host where the session stays attached (the agent session's frontmost
  flips to loginwindow under load, which pollutes long keyboard runs).
- Tapping requires the same Accessibility trust as input; `receipt-window`
  exits 3 with a clear message when trust is missing.

## Follow-up

Controller-level `verify=focus|effect` is the portable mechanism; this fixture
is the macOS-native measurement vehicle for `effect_ns`.
