# Input Suggestions

## Overview

Show Claude's input suggestions in Telegram as clickable buttons.

**What happens in Claude:**
- After response, suggestion appears in input box
- Format: `❯ посмотри что залогировалось                    ↵ send`

**What user sees in Telegram:**
- "💡" message arrives with ReplyKeyboardMarkup (suggestion as button)
- Click → text sent to Claude
- Keyboard auto-hides after use (one_time_keyboard)

## Parsing in screen.py

**New function:**
```python
def parse_input_suggestion(output: str) -> str | None:
    """Parse suggestion from input box.

    Format: ❯ suggestion text                    ↵ send
    Located between ──── lines (input box).
    """
    # Find input box content between last two ──── separators
    # Check for ❯ followed by text and ↵ send
    # Return suggestion text or None
```

**Detection logic:**
- Find content between last two `────` lines
- Match pattern: `❯\s*(.+?)\s*↵ send`
- Exclude empty input (`❯` only)

## Processing in permission_poller

**State:**
```python
last_suggestion: dict[str, str | None] = {}  # "chat:thread" → suggestion
```

**Logic:**
```python
suggestion = parse_input_suggestion(screen)
key = f"{project.chat_id}:{thread_id}"

if suggestion and suggestion != last_suggestion.get(key):
    # New suggestion — send 💡 with ReplyKeyboard
    batch = OutgoingBatch(
        chat_id=project.chat_id,
        thread_id=thread_id,
        messages=[{"text": "💡"}],
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=suggestion)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    await telegram_queue.enqueue_nowait(batch)
    last_suggestion[key] = suggestion

elif not suggestion:
    # Suggestion gone
    last_suggestion[key] = None
```

## Keyboard Removal

Automatic via `one_time_keyboard=True` — keyboard hides after user clicks button or sends any message.

## Thread Independence

- ReplyKeyboardMarkup is thread-specific in forum topics
- Each thread has own `suggestion_shown` state
- No cross-thread interference

## Integration with Activity Indicators

Both features:
- Parse from same tmux capture-pane output
- Process in permission_poller
- Use TelegramQueue for sending

**Order:** Parse thinking status first, then suggestion (suggestion appears after thinking ends).

## Edge Cases

1. **Long suggestion (>64 chars for placeholder)** — ReplyKeyboard button has no limit, ok
2. **Suggestion changes** — Update keyboard with new suggestion
3. **User types while suggestion shown** — Keyboard stays until explicit remove
4. **Multiple suggestions** — Only show latest one

## Testing

- Unit: `parse_input_suggestion()` with various formats
- E2E: Send message, wait for response, see suggestion button, click it
