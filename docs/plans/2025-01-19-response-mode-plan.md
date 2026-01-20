# Response Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-thread response mode setting that controls when bot responds to messages (all/polite/mentions).

**Architecture:** New `ResponseModeService` filters messages before routing. Setting stored in `ThreadInfo`/`ProjectState`, persisted to config. UI via `/response_mode` command and settings keyboard button.

**Tech Stack:** Python 3.11, aiogram 3.x, pytest

---

## Task 1: Add response_mode field to data models ✅ DONE

**Status:** Already implemented by previous subagent.

**Files changed:**
- `src/codogram/session_manager.py` - Added `response_mode: str = "all"` to both `ThreadInfo` and `ProjectState`
- `tests/unit/services/test_response_mode.py` - Created with 2 tests

**Commit:** `feat: add response_mode field to ThreadInfo and ProjectState`

---

## Task 2: Add persistence for response_mode

**Files:**
- Modify: `src/codogram/session_manager.py` (_load_projects and _save)
- Test: `tests/unit/services/test_response_mode.py`

### Step 1: Add test for loading response_mode from thread data

```python
def test_load_response_mode_from_thread_data():
    """response_mode is loaded from thread data."""
    from codogram.session_manager import ThreadInfo

    thread_data = {
        "name": "test",
        "response_mode": "polite",
    }

    thread = ThreadInfo(
        thread_id=123,
        name=thread_data.get("name", "main"),
        response_mode=thread_data.get("response_mode", "all"),
    )

    assert thread.response_mode == "polite"
```

### Step 2: Run test

Run: `PYTHONPATH=src pytest tests/unit/services/test_response_mode.py::test_load_response_mode_from_thread_data -v`
Expected: PASS

### Step 3: Update _load_projects - add response_mode to ThreadInfo creation

Find in `_load_projects` where ThreadInfo is created for threads, add:

```python
response_mode=thread_data.get("response_mode", "all"),
```

### Step 4: Update _load_projects - add response_mode for ProjectState

Find where project settings are loaded (near `project.auto_accept = ...`), add:

```python
project.response_mode = data.get("response_mode", "all")
```

### Step 5: Update _save - add response_mode for threads

Find in `_save` where thread_data is built, add after `feat_thinking_status`:

```python
if t.response_mode != "all":
    thread_data["response_mode"] = t.response_mode
```

### Step 6: Update _save - add response_mode for ProjectState

Find in `_save` where project_data dict is built, add:

```python
if p.response_mode != "all":
    project_data["response_mode"] = p.response_mode
```

### Step 7: Run all tests

Run: `PYTHONPATH=src pytest tests/unit/services/test_response_mode.py -v`
Expected: PASS

### Step 8: Commit

```bash
git add src/codogram/session_manager.py tests/unit/services/test_response_mode.py
git commit -m "feat: persist response_mode to config (thread + project level)"
```

---

## Task 3: Create ResponseModeService

**Files:**
- Create: `src/codogram/services/response_mode.py`
- Test: `tests/unit/services/test_response_mode.py`

### Step 1: Add test for mode "all"

```python
def test_response_mode_all_always_responds():
    """Mode 'all' responds to everything."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="all",
        text="Hello world",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "mode=all"
```

### Step 2: Run test to verify it fails

Run: `PYTHONPATH=src pytest tests/unit/services/test_response_mode.py::test_response_mode_all_always_responds -v`
Expected: FAIL with "ModuleNotFoundError"

### Step 3: Create service with minimal implementation

Create `src/codogram/services/response_mode.py`:

