# Background Permission Poller Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить blocking polling на независимый background poller для permission detection.

**Architecture:** Два независимых asyncio task — watcher (jsonl, non-blocking) и permission_poller (tmux, state machine с debounce). Shared state через `state.py`.

**Tech Stack:** Python 3.11, asyncio, aiogram 3.x

**Design:** `docs/designs/2025-12-24-background-permission-poller.md`

---

### Task 1: Fix watcher.py string bug

**Files:**
- Modify: `src/telegram_bridge/watcher.py:30-31, 45-46`
- Test: `tests/test_watcher.py`

**Step 1: Write failing test**

```python
# tests/test_watcher.py
from telegram_bridge.watcher import parse_jsonl_entry, ContentType

def test_parse_jsonl_entry_handles_string_in_content():
    """content может содержать строки, не только dict."""
    entry = {
        "type": "user",
        "message": {
            "content": ["string item", {"type": "tool_result", "content": "result"}]
        }
    }
    result = parse_jsonl_entry(entry)
    assert result is not None
    assert result.content_type == ContentType.TOOL_RESULT

def test_parse_jsonl_entry_handles_string_in_assistant_content():
    entry = {
        "type": "assistant",
        "message": {
            "content": ["string item", {"type": "text", "text": "hello"}]
        }
    }
    result = parse_jsonl_entry(entry)
    assert result is not None
    assert result.content_type == ContentType.TEXT
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge && source /home/superbereza/dev/personal-agent/venv/bin/activate && pytest tests/test_watcher.py -v`

Expected: FAIL with `AttributeError: 'str' object has no attribute 'get'`

**Step 3: Write minimal implementation**

В `src/telegram_bridge/watcher.py` добавить проверку isinstance:

```python
# Line 30-31: в user entries loop
for item in content:
    if not isinstance(item, dict):
        continue
    if item.get("type") == "tool_result":

# Line 45-46: в assistant entries loop
for item in content:
    if not isinstance(item, dict):
        continue
    item_type = item.get("type")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_watcher.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/watcher.py tests/test_watcher.py
git commit -m "fix(telegram-bridge): handle strings in jsonl content array"
```

---

### Task 2: Create PollerState enum

**Files:**
- Create: `src/telegram_bridge/permission_poller.py`
- Test: `tests/test_permission_poller.py`

**Step 1: Write failing test**

```python
# tests/test_permission_poller.py
from telegram_bridge.permission_poller import PollerState

def test_poller_state_enum():
    assert PollerState.IDLE.value == "idle"
    assert PollerState.DEBOUNCING.value == "debouncing"
    assert PollerState.SHOWING.value == "showing"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_permission_poller.py::test_poller_state_enum -v`

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/telegram_bridge/permission_poller.py
"""Background permission poller - independent of jsonl watcher."""
from enum import Enum


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_permission_poller.py::test_poller_state_enum -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/permission_poller.py tests/test_permission_poller.py
git commit -m "feat(telegram-bridge): add PollerState enum"
```

---

### Task 3: Create format_permission_content function

**Files:**
- Modify: `src/telegram_bridge/permission_poller.py`
- Test: `tests/test_permission_poller.py`

**Step 1: Write failing test**

```python
# tests/test_permission_poller.py (добавить)
from telegram_bridge.permission_poller import format_permission_content
from telegram_bridge.screen import PermissionPrompt

def test_format_permission_content_full():
    perm = PermissionPrompt(
        options=["1. Yes"],
        description="Create file test.txt",
        content="+ new content",
        question="Allow?"
    )
    result = format_permission_content(perm)
    assert "Create file test.txt" in result
    assert "+ new content" in result
    assert "Allow?" in result

def test_format_permission_content_minimal():
    perm = PermissionPrompt(options=["1. Yes"])
    result = format_permission_content(perm)
    assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_permission_poller.py::test_format_permission_content_full -v`

Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

```python
# src/telegram_bridge/permission_poller.py (добавить)
from dataclasses import dataclass

# Separators for Telegram display
SEPARATOR_SOLID = "─" * 20
SEPARATOR_DASHED = "╌" * 20


def format_permission_content(perm) -> str:
    """Format permission prompt content for Telegram display."""
    parts = []

    if perm.description:
        parts.append(SEPARATOR_SOLID)
        parts.append(perm.description)

    if perm.content:
        parts.append(SEPARATOR_DASHED)
        parts.append(perm.content)
        parts.append(SEPARATOR_DASHED)

    if perm.question:
        parts.append(perm.question)

    return "\n".join(parts)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_permission_poller.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/permission_poller.py tests/test_permission_poller.py
git commit -m "feat(telegram-bridge): add format_permission_content"
```

---

### Task 4: Create permission_poller_task skeleton

**Files:**
- Modify: `src/telegram_bridge/permission_poller.py`

**Step 1: Write the skeleton**

```python
# src/telegram_bridge/permission_poller.py (добавить)
import asyncio
from aiogram import Bot

