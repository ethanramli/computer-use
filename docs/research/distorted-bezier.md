# Research — Part 5: Distorted-Bezier Mouse Model

Source: https://github.com/User0332/rewards-farmer (`src/mouse_trajectory.py`, `src/fitts_law.py`, `src/mimic_typing.py`). MIT, Copyright (c) 2026 Carl Furtado. License notice kept for the adapted math.

Used here: trajectory math only, ported to OS-level `desktop/move.py` with stdlib (`math`, no numpy). Not used: Selenium driver, page scrolling, element selectors, rewards tasks, LLM query flow, webdriver-hiding flags.

## Model

- Cubic Bezier with 4 control points. p0 is start, p3 is end. p1 sits in a 20-40px box around start, p2 in a 20-40px box around end. A p2 behind the target creates the occasional natural overshoot.
- Distortion zones for micro-jitter. Time [0,1] splits into 0.05 zones. Each zone activates with probability 0.15. Active zones push 1-5px off-curve and back with a triangular ramp, so the path stays continuous. No teleporting.
- Logistic time warp. `2/(1+e^-x)-1` over normalized time 0-4.5. Ramps speed up early, slows down late.
- Fitts duration. `MT = 0.55 + 0.1276 * log2(2D/W)`. D is pixel distance, W is target size (default 80px, or mean of width and height). Constants come from the repo's own calibration tool: 18 timed trials on random rectangles, linear regression of MT on ID, reported R-squared.
- Target pick. Random point inside the center box (25-75 percent of width and height), not the exact center.
- Typing gaps. Inter-key delays from measured typing: 0-0.1s at 37.7%, 0.1-0.2s at 54.9%, 0.2-0.4s at 7.4%. Ported as `input.next_type_gap(rng)`.

## OS adaptation notes

- Their mover drives Selenium `ActionBuilder` pointer events inside a browser viewport and clamps to `window.innerWidth`. Ours returns plain point lists. Delivery to the OS lives in `platforms/`, which clamps to the display instead.
- Their calibration GUI is Windows-only Tkinter plus `ctypes.windll`. Not ported. Constants ship as defaults. Recalibrate per machine later with the same trial protocol.
- Numpy removed. Logistic uses `math.exp`. Seeding uses `random.Random(seed)` so paths replay exactly.
