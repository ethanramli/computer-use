# Wiki — Computer Automation

Source of truth for project decisions. Code must match this wiki. If code and wiki differ, fix the code or update the wiki in the same change.

## Overview

Computer Automation is an OS-level, cross-platform desktop-control toolkit for any OS that installs this repo. An agent observes the whole computer and operates it through real OS mouse and keyboard events. This is not a browser tool.

The controller is local and model-agnostic. It works offline. It controls browsers, terminals, editors, design tools, and native apps.

## Rules

- One domain per folder under `.wiki/`.
- One decision round per `part-N.md`. Never append to an existing part. New round = new file.
- Keep procedures as vertical lists.
- Record facts before implementation.
- Ask when requirements are unclear. Do not infer missing behavior.

## Directory tree

```text
.codebase/
  README.md
  pyproject.toml
  bin/desktop
  desktop/
    protocol.py
    state.py
    capture.py
    input.py
    move.py
    platforms/
      macos.py
      windows.py
      linux.py
  tests/test_protocol.py
.wiki/
|-- wiki.md
|-- protocol/
|   |-- part-1.md
|   `-- part-2.md
|-- safety/
|   `-- part-1.md
|-- architecture/
|   |-- part-1.md
|   `-- part-2.md
`-- research/
    |-- part-1.md
    |-- part-2.md
    |-- part-3.md
    `-- part-4.md
`-- goal/
    |-- part-1.md
    `-- part-2.md
```

## Domains

- `protocol/` — CLI commands, JSON results, exit codes.
- `safety/` — validation, stop control, confirmation gates, logging.
- `architecture/` — controller layout, platform adapters, skills and tests.
- `research/` — vendor-neutral findings with sources. Part 1 fast stack, part 2 human movement, part 3 global install, part 4 constraints log.
- `goal/` — definite v0.1 target. Part 1 base goal, part 2 whole-computer scope. Challenge UI stops with `needs_attention`. No bypass.

## Project status

Shipped: OS-level prototype in `.codebase/`. Full verb CLI, `move.py` seeded Bezier, MSS region with stub fallback, safety gates. Tests: 5 passed.

Next: `desktop doctor` perm checks, MSS timing p95, pipx global install.
