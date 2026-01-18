# Bug: Multiline messages not detected as stuck

**Date:** 2026-01-18
**Severity:** Medium
**Status:** Fixed
**Commit:** 083e4c7

## Summary

Multiline messages pasted into Claude's input but not submitted (Enter not pressed) were never detected as stuck, leaving users waiting indefinitely.

## Reproduction steps

1. Send a multiline message from Telegram (e.g., with line breaks)
2. Message is pasted into Claude's input via tmux
3. Enter is not pressed (race condition or tmux issue)
4. Message sits in input indefinitely
5. Stuck detection never triggers

## Root cause

In `permission_poller.py`, stuck message detection compared:
- `input_text` - extracted from screen using `extract_input_text()`, which returns only the **first line** after `❯`
- `last_sent_message` - the **full multiline** text stored when message was sent

```python
is_potentially_stuck = (
    PASTED_PATTERN.match(input_text) is not None or
    (last_msg is not None and input_text == last_msg)  # Never matches for multiline!
)
```

For a message like:
```
Какие-то проблемы в сессии
Не выходит
```

- `input_text` = `"Какие-то проблемы в сессии"` (first line only)
- `last_msg` = `"Какие-то проблемы в сессии\n\nНе выходит"` (full text)

They never match, so stuck detection fails.

## Evidence

From tmux capture:
```
❯ Какие-то проблемы в сессии tmux attach -t claude-codogram-whisper-use
  Не в  выходит
```

Message sat in input for minutes without being detected as stuck.

## Fix

Compare only the first line of `last_sent_message`:

```python
is_potentially_stuck = (
    PASTED_PATTERN.match(input_text) is not None or
    (last_msg is not None and input_text == last_msg.split('\n')[0])
)
```

## Affected code

- `src/codogram/permission_poller.py:315-318` - stuck detection comparison
