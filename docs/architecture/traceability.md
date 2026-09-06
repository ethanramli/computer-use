# Current requirement traceability

Updated: 2026-09-06. This file maps the live implementation without declaring a
final review verdict. Test totals are intentionally read from pytest rather than
copied into documentation.

| Area | Implementation | Primary evidence |
|---|---|---|
| Static command and whole-batch preflight | `desktop/safety.py` | `tests/test_goal_regressions.py`, `tests/test_final_regressions.py` |
| Risk, literal confirmation, key canonicalization | `desktop/safety.py` | `tests/test_safety.py`, `tests/test_goal_regressions.py` |
| Focus and secure/challenge UI checks | `desktop/controller.py`, platform accessibility metadata | `tests/test_controller.py`, `tests/test_goal_regressions.py` |
| Platform-neutral adapter contract | `desktop/platforms/base.py` | `tests/test_platforms.py` |
| macOS trust, focus, input, and display metadata | `desktop/platforms/macos.py`, `native/cghelper.c` | `tests/test_execute.py`, `tests/test_goal_regressions.py` |
| Fresh frame and display-region authorization | `desktop/frames.py`, `desktop/controller.py` | `tests/test_frames.py`, `tests/test_goal_regressions.py` |
| Bounded screenshot memory and private path lifecycle | `desktop/frames.py` | `tests/test_frames.py`, `tests/test_goal_regressions.py` |
| Request cancellation, deadlines, and emergency stop | `desktop/controller.py`, `desktop/mcp_server.py`, native loops | `tests/test_cancellation.py`, `tests/test_mcp.py`, `tests/test_final_regressions.py` |
| JSON-RPC bounds and structural errors | `desktop/mcp_server.py` | `tests/test_mcp.py`, `tests/test_final_regressions.py` |
| Honest operation-specific effect reporting | `desktop/controller.py` | `tests/test_effect_verify.py` |
| Clean macOS helper build and both entry points | `setup.py`, `MANIFEST.in` | `tests/test_packaging.py` |
| Agent workflows and repository boundaries | `README.md`, `skills/`, `docs/development.md` | documentation review |

Windows, Linux/X11, and Linux/Wayland remain intentionally unimplemented. Their
adapters return `CapabilityError` for unavailable operations and are contract
tested without claiming behavior that cannot be verified on a target host.
