# Bug: Messages starting with / not sent to Claude

**Date:** 2026-01-18
**Severity:** High
**Status:** Fixed
**Commit:** 083e4c7

## Summary

Messages starting with `/` (like `/dash`, `/help` intended for Claude) were silently dropped instead of being forwarded to Claude.

## Reproduction steps

1. Send a message starting with `/` in a registered thread (e.g., `/dash`)
2. Message is logged as "Incoming message"
3. No `tmux_send` occurs - message is silently dropped
4. Claude never receives the message

## Root cause

In `messages.py` lines 55-57, there was a filter:

```python
# Skip commands
if text and text.startswith("/"):
    return
```

The assumption was that all messages starting with `/` would be handled by aiogram command routers. However, if no command handler matches (e.g., `/dash` has no handler), the message falls through to the catch-all `on_message()` handler, which then returns early due to this filter.

## Evidence

From logs:
```
07:52:17 [INFO] Incoming message from user=34185809 chat=-1003532995083 thread=28037: /dash
07:52:17 [INFO] aiogram.event: Update id=486071479 is handled. Duration 2 ms by bot id=8261696530
```

No `tmux_send` log entry after the incoming message - handler completed in 2ms without sending.

## Fix

Removed the `text.startswith("/")` filter. Registered bot commands (like `/start`, `/help`) are already handled by their command routers before reaching `on_message()`, so the filter was unnecessary and harmful.

## Affected code

- `src/codogram/handlers/messages.py:55-57` - removed command filter
