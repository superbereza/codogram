# Inline Auto-Accept Notification

## Problem

When auto-accept is enabled, bot sends separate messages for each auto-accepted permission. This creates noise in chat, especially during tool-heavy sessions.

## Solution

Edit the last tool message to add auto-accept suffix instead of sending a new message.

## Design

### Format

```
original_tool_message

UPD: 🤖 auto accepted
```

Every 10th auto-accept shows hint:
```
original_tool_message

UPD: 🤖 auto accepted (/auto_accept to disable)
```

### Display Mode Behavior

| Mode | Behavior |
|------|----------|
| `silence` | Nothing (no tool messages to edit) |
| `current` | Edit the single tool message |
| `headers` | Edit last tool message |
| `lines` | Edit last tool message |
| `show_all` | Edit last tool message |

### Runtime State

Add to `ThreadInfo` (runtime-only, not persisted):
- `last_tool_msg_id: int | None` - Telegram message ID of last tool message
- `last_tool_msg_text: str | None` - Text content for editing
- `auto_accept_count: int = 0` - Counter for hint frequency

### Edit Logic

1. Check if `thread.last_tool_msg_id` exists
2. Build new text: `last_tool_msg_text + "\n\nUPD: 🤖 auto accepted"`
3. If `auto_accept_count % 10 == 0`: add hint
4. Try `EditBatch` to edit message
5. If edit fails (message deleted, too long): fallback to `OutgoingBatch`
6. Increment `auto_accept_count`

### Reset Conditions

Reset `last_tool_msg_id = None` when:
- TEXT content arrives (Claude's response)
- This ensures auto-accept only edits tool messages, not responses

### Refactoring

Reduce `try_auto_accept` parameters from 10 to 7 by passing `thread` object:

Before:
```python
async def try_auto_accept(
    options, body, tmux, queue, chat_id, thread_id,
    context_name, prompt_type, display_mode, line_limit
)
```

After:
```python
async def try_auto_accept(
    options, body, tmux, queue, chat_id,
    context_name, prompt_type, thread
)
```

Extract `display_mode`, `line_limit`, `thread_id` from `thread` object inside function.

## Files to Modify

1. **`core/session_manager.py`** - Add runtime fields to ThreadInfo
2. **`claude/history_watcher.py`** - Save msg_id/text after tool messages, reset on text
3. **`auto_accept.py`** - Refactor signature, add edit logic with fallback
4. **`claude/poller/processors/permissions.py`** - Update `try_auto_accept` call
