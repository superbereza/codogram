# Bug: Messages starting with / not sent to Claude

**Date:** 2026-01-18
**Severity:** High
**Status:** Fixed

## Summary

Messages starting with `/` (like `/dash`, `/foo` intended for Claude) were silently dropped instead of being forwarded to Claude.

## Fix history

### Fix 1 (083e4c7) — partial

Removed explicit `text.startswith("/")` filter in `on_message()`. Problem persisted.

### Fix 2 (current) — complete

Added explicit handler for unregistered commands:

```python
@router.message(F.text.startswith("/"))
async def on_unknown_command(message: Message, telegram_queue: TelegramQueue):
    """Forward unregistered commands to Claude as text."""
    await _route_message(message, telegram_queue)
```

**Why this works:** aiogram's catch-all `@router.message()` doesn't reliably catch "/" messages that weren't matched by `Command()` filters. Explicit `F.text.startswith("/")` filter guarantees matching.

Reference: [aiogram Discussion #1429](https://github.com/aiogram/aiogram/discussions/1429)

## Affected code

- `src/codogram/handlers/messages.py` — added `on_unknown_command` handler, refactored to `_route_message()`
