# Permission & Progress Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect Claude Code permission prompts via tmux capture-pane and show interactive buttons in Telegram.

**Architecture:** При tool_use в jsonl начинаем polling tmux capture-pane. Парсим экран на наличие permission prompt (маркер ❯). Показываем inline кнопки в Telegram. При нажатии отправляем соответствующий ключ в tmux.

**Tech Stack:** Python 3.11+, aiogram 3.x (InlineKeyboardMarkup, CallbackQuery), tmux

**Design Doc:** `docs/designs/telegram-bridge.md` — секция "Permission & Progress Detection"

---

## Task 1: Screen Parser

**Files:**
- Create: `agent-tools/telegram-bridge/src/telegram_bridge/screen.py`
- Create: `agent-tools/telegram-bridge/tests/test_screen.py`

**Step 1: Write failing test for permission detection**

```python
# tests/test_screen.py
import pytest
from telegram_bridge.screen import parse_screen, PermissionPrompt, ToolProgress, Idle

PERMISSION_SCREEN = """
● Write(test.txt)

──────────────────────────────────────────────────────────
 Create file test.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello world
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create test.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. Type here to tell Claude what to do differently

 Esc to cancel
"""

def test_parse_permission_prompt():
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) >= 2
    assert "Yes" in result.options[0]

def test_parse_idle():
    idle_screen = "> some prompt\n──────────────"
    result = parse_screen(idle_screen)
    assert isinstance(result, Idle)
```

**Step 2: Run test to verify it fails**

Run: `cd agent-tools/telegram-bridge && pytest tests/test_screen.py -v`
Expected: FAIL (module not found)

**Step 3: Implement screen parser**

```python
# src/telegram_bridge/screen.py
import re
from dataclasses import dataclass

@dataclass
class PermissionPrompt:
    options: list[str]  # ["1. Yes", "2. Yes, allow all...", ...]

@dataclass
class ToolProgress:
    tool: str
    output: str

@dataclass
class Idle:
    pass

ScreenState = PermissionPrompt | ToolProgress | Idle

def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state."""

    # Permission prompt: look for ❯ marker with numbered options
    if "❯" in output:
        options = []
        for line in output.split("\n"):
            # Match lines like "❯ 1. Yes" or "  2. Yes, allow..."
            match = re.match(r'\s*[❯\s]\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
        if options:
            return PermissionPrompt(options=options)

    # Tool progress: look for ● or ✶ with tool name
    progress_match = re.search(r'[●✶]\s*(\w+)\(([^)]*)\)', output)
    if progress_match and "❯" not in output:
        tool = progress_match.group(1)
        # Extract recent output (last lines before prompt)
        lines = output.strip().split("\n")
        output_lines = []
        for line in lines:
            if line.strip().startswith("⎿") or (line.strip() and not line.strip().startswith(("●", "✶", ">", "─"))):
                output_lines.append(line.strip())
        return ToolProgress(tool=tool, output="\n".join(output_lines[-5:]))

    return Idle()
```

**Step 4: Run test to verify it passes**

Run: `cd agent-tools/telegram-bridge && pytest tests/test_screen.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/screen.py agent-tools/telegram-bridge/tests/test_screen.py
git commit -m "feat(telegram-bridge): screen parser for permission detection"
```

---

## Task 2: Tmux Capture Function

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/tmux.py`
- Modify: `agent-tools/telegram-bridge/tests/test_tmux.py`

**Step 1: Add capture_pane method to TmuxSession**

```python
# Add to tmux.py TmuxSession class:

