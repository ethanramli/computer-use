# Development

Run commands from the repository root. The Python package and all executable
source live in `desktop/`; platform-specific native source lives in `native/`.

## Setup and checks

```bash
python3 -m pip install -e .
python3 -m pytest -q
python3 -m compileall -q desktop tests
git diff --check
```

The macOS wheel builds a universal `desktop/_bin/cghelper` from
`native/cghelper.c`. To inspect exactly what a clean package contains:

```bash
python3 -m pip wheel . --no-deps --wheel-dir /tmp/computer-automation-wheel
python3 -m zipfile -l /tmp/computer-automation-wheel/*.whl
```

Both console entry points come from that wheel:

- `desktop`: JSON CLI; dry-run unless `--execute` is present.
- `computer-mcp`: persistent newline-delimited JSON-RPC/MCP stdio server.

`computer-mcp --help` terminates normally. A protocol smoke test is also
terminating:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  | computer-mcp
```

## Command contract

Public commands are `observe`, `list_apps`, `list_windows`, `active-window`,
`focus_app`, `launch`, `move`, `click`, `double-click`, `right_click`, `drag`,
`scroll`, `type`, `click_type`, `press`, `hotkey`, `wait`, `batch`, `stop`, and
`doctor`.

Results are one JSON envelope. Errors contain stable `code`, `message`, and
`recover` fields. CLI exit codes are 0 for success, 2 for bad arguments, 3 for
attention/focus requirements, 4 for blocked or unsupported operations, and 5
for execution, focus, or stale-frame failures.

Input protocol calls require an explicit risk category. Consequential risks
also require literal `confirm: true`. Keyboard actions require an `app`. Every
coordinate action requires a frame ID created by the same live controller.

The one-shot CLI remains useful for help, diagnostics, metadata, and dry-run
planning. Executed observe-to-coordinate workflows belong in one persistent MCP
session so frame authorization is real.

## Native development on macOS

Syntax-check the input helper without producing a binary:

```bash
clang -fsyntax-only -Wall -Wextra -Werror native/cghelper.c
```

Build artifacts belong under ignored `build/`, never beside source:

```bash
mkdir -p build
clang -O2 -arch arm64 -arch x86_64 -o build/cghelper \
  native/cghelper.c -framework CoreGraphics -framework ApplicationServices
clang -O2 -o build/receipt-window native/receipt-window.c \
  -framework CoreGraphics -framework ApplicationServices
```

The receipt window is a listen-only manual measurement fixture. It is not
installed and does not participate in normal control logic.

Before manually testing real input, run `desktop doctor`, use a harmless local
application, confirm its foreground state, keep cancellation reachable, and do
not use accounts, secrets, messages, purchases, or destructive targets.

## Benchmarks

```bash
python3 tools/benchmark.py --samples 200 --runs 5
```

The ignored `benchmarks/latest.json` includes raw nanosecond samples, UTC
bounds, environment details, warm/cold state, quantiles, and failure rates. The
fake backend isolates controller overhead; OS dispatch needs separate,
platform-labelled measurements.

## Documentation

Current operational guidance is in this file, the root README, `AGENTS.md`, and
`skills/`. Dated architecture, research, and review records under `docs/` are
historical evidence and may describe earlier layouts or test counts.
