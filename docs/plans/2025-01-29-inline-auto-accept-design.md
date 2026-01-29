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
| `silence` | Nothing (no tool messages exist) |
| `current` | Edit the single tool message |
| `headers` | Edit last tool message |
| `lines` | Edit last tool message |
| `show_all` | Edit last tool message |

### Using `replace_key` Pattern

Instead of storing `last_tool_msg_id` manually, leverage existing `TelegramQueue.sent_statuses` infrastructure:

```python
# Key format
replace_key = f"tool:{chat_id}:{thread_id}"

# In history_watcher - when sending tool message:
batch = OutgoingBatch(
    chat_id=project.chat_id,
    thread_id=thread.thread_id,
    messages=messages,
    replace_key=replace_key,  # Queue stores msg_id automatically
)

# In auto_accept - when editing:
batch = EditBatch(
    chat_id=chat_id,
    message_id=0,  # Lookup from sent_statuses
    text=new_text,
    parse_mode="MarkdownV2",
    replace_key=replace_key,
)
```

**Benefits:**
- No new state in `ThreadInfo` (except counter)
- Leverages existing, tested infrastructure
- `current` mode can also use this pattern (unification)

### Runtime State

Add to `ThreadInfo` (runtime-only, not persisted):
```python
auto_accept_count: int = 0  # Counter for hint frequency
```

### Edit Logic

1. Build `replace_key = f"tool:{chat_id}:{thread_id}"`
2. Check if key exists in `telegram_queue.sent_statuses`
3. If exists:
   - Get original text from `sent_statuses` or reconstruct
   - Build new text: `original + "\n\nUPD: 🤖 auto accepted"`
   - If `auto_accept_count % 10 == 0`: add hint
   - Try `EditBatch` with `message_id=0, replace_key=replace_key`
   - Increment `auto_accept_count`
4. If not exists or edit fails: fallback to `OutgoingBatch`

### Storing Original Text

The `sent_statuses` dict only stores `replace_key -> msg_id`. For editing, we need the original text.

**Option A**: Extend `sent_statuses` to store `(msg_id, text)` tuple
**Option B**: Store `last_tool_msg_text` in ThreadInfo (runtime-only)

Recommend **Option B** - simpler, ThreadInfo already has runtime fields.

```python
@dataclass
class ThreadInfo:
    # Runtime-only (not persisted)
    last_tool_msg_text: str | None = None
    auto_accept_count: int = 0
```

### Reset Conditions

Reset state when:
- TEXT content arrives (Claude's response) → `last_tool_msg_text = None`
- Session changes (new `session_id`) → `auto_accept_count = 0`

### Fallback Cases

Edit can fail due to:
- Message deleted by user
- Message too old (48-hour Telegram limit)
- New text exceeds 4096 chars
- Race condition (key not in sent_statuses yet)

On any failure: send new message via `OutgoingBatch` (existing behavior).

### Refactoring: Unify with `current` Mode

Currently `history_watcher.py` has separate state for `current` mode:
```python
current_mode_key = f"current:{project.chat_id}:{thread.thread_id}"
current_mode_active = False
```

Can be unified with auto-accept tracking:
- Both use same `replace_key` pattern
- Both need to track last tool message
- Share `thread.last_tool_msg_text`

### Signature Refactoring

Reduce parameters by passing `thread`:

Before (10 params):
```python
async def try_auto_accept(
    options, body, tmux, queue, chat_id, thread_id,
    context_name, prompt_type, display_mode, line_limit
)
```

After (8 params):
```python
async def try_auto_accept(
    options, body, tmux, queue, chat_id,
    context_name, prompt_type, thread
)
```

Extract `display_mode`, `line_limit`, `thread_id` from `thread` inside function.

### Strings

Add to `strings.py`:
```python
AUTO_ACCEPT_SUFFIX = "UPD: 🤖 auto accepted"
AUTO_ACCEPT_HINT = "(/auto_accept to disable)"
```

## Files to Modify

1. **`core/session_manager.py`** - Add runtime fields: `last_tool_msg_text`, `auto_accept_count`
2. **`claude/history_watcher.py`**:
   - Add `replace_key` to tool message batches
   - Save `thread.last_tool_msg_text` after sending
   - Reset on TEXT content
3. **`auto_accept.py`** - Refactor signature, add edit logic with fallback
4. **`claude/poller/processors/permissions.py`** - Update `try_auto_accept` call
5. **`strings.py`** - Add auto-accept strings

## Edge Cases Documented

- **48-hour edit window**: Telegram limitation, fallback handles it
- **Message length**: If original + suffix > 4096 chars, fallback to new message
- **Concurrency**: Watcher must send before poller tries to edit (natural order via queue)
- **Silence mode**: No-op, no tool messages to edit