def capture_pane(self) -> str:
    """Capture current pane content."""
    session = shlex.quote(self.name)
    result = subprocess.run(
        f"tmux capture-pane -t {session} -p",
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout if result.returncode == 0 else ""
```

**Step 2: Test manually**

Run: `python -c "from telegram_bridge.tmux import TmuxSession; s = TmuxSession('test', '/tmp'); print(repr(s.capture_pane()))"`

**Step 3: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/tmux.py
git commit -m "feat(telegram-bridge): add capture_pane to TmuxSession"
```

---

## Task 3: Inline Keyboard for Permissions

**Files:**
- Create: `agent-tools/telegram-bridge/src/telegram_bridge/keyboards.py`

**Step 1: Create keyboard builder**

```python
# src/telegram_bridge/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def permission_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    """Build inline keyboard from permission options."""
    buttons = []

    for opt in options[:3]:  # Max 3 options
        # Extract number from "1. Yes" -> "1"
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip()[:20]  # Truncate label
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"perm:{num}"
        )])

    # Always add Esc button
    buttons.append([InlineKeyboardButton(
        text="❌ Cancel",
        callback_data="perm:esc"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/keyboards.py
git commit -m "feat(telegram-bridge): inline keyboard for permissions"
```

---

## Task 4: Callback Handler

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/bot.py`

**Step 1: Add callback query handler**

```python
# Add to bot.py:
from aiogram import F
from aiogram.types import CallbackQuery

@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press."""
    if callback.message.chat.id != settings.chat_id:
        return

    action = callback.data.split(":")[1]
    s = get_session()

    if action == "esc":
        s.send_key("Escape")
        await callback.answer("Cancelled")
    else:
        # Send the number key
        s.send_key(action)
        await callback.answer(f"Sent: {action}")

    # Remove keyboard after action
    await callback.message.edit_reply_markup(reply_markup=None)
```

**Step 2: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): callback handler for permission buttons"
```

---

## Task 5: Permission Polling Integration

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/main.py`

**⚠️ Архитектурное замечание:**
- Контент permission НЕ попадает в jsonl
- После выбора permission он пропадает из истории Claude
- Нужно: удалять сообщение(я) из Telegram после выбора
- Permission может быть длинным (несколько чанков) — трекать все message_id и удалять

**Step 1: Add permission polling to watcher_task**

```python
# Add imports at top of main.py:
from .screen import parse_screen, PermissionPrompt, ToolProgress
from .keyboards import permission_keyboard

# Replace the tool_use handling in watcher_task:

elif entry.content_type == ContentType.TOOL_USE:
    # Send tool info
    tool_info = format_tool_use(entry.tool_name, entry.tool_input)
    msg = await bot.send_message(settings.chat_id, tool_info, parse_mode="Markdown")

    # Start polling for permission/progress
    s = get_session()
    last_state = None

    while True:
        await asyncio.sleep(0.5)

        screen = s.capture_pane()
        state = parse_screen(screen)

        if isinstance(state, PermissionPrompt):
            if last_state != state.options:
                kb = permission_keyboard(state.options)
                await msg.edit_reply_markup(reply_markup=kb)
                last_state = state.options

        elif isinstance(state, ToolProgress):
            # Could update message with progress here
            pass

        else:
            # Idle - permission was handled or tool finished
            break

        # Check if tool_result appeared (need to peek jsonl)
        # For now, rely on state detection
```

**Step 2: Test end-to-end**

1. Start Claude Code in tmux
2. Start bridge: `python -m telegram_bridge.main`
3. Send message that triggers permission (e.g., "create file test.txt")
4. Verify buttons appear in Telegram
5. Press button, verify action sent to tmux

**Step 3: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/main.py
git commit -m "feat(telegram-bridge): permission polling integration"
```

---

## Task 6: Watcher tool_result Detection

**Files:**
- Modify: `agent-tools/telegram-bridge/src/telegram_bridge/watcher.py`

**Step 1: Add tool_result parsing**

```python
# Update parse_jsonl_entry to handle user entries with tool_result:

def parse_jsonl_entry(entry: dict) -> ParsedEntry | None:
    entry_type = entry.get("type")

    # Tool results come in "user" entries
    if entry_type == "user":
        message = entry.get("message", {})
        content = message.get("content", [])
        for item in content:
            if item.get("type") == "tool_result":
                return ParsedEntry(
                    content_type=ContentType.TOOL_RESULT,
                    text=str(item.get("content", ""))[:500],
                    is_complete=True
                )
        return None

    # Rest of existing code for assistant entries...
```

**Step 2: Update main.py to stop polling on tool_result**

The polling loop should check for tool_result to know when to stop.

**Step 3: Commit**

```bash
git add agent-tools/telegram-bridge/src/telegram_bridge/watcher.py
git commit -m "feat(telegram-bridge): parse tool_result from jsonl"
```

---

## Summary

| Task | Component | Ключевое |
|------|-----------|----------|
| 1 | Screen Parser | Парсинг ❯ для permission detection |
| 2 | Capture Pane | Метод capture_pane в TmuxSession |
| 3 | Keyboards | InlineKeyboardMarkup для опций |
| 4 | Callback Handler | Обработка нажатий кнопок |
| 5 | Polling Integration | Цикл между tool_use и tool_result |
| 6 | tool_result Detection | Парсинг user entries в jsonl |

**После выполнения:** Permissions показываются с кнопками в Telegram, можно одобрять/отклонять не заходя в терминал.
