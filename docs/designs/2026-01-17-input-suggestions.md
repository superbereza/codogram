# Input Suggestions

## Overview

Show Claude's input suggestions in Telegram as clickable buttons.

**What happens in Claude:**
- After response, suggestion appears in input box
- Format: `❯ посмотри что залогировалось                    ↵ send`

**What user sees in Telegram:**
- ReplyKeyboardMarkup with suggestion text as button
- Click → text sent to Claude
- After any message sent → keyboard removed

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

**New state:**
```python
suggestion_shown: bool = False
last_suggestion: str | None = None
```

**Logic:**
```python
suggestion = parse_input_suggestion(screen)

if suggestion and suggestion != last_suggestion:
    # Show new suggestion
    batch = OutgoingBatch(
        chat_id=chat_id,
        thread_id=thread_id,
        messages=[{"text": "💡"}],
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=suggestion)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    await telegram_queue.enqueue(batch)
    suggestion_shown = True
    last_suggestion = suggestion

elif suggestion_shown and not suggestion:
    # Suggestion gone (user typed something)
    # Remove keyboard on next user message
    suggestion_shown = False
    last_suggestion = None
```

## Keyboard Removal

When user sends any message to the thread:
```python
# In message handler
if suggestion_shown_for_thread(thread_id):
    await bot.send_message(
        chat_id=chat_id,
        message_thread_id=thread_id,
        text="✓",  # or invisible character
        reply_markup=ReplyKeyboardRemove(),
    )
```

**Alternative:** Track in permission_poller — when input box has user text (not suggestion), send ReplyKeyboardRemove.

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
