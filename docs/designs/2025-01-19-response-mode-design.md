# Response Mode Design

## Overview

Per-thread setting that controls when the bot responds to messages. Three modes cycle via `/response_mode` command or settings button.

## Modes

| Mode | Behavior | Explanation |
|------|----------|-------------|
| `all` | Responds to everything | _responds to all messages_ |
| `polite` | Ignores messages directed at others | _doesn't reply others' mentions_ |
| `mentions` | Only responds when explicitly called | _only when mentioned_ |

**Default**: `all`

## Mode Logic

### `all` (default)
- Responds to all messages

### `polite`
Ignores message if:
- Has `@someone` (not bot) AND no `@bot` mention
- OR is reply to someone else's message AND no `@bot` mention

Responds otherwise.

### `mentions`
Responds only if:
- Has `@bot` mention
- OR is reply to bot's message
- OR is command with bot mention (`/cmd@bot`)

### Scope

- **Thread chats (forum topics)**: Uses `thread.response_mode`
- **Non-thread chats**: Uses `project.response_mode`
- **Private chats**: Response mode ignored, always responds

## Data Model

```python
# session_manager.py

@dataclass
class ThreadInfo:
    response_mode: str = "all"
    # ... existing fields

@dataclass
class ProjectState:
    response_mode: str = "all"  # for non-thread chats
    # ... existing fields
```

**Persistence**: Save to `~/.codogram/config.json` like other settings.

**Cascade**: thread.response_mode → project.response_mode → `"all"`

## Filtering Service

New service `ResponseModeService` in `services/response_mode.py`:

```python
from dataclasses import dataclass
from aiogram.enums import MessageEntityType

@dataclass
class FilterResult:
    should_respond: bool
    reason: str  # for logging

class ResponseModeService:
    def __init__(self, bot_id: int, bot_username: str):
        self.bot_id = bot_id
        self.bot_username = bot_username.lower().lstrip('@')

    def should_respond(
        self,
        mode: str,
        text: str | None,
        entities: list | None,
        reply_to_user_id: int | None,  # extracted from message, None if no reply or deleted user
    ) -> FilterResult:
        """
        Check if bot should respond based on response mode.

        Args:
            mode: "all", "polite", or "mentions"
            text: message.text or message.caption (can be None for media-only)
            entities: message.entities or message.caption_entities
            reply_to_user_id: from_user.id of replied message (None if no reply or user deleted)
        """
        text = text or ""
        entities = entities or []

        if mode == "all":
            return FilterResult(True, "mode=all")

        has_bot_mention = self._has_bot_mention(text, entities)
        is_reply_to_bot = reply_to_user_id == self.bot_id if reply_to_user_id else False

        if mode == "mentions":
            if has_bot_mention or is_reply_to_bot:
                return FilterResult(True, "mentioned or replied to bot")
            return FilterResult(False, "not mentioned")

        if mode == "polite":
            has_other_mention = self._has_other_mention(text, entities)
            is_reply_to_other = reply_to_user_id is not None and reply_to_user_id != self.bot_id

            if (has_other_mention or is_reply_to_other) and not has_bot_mention:
                return FilterResult(False, "directed at others")
            return FilterResult(True, "general message")

        return FilterResult(True, "unknown mode, default allow")

    def _has_bot_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions the bot."""
        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip('@')
                if mention == self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id == self.bot_id:
                    return True
        return False

    def _has_other_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions someone other than the bot."""
        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip('@')
                if mention != self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id != self.bot_id:
                    return True
        return False
```

## Bot Identity Injection

Initialize in `main.py` and pass via dispatcher:

```python
# main.py

async def main():
    # ... existing setup ...

    # Get bot info for response mode filtering
    bot_info = await bot.get_me()
    response_mode_service = ResponseModeService(
        bot_id=bot_info.id,
        bot_username=bot_info.username,
    )
    dp["response_mode_service"] = response_mode_service

    # ... rest of setup ...
```

