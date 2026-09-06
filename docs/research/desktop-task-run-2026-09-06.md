# Desktop task run — 2026-09-06

Status: Test 3 complete. Birthday and YouTube work are outside the active run.

## Goal and acceptance checks

Use only this repository's Python desktop controls and real OS input with the
Bezier cursor path, approaching the README as a first-time installer.

1. In the requested personal Google account, save a birthday on 22 January,
   repeating yearly with a notification. Verify the account, date, recurrence,
   notification, and saved event in Calendar.
2. In a new YouTube tab, search `faysal`, open a video, and verify it is paused.
3. In the school account, leave Economics in Google Classroom, Revision Rojo,
   and Save My Exams open in separate tabs. Verify the account and destinations.
4. Record attempts, failures, remedies, and evidence here; promote reusable,
   verified lessons into the bundled agent instructions.

Do not store screenshots, credentials, or unrelated account content in this log.
Account identity is checked on screen; account details need not be copied here.

## Attempts and results

| Attempt | Observed result | Implication / next action |
| --- | --- | --- |
| Read README and all six bundled instruction files | One-shot executed coordinate actions cannot reuse a frame; persistent MCP is the documented path | Run `python3 -m desktop.mcp_server` and retain its live session |
| `observe` with `path_mode: true` inside the execution sandbox | `unsupported`: `cghelper: display layout unavailable` | Diagnose environment access before altering the adapter |
| `doctor` in that session | Helper and MSS available; Accessibility and Screen Recording reported unavailable | These results alone do not distinguish sandbox restrictions from missing OS grants |
| Approved `python3 -m desktop.cli doctor` outside the sandbox | `ready: true`; all four checks passed | Sandbox access was the differentiating condition; no OS permission change needed |
| Start approved persistent Python MCP outside the sandbox; observe | Successful 1440 × 900 capture, display geometry, frame ID, and active app | Observation works in this execution context |
| Generic `launch` for Google Chrome, then observe and inspect current image | Launch verified Chrome foreground; screenshot showed its existing browser window | Generic launch and screen capture work; requested tasks still unverified |
| Re-observe after user interruption | Active app was Code | Recheck focus after interruptions; previous foreground evidence is insufficient |

## Remedies and code changes

- Environment remedy: obtained execution approval and used the controller outside
  the sandbox. No controller code fix or macOS permission change was made.
- Documentation: added this run record and sandbox recovery guidance.
- Batching is an intended optimization, not a measured speedup in this run yet.
  Record comparable timings and verified effects before claiming a speedup.

## Outstanding verification

## Input regressions and live probes