```python
"""Response mode filtering service."""

from dataclasses import dataclass


@dataclass
class FilterResult:
    """Result of response mode filtering."""
    should_respond: bool
    reason: str


class ResponseModeService:
    """Service to determine if bot should respond based on response mode."""

    VALID_MODES = ("all", "polite", "mentions")

    def __init__(self, bot_id: int, bot_username: str):
        self.bot_id = bot_id
        self.bot_username = bot_username.lower().lstrip("@")

    def should_respond(
        self,
        mode: str,
        text: str | None,
        entities: list | None,
        reply_to_user_id: int | None,
    ) -> FilterResult:
        """Check if bot should respond based on response mode."""
        text = text or ""
        entities = entities or []

        # Fallback for invalid mode
        if mode not in self.VALID_MODES:
            return FilterResult(True, "invalid mode, default allow")

        if mode == "all":
            return FilterResult(True, "mode=all")

        # Media-only messages (no text, no entities) - always respond
        # Can't contain mentions, so bypass filter
        if not text and not entities:
            return FilterResult(True, "media-only message")

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

        return FilterResult(True, "unknown mode")

    def _has_bot_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions the bot."""
        from aiogram.enums import MessageEntityType

        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip("@")
                if mention == self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id == self.bot_id:
                    return True
        return False

    def _has_other_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions someone other than the bot."""
        from aiogram.enums import MessageEntityType

        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip("@")
                if mention != self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id != self.bot_id:
                    return True
        return False
```

### Step 4: Add remaining tests

```python
def test_response_mode_mentions_ignores_without_mention():
    """Mode 'mentions' ignores messages without bot mention."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="mentions",
        text="Hello @someone",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is False
    assert result.reason == "not mentioned"


def test_response_mode_mentions_responds_to_bot_mention():
    """Mode 'mentions' responds when bot is mentioned."""
    from unittest.mock import MagicMock
    from aiogram.enums import MessageEntityType
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    entity = MagicMock()
    entity.type = MessageEntityType.MENTION
    entity.offset = 0
    entity.length = 8

    result = service.should_respond(
        mode="mentions",
        text="@testbot hello",
        entities=[entity],
        reply_to_user_id=None,
    )

    assert result.should_respond is True


def test_response_mode_mentions_responds_to_reply():
    """Mode 'mentions' responds when replying to bot's message."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="mentions",
        text="thanks!",
        entities=[],
        reply_to_user_id=123,
    )

    assert result.should_respond is True


def test_response_mode_polite_ignores_other_mentions():
    """Mode 'polite' ignores messages with other mentions."""
    from unittest.mock import MagicMock
    from aiogram.enums import MessageEntityType
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    entity = MagicMock()
    entity.type = MessageEntityType.MENTION
    entity.offset = 0
    entity.length = 5

    result = service.should_respond(
        mode="polite",
        text="@john hello",
        entities=[entity],
        reply_to_user_id=None,
    )

    assert result.should_respond is False
    assert result.reason == "directed at others"


def test_response_mode_polite_responds_to_general():
    """Mode 'polite' responds to messages without mentions."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="polite",
        text="hello everyone",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "general message"
```

### Step 5: Run all service tests

Run: `PYTHONPATH=src pytest tests/unit/services/test_response_mode.py -v`
Expected: All PASS

### Step 6: Commit

```bash
git add src/codogram/services/response_mode.py tests/unit/services/test_response_mode.py
git commit -m "feat: implement ResponseModeService with all/polite/mentions modes"
```

---

## Task 4: Initialize service in main.py

**Files:**
- Modify: `src/codogram/main.py`

### Step 1: Add import and initialization

After `dp["telegram_queue"] = telegram_queue`, add:

```python
    # Get bot info for response mode filtering
    bot_info = await bot.get_me()
    from .services.response_mode import ResponseModeService
    response_mode_service = ResponseModeService(
        bot_id=bot_info.id,
        bot_username=bot_info.username,
    )
    dp["response_mode_service"] = response_mode_service
```

### Step 2: Verify bot starts

Run: `./kill-instance-and-start-from-worktree.sh`
Expected: Bot starts without errors

### Step 3: Commit

```bash
git add src/codogram/main.py
git commit -m "feat: initialize ResponseModeService in main.py"
```

---

## Task 5: Integrate filter into messages handler

**Files:**
- Modify: `src/codogram/handlers/messages.py`

### Step 1: Add helper function for response mode filtering

Add at module level (before handlers):

