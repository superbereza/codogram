# Bug: Command followed by text not sent to Claude

**Date:** 2026-01-27
**Severity:** Medium
**Status:** Fixed

## Summary

Messages starting with a command but followed by text (e.g., `/settings давай доработаем`) were handled as commands instead of being sent to Claude. The text after the command was silently ignored.

## Root cause

aiogram's `Command()` filter matches command prefix regardless of what follows. So `/settings foo bar` matches `/settings` command handler, and `foo bar` is ignored.

## Fix

Added `CommandStrict()` filter to all commands that don't accept arguments. This filter checks that the message contains ONLY the command, no additional text:

```python
class CommandStrict(Filter):
    """Filter that only matches commands WITHOUT arguments."""
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        parts = message.text.split(maxsplit=1)
        return len(parts) == 1
```

Usage:
```python
@router.message(Command("settings", ignore_case=True), CommandStrict())
```

Now `/settings` triggers the settings menu, but `/settings давай доработаем` falls through to `on_unknown_command` and gets sent to Claude.

## Affected code

- `src/codogram/handlers/common.py` — `CommandStrict` class (already existed)
- `src/codogram/handlers/sessions.py` — added to /clear, /esc, /resume
- `src/codogram/handlers/finish_chat.py` — added to /finish_chat
- `src/codogram/handlers/new_chat.py` — added to /new_chat
- `src/codogram/handlers/threads.py` — added to /thread, /thread_delete
- `src/codogram/handlers/branches.py` — added to /branch, /branch_finish
- `src/codogram/handlers/shift_tab.py` — added to /shift_tab
- `src/codogram/handlers/reset/handlers.py` — added to /hard_reset
- `src/codogram/handlers/restart/handlers.py` — added to /restart
- `src/codogram/handlers/settings/main.py` — added to all commands except /settings (already had it)
- `src/codogram/handlers/settings/verbose_menu.py` — added to /verbose_mode
- `src/codogram/handlers/start/commands.py` — added to /start (group)