- Added a public-controller regression for type, press, hotkey, scroll,
  click_type, drag approach, and native move. All seven initially failed the
  visible-travel requirement (after correcting the test's argument schema).
- Fixed the shared controller to travel along a seeded curve before those
  routes. Untargeted input returns to its current position; keyboard focus is
  rechecked after travel. Native move no longer teleports. Updated older tests
  that explicitly expected teleporting or omitted movement events.
- `python3 -m pytest -q`: 286 passed after the controller change.
- Live TextEdit: clicks opened File → New. Initial Command-N and native typing
  reported dispatch but had no visible effect. No browser input was attempted.
- Python read-only Carbon probe: Secure Input was false. A permission approval
  moved focus to Code; the controller rejected the next typing attempt without
  input, then explicit focus restoration allowed the next probe.
- Compatibility typing inserted `Test`; native typing of ` Native` immediately
  afterward left the document unchanged. This distinguished zero-gap delivery
  from general inability to type in the document.
- Native helper experiment: keep the keyboard posting process alive with a
  20 ms run-loop delivery window after posting. Native ` Native` then appeared
  correctly. This supports the process-lifetime hypothesis on this host; it
  does not establish reliability across macOS versions. No per-character delay
  was added. Hotkey and further live checks remain pending.
- Command-N subsequently triggered a new TextEdit window (capture caught the
  animation). Chrome navigation batches still did not navigate. A separate
  Command-L then Unicode typing probe isolated a second issue: keyboard events
  with unspecified flags could inherit modifiers. Explicitly set zero flags
  for Unicode typing and always set the requested flags for key events,
  including zero. The full Calendar URL then appeared correctly in Chrome's
  address bar with native timing. Further navigation checks are pending.
- Account check: initial Chrome profile was not the requested account. Switched
  profiles using the visible Chrome menu and verified the personal account's
  full address in Google's account panel. A separate Ethan school profile is
  available, but its full address still requires verification. Display names
  alone are insufficient because both intended profiles are named Ethan.

At that earlier checkpoint, all three browser task outcomes remained
unverified. No birthday save or video pause is claimed anywhere in this run;
the later continuation below covers only the requested school-account setup.

## Test 3 continuation — 2026-09-07

### Goal

Using only the persistent native `computer-mcp` stdio controller, verify the
school Chrome profile by its full on-screen address and leave these open in
three separate tabs: Economics in Google Classroom, RevisionDojo (requested as
“Revision Rojo”), and Save My Exams. Also verify the documented first-install
MCP path, including doctor, observe, batch, cancellation, and same-session
frame reuse. Birthday and YouTube tasks were explicitly excluded.

### Attempts and results

| Attempt | Observed result | Implication / remedy |
| --- | --- | --- |
| Run `./install` as a first-time user | Wheel and both entry points installed, but Python's user scripts directory was outside `PATH` | Fixed the fallback installer to expose safe symlinks through an already configured `~/.local/bin`; it refuses to replace unrelated files |
| Start a fresh installed `computer-mcp` stdio process | Initialize and tool discovery succeeded; `doctor` reported helper, Accessibility, Screen Recording, and MSS ready | The native MCP path is usable without a Python terminal wrapper and opens no socket |
| Observe Chrome account UI | The requested school account's full address was visible | Full-address account gate passed; no address or screenshot was stored here |
| Open Classroom and select Economics | `11 IB Economics` was visible in the Classroom course page | Economics tab verified |
| Search the requested “Revision Rojo” wording | Search resolved it to RevisionDojo; its `/landing` redirect showed a site-owned 404, and “Go back home” opened the authenticated home dashboard | RevisionDojo tab verified; the broken redirect belongs to the site, not the controller |
| Open Save My Exams | The authenticated Save My Exams dashboard was visible | Save My Exams tab verified; all three requested tabs were visible in Chrome's tab strip |
| Reuse an observed frame for coordinate input in the same process | A frame-authorized click opened Economics; a fresh installed process also accepted a frame-authorized mouse move | In-session frame reuse works; an intentionally delayed frame was safely rejected as stale with zero input |
| Execute navigation and wait batches | Batches completed with ordered receipts and `last_completed` | Batch is functionally verified; no speedup claim was made because comparable timing was not measured |
| Cancel a live five-second wait by request ID | The request returned structured `cancelled` before the wait completed | Request-scoped MCP cancellation works |
| Scroll Save My Exams down eight ticks, then up eight ticks | The viewport visibly moved down and then returned near the top | Native vertical wheel direction and delivery are verified live |

### Mouse and scroll fix

- The shared controller already routed every public input command, including
  scroll, through visible seeded Bezier travel; the regression suite covers
  this invariant.
- Diagnosis found that the macOS adapter accepted `left` and `right` but sent
  them on the vertical wheel axis. A red regression reproduced both failures.
- The adapter now maps `up`/`down` to `dy` and `left`/`right` to `dx`. The new
  four-direction regression and the complete visible-travel test file pass.
- Added `skills/scroll.md` with the verified native workflow: focus, position
  over the intended pane using a fresh frame when necessary, scroll explicitly,
  and observe the result.

### Verification summary

- Three required tabs: visibly verified in the school Chrome profile.
- Native MCP: bare `computer-mcp` command resolved after reinstall; initialize,
  tools/list, doctor, observe, same-session frame use, batch, and cancellation
  all succeeded from a fresh process.
- Safety: no challenge, password, payment, permission, message, publishing, or
  destructive action was attempted. Screenshots remained only in the
  controller's capacity-one temporary frame path and were not added to the repo.