```python
def _should_skip_by_response_mode(
    message: Message,
    response_mode_service,
) -> bool:
    """Check if message should be skipped based on response mode.

    Returns True if message should be skipped, False if should process.
    """
    # Skip filter for private chats
    if message.chat.type == "private":
        return False

    # Forwarded messages - always respond (user forwarded intentionally)
    if message.forward_date or message.forward_from or message.forward_from_chat:
        return False

    chat_id = message.chat.id
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return False  # No project = no filter

    thread = project.threads.get(thread_id) if thread_id is not None else project.threads.get(None)
    mode = thread.response_mode if thread else project.response_mode

    reply_to_user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        reply_to_user_id = message.reply_to_message.from_user.id

    text = message.text or message.caption
    entities = message.entities or message.caption_entities or []

    result = response_mode_service.should_respond(
        mode=mode,
        text=text,
        entities=entities,
        reply_to_user_id=reply_to_user_id,
    )

    if not result.should_respond:
        logger.info(f"Skipping message in {mode} mode: {result.reason}")
        return True

    return False
```

### Step 2: Update on_message handler

Add `response_mode_service=None` parameter and use helper:

```python
@router.message()
async def on_message(
    message: Message,
    telegram_queue: TelegramQueue,
    response_mode_service=None,
):
    """Route regular messages to tmux sessions."""
    if response_mode_service and _should_skip_by_response_mode(message, response_mode_service):
        return

    await _route_message(message, telegram_queue)
```

### Step 3: Update on_unknown_command handler

Find `on_unknown_command` handler and add the same filter:

```python
@router.message(F.text.startswith("/"))
async def on_unknown_command(
    message: Message,
    telegram_queue: TelegramQueue,
    response_mode_service=None,
):
    """Handle unknown commands - treat as regular messages."""
    if response_mode_service and _should_skip_by_response_mode(message, response_mode_service):
        return

    # ... existing logic
```

### Step 4: Verify bot still works

Run: `./kill-instance-and-start-from-worktree.sh`
Test: Send a message, verify it routes normally.

### Step 5: Commit

```bash
git add src/codogram/handlers/messages.py
git commit -m "feat: integrate ResponseModeService filter into message handlers"
```

---

## Task 6: Add strings and /response_mode command

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/handlers/settings.py`

### Step 1: Add strings to strings.py

Add at the end of strings.py (before any buttons section):

```python
# --- Response Mode ---

