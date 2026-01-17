# Input Suggestions

## Overview

Show Claude's input suggestions in Telegram as clickable buttons.

**What happens in Claude:**
- After response, suggestion appears in input box
- Format: `❯ посмотри что залогировалось                    ↵ send`

**What user sees in Telegram:**
- Claude's response arrives with ReplyKeyboardMarkup (suggestion as button)
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

## SuggestionProvider Mediator

Bridge between Poller (producer) and Watcher (consumer). Suggestion is sent WITH Claude's response, not as separate message.

**Class:**
```python
class SuggestionProvider:
    """Bridge between Poller (producer) and Watcher (consumer)."""

    def __init__(self):
        self._suggestions: dict[str, str] = {}  # key → suggestion
        self._events: dict[str, asyncio.Event] = {}

    def set_suggestion(self, chat_id: int, thread_id: int | None, suggestion: str | None):
        """Called by Poller when suggestion found/cleared."""
        key = f"{chat_id}:{thread_id}"
        if suggestion:
            self._suggestions[key] = suggestion
            if key in self._events:
                self._events[key].set()
        else:
            self._suggestions.pop(key, None)

    async def wait_for_suggestion(self, chat_id: int, thread_id: int | None, timeout: float = 1.0) -> str | None:
        """Called by Watcher before sending response."""
        key = f"{chat_id}:{thread_id}"

        if key in self._suggestions:
            return self._suggestions.pop(key)

        event = self._events.setdefault(key, asyncio.Event())
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return self._suggestions.pop(key, None)
        except asyncio.TimeoutError:
            return None
```

## Processing in permission_poller

**Logic (producer):**
```python
suggestion = parse_input_suggestion(screen)
suggestion_provider.set_suggestion(project.chat_id, thread_id, suggestion)
```

## Processing in watcher

**Logic (consumer):**
```python
# Before sending response
suggestion = await suggestion_provider.wait_for_suggestion(chat_id, thread_id, timeout=1.0)

reply_markup = None
if suggestion:
    reply_markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=suggestion)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

batch = OutgoingBatch(
    chat_id=chat_id,
    thread_id=thread_id,
    messages=[{"text": response}],
    reply_markup=reply_markup,
)
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
