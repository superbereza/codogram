# Bug: AskUserQuestion duplicates on bot restart

**Date:** 2026-01-22
**Severity:** Medium
**Status:** Fixed
**Commit:** 72ba94e

## Summary

When bot restarts while AskUserQuestion prompt is active, the prompt message is sent again, causing duplicates in Telegram chat.

## Reproduction steps

1. Claude asks AskUserQuestion (single-select or multi-select)
2. Bot displays prompt with buttons in Telegram
3. Restart bot (`./stop-and-restart.sh`)
4. Bot sends the same prompt AGAIN
5. User sees 2 identical prompts with buttons

## Root cause

`AskUserQuestionProcessor` stores `self.showing` state in memory only. On restart:

1. `self.showing = False` (init)
2. Processor sees AskUserQuestion on tmux screen
3. Debounce passes
4. `_send()` sends NEW message
5. Old message from previous run remains in chat

No persistence of "prompt already shown" state.

## Fix

Added `last_ask_msg_id` to `ThreadInfo` (persisted in config), similar to existing `last_suggestion_msg_id`:

1. **ThreadInfo** - added `last_ask_msg_id: int | None = None`
2. **session_manager.py** - added load/save for `last_ask_msg_id`
3. **AskUserQuestionProcessor.__init__** - restore `self.showing = True` if `thread.last_ask_msg_id` exists
4. **_send()** - persist `thread.last_ask_msg_id = kb_msg_id`
5. **_reset()** - clear `thread.last_ask_msg_id = None`

```python
# In __init__:
thread = ctx.thread if ctx.thread else ctx.project.threads.get(None)
if thread and thread.last_ask_msg_id:
    self.showing = True
    self.kb_msg_id = thread.last_ask_msg_id
    self.log_debug(f"ask: restored from restart, kb_msg={self.kb_msg_id}")
```

Now on restart, processor knows prompt is already shown and won't send duplicate.

## Affected code

- `src/codogram/core/session_manager.py` - ThreadInfo.last_ask_msg_id
- `src/codogram/claude/poller/processors/ask_user.py` - persistence logic
