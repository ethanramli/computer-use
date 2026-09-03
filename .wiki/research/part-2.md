# Research — Part 2: Human-Like Mouse Movement

Status: findings from GitHub search 2026-09-04. Math only, no evasion tactics.

## Why straight lines fail

Straight lines at constant speed look robotic. Human paths curve, slow at the ends, and shake.

## Core models

- Bezier curves for path shape. Random control point with deviation 10-30 percent of distance. Overshoot then correct back.
- Fitts Law for timing. Longer distance takes more time. Duration scales with distance and target size.
- Minimum-jerk velocity. Bell shape. Slow start, fast middle, slow end. Peak near 38-45 percent.
- Tremor. 8-12 Hz low-amplitude Gaussian noise scaled with velocity.
- Overshoot. Fast moves overshoot ~70 percent of the time, then correct.

## Libraries that implement this

- `sarperavci/human_mouse` — 101 stars. Bezier plus spline. `move`, `move_random`, `perform_click`, `perform_double_click`. Speed factor, zigzag flag. MIT. Source: https://github.com/sarperavci/human_mouse
- `AsfhtgkDavid/windmouse` — 62 stars. WindMouse algorithm. Gravity, wind, damping params. Backends: PyAutoGUI and AutoHotkey. GPL-3.0. Source: https://github.com/AsfhtgkDavid/windmouse
- `kkb-98/synthetic-behavior` — Bezier plus Fitts timing plus jitter plus overshoot. Returns `(x, y, delay_ms)` points.
- `ChrisdeWolf/bezier-mouse-js` — 6 stars. Pure curve math plus nut-js driver. `bezierCurveTo(init, fin, deviation, steps)`. Use with Playwright or Puppeteer. MIT. Source: https://github.com/ChrisdeWolf/bezier-mouse-js
- `Tomotsugu-dev/HumanMoveMouse` — human trajectories plus pixel-exact straight mode plus record and replay. Speed, smoothness, jitter, seed for repro. MIT.
- `autoscrape-labs/pydoll` — `humanize=True` flag. Bezier paths, Fitts timing, minimum-jerk, tremor, overshoot. CDP level, no WebDriver. Source: https://github.com/thalissonvs/pydoll
- `Super-44/nothingtoseehere` — neuromotor model. Throughput under 12 bits per second, peak at 42 percent, straightness ~0.91, 10 Hz tremor, log-normal clicks ~100ms.
- `vincentbavitz/bezmouse` — 208 stars. Bezier with xdotool. Overshoot and variable speed. Original use was game bots.
- `bgdmnl/HumanizedMouse` — C++ Windows. Cubic Bezier, randomized control points, Win32 cursor APIs. MIT.

## Plan for this project

- Phase 1: straight `move` with fixed steps. Deterministic. Testable.
- Phase 2: cubic Bezier with seeded random. `seed` arg reproduces the same path.
- Phase 3: add Fitts timing plus minimum-jerk delays. No new deps. One function returns point list.
- Keep exact-click mode for small targets. Human curve for travel, exact land for click.
