# Bug: Stuck detection only worked for threads during binding

**Date:** 2026-01-18
**Severity:** High
**Status:** Fixed
**Commit:** 3966e6f

## Summary

Single-line messages in already-bound threads (with session_id) were never detected as stuck, leaving users waiting indefinitely.

## Reproduction steps

1. Have a thread with established session_id (already bound)
2. Send a single-line message from Telegram
3. Message gets pasted into Claude input but Enter not pressed (race condition)
4. Message sits in input indefinitely
5. Stuck detection never triggers

## Root cause

`last_sent_message` was only set in `_start_binding()` function, which only runs for threads WITHOUT session_id (during initial binding).

For already-bound threads, the code path was:
```python
case RouteAction.SEND_TO_TMUX:
    success = await _send_content(message, result, telegram_queue)
```

And `_send_content()` never set `last_sent_message`.

Stuck detection in `permission_poller.py` checks:
```python
is_potentially_stuck = (
    PASTED_PATTERN.match(input_text) is not None or  # Only multiline
    (last_msg is not None and input_text == last_msg.split('\n')[0])  # Always None!
)
```

Since `last_msg` was always None for bound threads, only PASTED_PATTERN could trigger detection - but that only matches `[Pasted text #X +Y lines]` pattern (multiline messages).

## Evidence

Message "Е2е тесты адаптировал под это?" sent at 10:25:21 to bound thread `set-up-flow-redesign` sat stuck for 5+ minutes with no detection.

## Fix

Set `last_sent_message` for ALL messages in `_send_content()`:

```python
# Track for stuck message detection
if result.thread:
    result.thread.last_sent_message = content

return _message_router.send_to_tmux(result, content)
```

## Affected code

- `src/codogram/handlers/messages.py:140-142` - added last_sent_message tracking
