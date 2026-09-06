# Architecture — Part 3: Native Execution Layer

Status: shipped and live-tested 2026-09-04. Cursor moved 465,450 to 545,450 and back via `--execute move`.

## Why a C helper

Three cheaper rungs failed, in order:

1. ctypes + CoreGraphics directly. Segfaults on this toolchain. Python 3.9 on ARM64 cannot pass CGPoint structs by value through ctypes. Both the move path and the cursor read crashed.
2. pynput. Cannot install. Its pyobjc chain fails to build on this Python.
3. JXA-ObjC bridge. `CGEventCreateMouseEvent` is not exposed to JavaScript for Automation.

So: `csrc/cghelper.c`, ~200 lines against system frameworks only. Python stays stdlib subprocess. Ponytail ladder honored, receipts in research.

## Design

- One spawn per action. Moves batch all points through one `movebatch gap_us` call with points on stdin. Ticks loop inside C for scroll.
- Verbs: pos, trusted, move, movebatch, click, drag, scroll, type, key.
- Typing sends Unicode key events with a mean gap sampled from the measured distribution. Per-key variance moves into the helper later.
- Live moves start from the real cursor via `cursor_position`, never from origin. An early build pathed from 0,0. Fixed before any live run.
- Helper resolves at `.codebase/bin/cghelper` relative to the adapter file. An off-by-one parent climb broke this once. Covered by live test, not unit test.

## Trust note

`doctor` reported `trusted: false` in the dev sandbox, yet posted moves landed and verified by position read. TCC attribution is per binary. The user-facing rule stands: grant Accessibility to the terminal or installed binary, then run `desktop doctor`.