## Integration Point

Filter in `handlers/messages.py` before routing.

**Key insight**: Commands like `/settings`, `/help` are handled by their own routers BEFORE reaching `messages.py`. So no special bypass needed — those commands never hit the filter.

```python
# handlers/messages.py

@router.message(F.text | F.caption | F.photo | F.document)
async def on_message(
    message: Message,
    telegram_queue: TelegramQueue,
    response_mode_service: ResponseModeService,  # injected by aiogram DI
):
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    # Get project and thread
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return  # not registered

    thread = project.threads.get(thread_id) if thread_id else None
    mode = thread.response_mode if thread else project.response_mode

    # Skip filtering for private chats
    if message.chat.type == "private":
        mode = "all"

    # Extract reply info (with null safety)
    reply_to_user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        reply_to_user_id = message.reply_to_message.from_user.id

    # Check if should respond
    text = message.text or message.caption
    entities = message.entities or message.caption_entities

    result = response_mode_service.should_respond(
        mode=mode,
        text=text,
        entities=entities,
        reply_to_user_id=reply_to_user_id,
    )

    if not result.should_respond:
        logger.info(f"Skipping message in {mode} mode: {result.reason}")
        return

    # Continue with normal routing...
    await _route_message(message, telegram_queue)
```

## Message Types Handling

| Message Type | Text Source | Entities Source | Default Behavior |
|--------------|-------------|-----------------|------------------|
| Text | `message.text` | `message.entities` | Normal filtering |
| Photo with caption | `message.caption` | `message.caption_entities` | Normal filtering |
| Document with caption | `message.caption` | `message.caption_entities` | Normal filtering |
| Media-only (no caption) | `None` | `None` | Respond (can't mention) |
| Sticker | `None` | `None` | Respond (can't mention) |
| Voice (after transcription) | transcribed text | `None` | Normal filtering |
| Forwarded | original text | original entities | Respond (user forwarded intentionally) |

## Settings UI

### Command `/response_mode`

Cycles: `all` → `polite` → `mentions` → `all`

Response format:
```
response mode: polite
_doesn't reply others' mentions_
```

### Settings keyboard

Button shows command only (consistent with existing buttons):
```
[/response_mode]
```

Value shown in settings text above keyboard.

### Settings display

In `/settings` output, under thread/chat settings:
```
• response_mode: polite
```

### Callback handler

```python
# handlers/settings.py

# Add to callback_settings():
elif action == "rm":  # response_mode
    modes = ["all", "polite", "mentions"]
    current = thread.response_mode if thread else project.response_mode
    next_idx = (modes.index(current) + 1) % len(modes)
    next_mode = modes[next_idx]

    if thread:
        thread.response_mode = next_mode
    else:
        project.response_mode = next_mode
    project_manager._save()
```

## Files to Modify

1. `session_manager.py` — add `response_mode` field to `ThreadInfo` and `ProjectState`
2. `services/response_mode.py` — new `ResponseModeService` (create file)
3. `main.py` — initialize service with bot info, inject into dispatcher
4. `handlers/messages.py` — integrate filter before routing
5. `handlers/settings.py` — add `/response_mode` command and callback
6. `keyboards/settings.py` — add `/response_mode` button

## Edge Cases

| Case | Handling |
|------|----------|
| Bot username with @ prefix | Strip @ in service init |
| `reply_to_message.from_user` is None | Treat as no reply (deleted user, anonymous admin) |
| TEXT_MENTION entity | Check `entity.user.id` for bot comparison |
| Media-only message (no text/caption) | Respond — can't contain mentions |
| Forwarded message | Respond — user forwarded intentionally |
| Edited message | Not supported (not in `allowed_updates`) |
| Private chat | Mode ignored, always `all` |
| Command with mention `/cmd@bot` | Handled by command routers before filter |

## Not Supported

- **Edited messages**: Bot doesn't receive `edited_message` events
- **Inline queries**: Different handler, not affected by response mode
