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

**Exception for all modes**: Settings commands always work without mention:
- `/settings`, `/help`
- `/auto_accept`, `/verbose`, `/response_mode`
- `/exp_*` experimental settings
- Any command triggered via settings keyboard

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

## Filtering Logic

New service `ResponseModeFilter` in `services/response_mode.py`:

```python
@dataclass
class FilterResult:
    should_respond: bool
    reason: str  # for logging/debugging

class ResponseModeFilter:
    def __init__(self, bot_id: int, bot_username: str):
        self.bot_id = bot_id
        self.bot_username = bot_username.lower()

    def should_respond(
        self,
        mode: str,
        text: str,
        entities: list,  # message entities for @mentions
        reply_to_message: Message | None,
        is_settings_command: bool,
    ) -> FilterResult:
        # Settings commands always pass
        if is_settings_command:
            return FilterResult(True, "settings command")

        if mode == "all":
            return FilterResult(True, "mode=all")

        has_bot_mention = self._has_bot_mention(text, entities)
        is_reply_to_bot = self._is_reply_to_bot(reply_to_message)

        if mode == "mentions":
            if has_bot_mention or is_reply_to_bot:
                return FilterResult(True, "mentioned or replied to bot")
            return FilterResult(False, "not mentioned")

        if mode == "polite":
            has_other_mention = self._has_other_mention(entities)
            is_reply_to_other = self._is_reply_to_other(reply_to_message)

            if (has_other_mention or is_reply_to_other) and not has_bot_mention:
                return FilterResult(False, "directed at others")
            return FilterResult(True, "not directed at others")

        return FilterResult(True, "unknown mode, default allow")
```

## Integration Point

Filter in `handlers/messages.py` before routing:

```python
async def on_message(message: Message, ...):
    # Early exit for settings commands
    if _is_settings_command(message.text):
        # route normally
        ...

    # Get response mode
    thread = project.threads.get(thread_id)
    mode = thread.response_mode if thread else project.response_mode

    # Filter
    result = response_filter.should_respond(
        mode=mode,
        text=message.text,
        entities=message.entities,
        reply_to_message=message.reply_to_message,
        is_settings_command=False,
    )

    if not result.should_respond:
        logger.debug(f"Skipping message: {result.reason}")
        return  # Silent ignore

    # Continue with normal routing
    ...
```

## Settings UI

### Command `/response_mode`

Cycles: `all` → `polite` → `mentions` → `all`

Response:
```
Response mode: polite
_doesn't reply others' mentions_
```

### Settings keyboard

Button shows current mode, cycles on press:
```
[/response_mode: all]  →  [/response_mode: polite]  →  [/response_mode: mentions]
```

### Settings display

In `/settings` output:
```
• response_mode: polite
```

## Settings Commands (Always Allowed)

These commands bypass response mode filtering:
- `/settings`
- `/help`
- `/auto_accept`
- `/verbose`
- `/response_mode`
- `/exp_thinking_status`
- `/exp_suggestions`
- `/exp_avatar_pack`
- `/thread_create`, `/thread_delete` (management)
- `/branch_create`, `/branch_finish` (management)

## Files to Modify

1. `session_manager.py` — add `response_mode` field to `ThreadInfo` and `ProjectState`
2. `services/response_mode.py` — new `ResponseModeFilter` service
3. `handlers/messages.py` — integrate filter before routing
4. `handlers/settings.py` — add `/response_mode` command and callback
5. `keyboards/settings.py` — add button to settings keyboard

## Edge Cases

1. **Bot username detection**: Get from `bot.get_me()` at startup, store in filter
2. **Entities parsing**: Use `message.entities` to find `MessageEntityType.MENTION`
3. **Reply detection**: Check `message.reply_to_message.from_user.id == bot_id`
4. **Command with mention**: Parse `/cmd@username` format
5. **Empty thread**: Fall back to project.response_mode
