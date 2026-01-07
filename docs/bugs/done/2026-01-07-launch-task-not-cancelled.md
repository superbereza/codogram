# Bug: launch_task not cancelled on /finish and /restart

**Date:** 2026-01-07
**Severity:** Medium
**Status:** Fixed
**Fixed:** 2026-01-07

## Symptom

When user sends `/start` and then `/finish` or `/restart` before Claude finishes loading, the launch animation continues running until timeout (2 minutes).

## Root Cause

`archive_thread()` cancels `watcher_task`, `poller_task`, `binding_task` but NOT `launch_task`.

`handle_restart_confirm()` only kills tmux session, doesn't cancel any tasks.

## Affected Code

- `src/codogram/services/branch.py` - `archive_thread()` missing `launch_task.cancel()`
- `src/codogram/handlers/start.py` - restart flow doesn't cancel tasks

## Reproduction

1. Send `/start` in a topic
2. Immediately send `/finish` before Claude is ready
3. Observe: animation keeps running, face emojis keep updating

## Fix

Added task cancellation to both flows:

1. `archive_thread()` - now cancels all 4 tasks in a loop
2. `on_restart_confirm()` - added task cancellation before killing tmux
