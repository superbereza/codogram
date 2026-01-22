# Bug: AskUserQuestion duplicates on bot restart

**Date:** 2026-01-22
**Severity:** Medium
**Status:** Fixed
**Commits:** 72ba94e, e7be4ef

## Summary

When bot restarts while AskUserQuestion prompt is active, the prompt message is sent again, causing duplicates in Telegram chat. Additionally, callbacks don't work after restart because `ask_options_state` is in-memory only.

## Reproduction steps

1. Claude asks AskUserQuestion (single-select or multi-select)
2. Bot displays prompt with buttons in Telegram
3. Restart bot (`./stop-and-restart.sh`)
4. Bot sends the same prompt AGAIN
5. User sees 2 identical prompts with buttons
6. Clicking buttons on old message doesn't work (callbacks lost)

## Root cause

1. `AskUserQuestionProcessor` stores `self.showing` state in memory only
2. `ask_options_state` dict (for multi-select) is in-memory only
3. On restart, no way to restore callback state

## Fix

Delete stale message and send fresh one with working callbacks:

1. **ThreadInfo** - added `last_ask_msg_id: int | None = None` (persisted)
2. **AskUserQuestionProcessor.__init__** - detect stale message from previous run
3. **process()** - delete stale message when AskUserQuestion detected
4. **_send()** - persist `last_ask_msg_id` for next restart
5. **_reset()** - clear `last_ask_msg_id`

```python
# In __init__:
if thread and thread.last_ask_msg_id:
    self.stale_msg_id = thread.last_ask_msg_id
    self.log_debug(f"ask: found stale msg from restart, will delete: {self.stale_msg_id}")
    thread.last_ask_msg_id = None
    project_manager._save()

# In process():
if self.stale_msg_id and is_ask:
    await self._delete_stale_message()
```

Now on restart:
- Old message is deleted
- New message sent with fresh callbacks
- Buttons work correctly

## Affected code

- `src/codogram/core/session_manager.py` - ThreadInfo.last_ask_msg_id
- `src/codogram/claude/poller/processors/ask_user.py` - stale message deletion
