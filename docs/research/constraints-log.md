# Research — Part 4: Constraints Log

Date: 2026-09-04.

## Accepted

1. Fast. Use MSS region grabs, one temp frame, minimal deps. See part-1.
2. No APIs. Local capture plus local input only. Model stays outside the controller.
3. Global use. One `desktop` CLI on PATH. JSON contract. See part-3.
4. Human-like clicks. Bezier plus Fitts plus minimum-jerk plus tremor. Seeded and testable. See part-2.

## Declined

5. Bypass Cloudflare and similar protections. Declined.

Reason: `README.md` Non-goals says no stealth or evasion features. `AGENTS.md` requires confirmation gates and bans stealth, persistence, and unauthorized access. A bypass feature breaks both.

What this project does instead:

- Automates apps and sites the user owns or has permission to test.
- Respects site terms. Stops at password, permission, payment, and challenge UI and asks the user.
- Uses official paths: accessibility tree, keyboard nav, vendor APIs where present.
- Logs clearly with no secrets.

No bypass research is recorded here by design.
