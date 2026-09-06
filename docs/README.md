# Documentation

Use the root `README.md`, `AGENTS.md`, this index, and `skills/` for the current
contract. Everything with a date in its name is a decision or evidence
record from that point in the project's history; it is not automatically the
current interface.

## Current guides

- `development.md` — setup, package checks, protocol smoke tests, native builds,
  and benchmarks.
- `reviews/review-fix-log-2026-09-06.md` — current defect remediation evidence.
- `research/desktop-task-run-2026-09-06.md` — ongoing first-use desktop task run,
  observed failures, remedies, and completion checks.

## Decision and evidence records

- `architecture/` — architecture decisions, traceability, and macOS live-smoke
  records.
- `protocol/` — earlier command and envelope decisions.
- `safety/` — earlier safety decisions.
- `goal/` — original product-scope records.
- `research/` — investigations and performance evidence.
- `reviews/archive/` — superseded reviews and remediation logs.

When a historical record conflicts with executable behavior, verify the tests
and current guide, then update the current documentation with the code change.
