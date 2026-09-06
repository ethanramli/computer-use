# Research — Part 3: Global Install, Any Agent Can Use

Status: decision. Goal: any local agent uses one CLI after install.

## Pattern

- One binary on PATH. Name: `desktop`.
- JSON on stdout. Non-zero exit on error. Help text per command.
- No daemon by default. No server port. Localhost only if IPC is added later.
- Reference: Hermes `hermes computer-use install | status | doctor`. Same three verbs fit here.

## Options

- Python: `pipx install .` from `.codebase/`. Gives isolated venv plus PATH binary. No API keys.
- Node alt: `npm i -g` with prebuilt binaries like nut.js and robotjs. No build tools needed.
- Rust alt: `cargo install` for enigo-based helper. Fastest input path.
- Permissions are OS gates, not config. macOS needs Accessibility plus Screen Recording for the installed binary. Hermes attributes perms to `com.trycua.driver` daemon, not the terminal. Same rule applies: grant to the installed app, then relaunch the caller.

## Contract

```bash
desktop observe
desktop click --x 640 --y 420
desktop type "hello"
desktop stop
```

- `observe` writes `/tmp/desktop-current.jpg` and prints metadata.
- Every result is JSON. Errors carry `code`, `message`, `recover`.
- Keep only the current frame. No history dir.