RESPONSE_MODE_ALL = "responds to all messages"
RESPONSE_MODE_POLITE = "doesn't reply others' mentions"
RESPONSE_MODE_MENTIONS = "only when mentioned"
```

### Step 2: Add command handler in settings.py

After `cmd_verbose`, add:

```python
@router.message(Command("response_mode", ignore_case=True))
async def cmd_response_mode(message: Message, telegram_queue: TelegramQueue):
    """Cycle response mode: all -> polite -> mentions -> all."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = None
    if project.threads:
        thread = project.threads.get(thread_id)

    # Cycle through modes
    modes = ["all", "polite", "mentions"]
    explanations = {
        "all": strings.RESPONSE_MODE_ALL,
        "polite": strings.RESPONSE_MODE_POLITE,
        "mentions": strings.RESPONSE_MODE_MENTIONS,
    }

    if thread:
        current = thread.response_mode
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0  # Invalid mode, reset to "all"
        thread.response_mode = modes[next_idx]
        new_mode = thread.response_mode
    else:
        current = project.response_mode
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0  # Invalid mode, reset to "all"
        project.response_mode = modes[next_idx]
        new_mode = project.response_mode

    project_manager._save()

    explanation = explanations.get(new_mode, "")
    await telegram_queue.reply(message, f"response mode: {new_mode}\n_{explanation}_")
```

### Step 3: Verify command works

Run: `./kill-instance-and-start-from-worktree.sh`
Test: Send `/response_mode` to cycle through modes.

### Step 4: Commit

```bash
git add src/codogram/strings.py src/codogram/handlers/settings.py
git commit -m "feat: add /response_mode command with strings"
```

---

## Task 7: Add response_mode to settings display

**Files:**
- Modify: `src/codogram/handlers/settings.py` (_build_settings_text)

### Step 1: Update _build_settings_text

After `lines.append(f"• verbose: {verbose_status}")`, add:

```python
    # Response mode
    response_mode = thread.response_mode if thread else project.response_mode
    lines.append(f"• response\\_mode: {response_mode}")
```

### Step 2: Verify /settings shows response_mode

Run: `./kill-instance-and-start-from-worktree.sh`
Test: Send `/settings` and verify `response_mode: all` appears.

### Step 3: Commit

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: show response_mode in /settings display"
```

---

## Task 8: Add button to settings keyboard

**Files:**
- Modify: `src/codogram/keyboards/settings.py`
- Test: `tests/unit/keyboards/test_settings.py`

### Step 1: Add test for new button

```python
def test_settings_keyboard_has_response_mode_button():
    """Settings keyboard includes /response_mode button."""
    kb = settings_keyboard("claude-test")

    assert len(kb.inline_keyboard) == 5
    assert kb.inline_keyboard[2][0].text == "/response_mode"


def test_settings_keyboard_response_mode_callback():
    """Response mode button has correct callback data."""
    kb = settings_keyboard("claude-test")
    sid = _short_id("claude-test")

    assert kb.inline_keyboard[2][0].callback_data == f"set:rm:{sid}"
```

### Step 2: Run tests to verify they fail

Run: `PYTHONPATH=src pytest tests/unit/keyboards/test_settings.py -v`
Expected: FAIL

### Step 3: Update settings_keyboard

Add new button after `/verbose`:

```python
        [InlineKeyboardButton(
            text="/response_mode",
            callback_data=f"set:rm:{sid}"
        )],
```

### Step 4: Update existing tests

Update row counts and indices in existing tests to account for 5 buttons.

### Step 5: Run tests

Run: `PYTHONPATH=src pytest tests/unit/keyboards/test_settings.py -v`
Expected: All PASS

### Step 6: Commit

```bash
git add src/codogram/keyboards/settings.py tests/unit/keyboards/test_settings.py
git commit -m "feat: add /response_mode button to settings keyboard"
```

---

## Task 9: Add callback handler for response_mode button

**Files:**
- Modify: `src/codogram/handlers/settings.py` (callback_settings)

### Step 1: Add handler for "rm" action

In `callback_settings`, after the `elif action == "m":` block, add:

```python
    elif action == "rm":  # response_mode
        modes = ["all", "polite", "mentions"]
        if thread:
            current = thread.response_mode
            try:
                next_idx = (modes.index(current) + 1) % len(modes)
            except ValueError:
                next_idx = 0  # Invalid mode, reset to "all"
            thread.response_mode = modes[next_idx]
            new_mode = thread.response_mode
        else:
            current = project.response_mode
            try:
                next_idx = (modes.index(current) + 1) % len(modes)
            except ValueError:
                next_idx = 0  # Invalid mode, reset to "all"
            project.response_mode = modes[next_idx]
            new_mode = project.response_mode
        project_manager._save()
        await callback.answer(f"Response: {new_mode}")
```

### Step 2: Verify callback works

Run: `./kill-instance-and-start-from-worktree.sh`
Test: Send `/settings`, click `/response_mode` button, verify it cycles.

### Step 3: Commit

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: add callback handler for response_mode button"
```

---

## Task 10: E2E Testing

**Files:** None (manual testing with Telegram MCP)

### Step 1: Ask user for test chat ID

Ask: "Which chat should I use for E2E testing?"

### Step 2: Test mode cycling

```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/response_mode")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
```

### Step 3: Test polite mode filtering

```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="@someone hello")
# Verify bot does NOT respond
```

### Step 4: Test mentions mode

```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/response_mode")  # cycle to mentions
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="hello")  # should be ignored
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="@bot hello")  # should respond
```

### Step 5: Reset to all mode

```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/response_mode")
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | Add response_mode field | ✅ DONE |
| 2 | Add persistence (thread + project) | Pending |
| 3 | Create ResponseModeService | Pending |
| 4 | Initialize in main.py | Pending |
| 5 | Integrate into messages handler | Pending |
| 6 | Add strings + /response_mode command | Pending |
| 7 | Add to settings display | Pending |
| 8 | Add keyboard button | Pending |
| 9 | Add callback handler | Pending |
| 10 | E2E Testing | Pending |
