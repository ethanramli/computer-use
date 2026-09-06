# Goal — Part 1: Definite Achievable Target

Date: 2026-09-04. This is the build target. It keeps constraints 1-4 and replaces 5 with a compliant path.

## Goal v0.1

Ship a local-only `desktop` CLI that any installed agent can call. No network. No accounts. Fast region capture plus seeded human-like moves. It stops at login, permission, payment, and challenge UI instead of solving them.

## Acceptance

- `desktop observe --region x,y,w,h` prints JSON in under 150ms p95 on an 800x600 region.
- `desktop move --x 640 --y 420 --seed 7` emits a curved path in under 5ms and clicks the exact target.
- `desktop click`, `type`, `press`, `stop` work from any fresh shell after `pipx install .`.
- No outbound calls. Tests prove it by blocking sockets.
- Challenge UI returns `{"ok": false, "error": {"code": "needs_attention"}}`. No auto-solve.

## How each constraint is met

1. Fast. MSS region grab. One temp frame. Pure-Python Bezier. No per-step inference. Measure with p95, not mean.
2. No APIs. Deps: MSS plus pynput or PyAutoGUI only. Model stays outside. Controller never fetches.
3. Global. `pipx install .` from `.codebase/` puts `desktop` on PATH. JSON on stdout. Exit codes: 0 ok, 2 bad arg, 3 needs attention, 4 blocked. `desktop doctor` checks PATH plus Accessibility plus Screen Recording.
4. Human moves. One pure function `points(x0, y0, x1, y1, seed)` returns a list. Cubic Bezier with seeded deviation. Fitts time for total duration. Minimum-jerk delays between points. Optional tremor. Exact-land mode for targets under 20px. No driver needed to test the math.

## Challenge handling, not bypass

Bypass stays out of scope per `research/constraints-log.md`. v0.1 does this instead:

- Detect labels like password, permission, payment, verify you are human, Turnstile, CAPTCHA via AX tree or title match.
- Stop with code `needs_attention` and a recover hint for the user.
- For dev on own sites only: support official Turnstile test keys in `.env.local`. Test keys always pass by design. This tests the flow without evading protection.
- Respect site terms. Automate only apps and sites with permission.

## Phases

- Phase 0 done. Protocol, state, CLI stubs, 3 tests pass.
- Phase 1 input. MSS region capture plus OS click plus validation plus stop. Gate: p95 timing plus exit codes.
- Phase 2 move. `desktop/move.py` pure math plus replay test. Gate: under 5ms, seed repro exact, straightness 0.80-0.95.
- Phase 3 global. pipx package plus doctor. Gate: fresh shell run works.
- Phase 4 safety. Blocklist plus `--yes` flag for destructive plus challenge stop. Gate: blocked action never executes.

## Out of scope

No bypass, no CAPTCHA solving, no stealth flags, no daemon, no cloud OCR, no credential storage.
