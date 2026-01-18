# Bug: Commands with uppercase letters not recognized

**Date:** 2026-01-18
**Severity:** Low
**Status:** Fixed

## Summary

Commands typed with uppercase letters (e.g., `/Branch`, `/HELP`, `/New`) were not recognized by the bot. Users had to type commands in exact lowercase.

## Reproduction steps

1. Open Telegram chat with the bot
2. Type `/Branch` or `/BRANCH` instead of `/branch`
3. **Bug:** Bot doesn't respond (command not matched)

## Root cause

Aiogram's `Command()` filter is case-sensitive by default. It only matches exact lowercase command names.

## Fix

Added `NormalizeCommandMiddleware` that converts command text to lowercase while preserving argument case:

```python
# /BRANCH MyFeature -> /branch MyFeature
parts = event.text.split(None, 1)
command = parts[0].lower()
args = parts[1] if len(parts) > 1 else ""
event.text = f"{command} {args}".rstrip()
```

Registered as `outer_middleware` to run before other middlewares process the message.

## Files changed

- `src/codogram/middleware/normalize_command.py` - New middleware
- `src/codogram/main.py` - Register middleware
- `tests/test_normalize_command.py` - Unit tests

## Commits

- `d1abfb4` feat: normalize command case (/Branch -> /branch)