from .config import settings
from .screen import parse_screen, PermissionPrompt
from .keyboards import permission_keyboard
from .chunker import chunk_message
from .state import permission_messages


async def permission_poller_task(bot: Bot, get_session_fn):
    """
    Background poller for permission prompts.

    Polls tmux every 0.5s, uses debounce before sending.
    State machine: IDLE → DEBOUNCING → SHOWING → IDLE
    """
    print("Permission poller: started")

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    content_msg_ids: list[int] = []
    kb_msg = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            session = get_session_fn()
            screen = session.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            print(f"Permission poller: capture error: {e}")
            continue

        is_permission = isinstance(parsed, PermissionPrompt)

        # State machine transitions - Task 5
        pass
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/telegram_bridge/permission_poller.py`

Expected: No output (success)

**Step 3: Commit**

```bash
git add src/telegram_bridge/permission_poller.py
git commit -m "feat(telegram-bridge): permission_poller_task skeleton"
```

---

### Task 5: Implement state machine transitions

**Files:**
- Modify: `src/telegram_bridge/permission_poller.py`

**Step 1: Replace `pass` with state machine logic**

```python
        # Replace the "pass" at the end of the while loop with:

        if state == PollerState.IDLE:
            if is_permission:
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    # Send to Telegram
                    try:
                        content_text = format_permission_content(parsed)
                        content_msg_ids = []

                        if content_text.strip():
                            for chunk in chunk_message(content_text):
                                try:
                                    msg = await bot.send_message(
                                        settings.chat_id, chunk, parse_mode="Markdown"
                                    )
                                except Exception:
                                    msg = await bot.send_message(settings.chat_id, chunk)
                                content_msg_ids.append(msg.message_id)

                        kb = permission_keyboard(parsed.options)
                        kb_msg = await bot.send_message(
                            settings.chat_id, "👆", reply_markup=kb
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        print(f"Permission poller: sent {len(parsed.options)} options")
                    except Exception as e:
                        print(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                # Cleanup if messages still exist
                if kb_msg and kb_msg.message_id in permission_messages:
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(settings.chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(settings.chat_id, kb_msg.message_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg.message_id, None)

                state = PollerState.IDLE
                last_options = None
                content_msg_ids = []
                kb_msg = None
            elif parsed.options != last_options:
                try:
                    kb = permission_keyboard(parsed.options)
                    if kb_msg:
                        await kb_msg.edit_reply_markup(reply_markup=kb)
                    last_options = parsed.options
                except Exception:
                    pass
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/telegram_bridge/permission_poller.py`

Expected: No output (success)

**Step 3: Commit**

```bash
git add src/telegram_bridge/permission_poller.py
git commit -m "feat(telegram-bridge): implement poller state machine"
```

---

### Task 6: Refactor main.py

**Files:**
- Modify: `src/telegram_bridge/main.py`

**Step 1: Remove blocking loop and start poller**

Изменения в `main.py`:

1. Заменить импорты (убрать неиспользуемые, добавить poller):
```python
# Убрать: from .screen import parse_screen, PermissionPrompt, ToolProgress
# Убрать: from .keyboards import permission_keyboard
# Убрать: from .state import permission_messages
# Убрать: SEPARATOR_SOLID, SEPARATOR_DASHED, format_permission_content

# Добавить:
from .permission_poller import permission_poller_task
```

2. Заменить TOOL_USE handler (строки ~115-167):
```python
elif entry.content_type == ContentType.TOOL_USE:
    # Just send tool info, permissions handled by background poller
    text = format_tool_use(entry.tool_name, entry.tool_input)
    try:
        await bot.send_message(settings.chat_id, text, parse_mode="Markdown")
    except Exception:
        await bot.send_message(settings.chat_id, f"● {entry.tool_name}")
```

3. Добавить запуск poller в main():
```python
asyncio.create_task(watcher_task(bot))
asyncio.create_task(permission_poller_task(bot, get_session))  # Добавить
await dp.start_polling(bot)
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/telegram_bridge/main.py`

Expected: No output (success)

**Step 3: Commit**

```bash
git add src/telegram_bridge/main.py
git commit -m "refactor(telegram-bridge): use background permission poller"
```

---

### Task 7: Integration test

**Files:** None (manual testing)

**Step 1: Restart bot**

```bash
/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/restart.sh
```

**Step 2: Check logs**

```bash
sleep 2 && cat /tmp/tg-bot.log
```

Expected: No errors, should see "Permission poller: started"

**Step 3: Test permission flow**

1. Триггерни permission в Claude (создай файл)
2. Проверь что появляется контент + кнопки в Telegram
3. Нажми кнопку — должно удалиться

**Step 4: Commit all and push**

```bash
git push
```
