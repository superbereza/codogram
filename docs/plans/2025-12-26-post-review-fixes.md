# Post-Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all issues from code review: critical bug, remove backwards compat, cleanup dead code, reduce duplication, improve validation.

**Architecture:** Simplify /start to 2 modes (0 args, 1 arg), extract common helpers, add proper validation and error handling.

**Tech Stack:** Python, aiogram, asyncio

---

## Task 1: Fix critical _stop_tasks bug

**Files:**
- Modify: `src/telegram_bridge/bot.py:578-604`

**Problem:** Line 590 calls `project_manager._stop_tasks(project)` which doesn't exist. Crashes `/restart_session`.

**Step 1: Replace broken call with inline task cancellation**

In `on_restart_confirm` function, replace line 590:

```python
# OLD (line 590):
await project_manager._stop_tasks(project)

# NEW (replace with):
import asyncio
# Stop poller task
if project.poller_task and not project.poller_task.done():
    project.poller_task.cancel()
    try:
        await project.poller_task
    except asyncio.CancelledError:
        pass
    project.poller_task = None

# Stop watcher task
if project.watcher_task and not project.watcher_task.done():
    project.watcher_task.cancel()
    try:
        await project.watcher_task
    except asyncio.CancelledError:
        pass
    project.watcher_task = None
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "fix(telegram-bridge): fix _stop_tasks crash in restart_session

The method was removed but still called. Inline the task cancellation logic.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Remove backwards compatibility

**Files:**
- Modify: `src/telegram_bridge/bot.py:213-306`

**Step 1: Delete _start_with_explicit_args function**

Remove lines 213-264 entirely (the whole function).

**Step 2: Simplify cmd_start**

Replace the current `cmd_start` (lines 266-306) with:

```python
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Start command - auto-detect project or show status.

    Usage:
        /start              - auto-detect from chat or ask for project name
        /start <project>    - start with specific project
    """
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    args = message.text.split()[1:]  # Skip /start

    # Case 1: Project name provided
    if args:
        project_name = args[0]
        project = project_manager.get_or_create(project_name)
        project.chat_id = chat_id
        await _start_project_flow(message, project)
        return

    # Case 2: No args - auto-detect from chat
    project_name, project = get_project_for_chat(chat_id)

    if project and is_claude_running(project):
        await show_status(message, project)
        return

    if project:
        await _start_project_flow(message, project)
        return

    # Unknown chat - ask for project name
    _start_state[chat_id] = {"state": "awaiting_project_name"}
    await message.answer(
        "Отправь имя проекта (например: `my-project`):",
        parse_mode="Markdown",
    )
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "refactor(telegram-bridge): remove /start backwards compatibility

BREAKING: /start <project> <cwd> no longer supported.
Use /start or /start <project> instead.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Remove dead code

**Files:**
- Modify: `src/telegram_bridge/start_flow.py:49-55`

**Step 1: Delete unused ask_project_name_keyboard**

Remove lines 49-55 from `start_flow.py`:

```python
# DELETE THIS:
def ask_project_name_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown when project name cannot be determined."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отмена", callback_data="start:cancel"),
        ]
    ])
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/start_flow.py
git commit -m "refactor(telegram-bridge): remove unused ask_project_name_keyboard

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add asyncio import at top level

**Files:**
- Modify: `src/telegram_bridge/bot.py:1-10`

**Step 1: Add asyncio to imports**

Add after line 1:

```python
import asyncio
import re
```

**Step 2: Remove inline asyncio imports**

Search and remove these lines throughout the file:
- `import asyncio` (in _connect_or_launch, _start_with_explicit_args, launch_claude_new, on_restart_confirm)

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "refactor(telegram-bridge): move asyncio import to top level

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add InlineKeyboard imports at top level

**Files:**
- Modify: `src/telegram_bridge/bot.py:5`

**Step 1: Update aiogram.types import**

Change line 5 from:
```python
from aiogram.types import Message, CallbackQuery
```

To:
```python
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
```

**Step 2: Remove inline import in _connect_or_launch**

Remove this line from `_connect_or_launch`:
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "refactor(telegram-bridge): move InlineKeyboard imports to top

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Extract task starter helper

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add helper function after show_status**

Add after `show_status` function (around line 108):

```python
def _make_task_starters(bot):
    """Create task starter functions for poller and watcher.

    Returns:
        (start_poller, start_watcher) - async functions to start tasks
    """
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    return start_poller, start_watcher
```

**Step 2: Replace all duplications**

Find all places with this pattern:
```python
bot = message.bot  # or callback.bot
async def start_poller(p: ProjectState) -> asyncio.Task:
    from .permission_poller import create_poller_task
    return await create_poller_task(bot, p)

async def start_watcher(p: ProjectState) -> asyncio.Task:
    from .watcher import create_watcher_task
    return await create_watcher_task(bot, p)
```

Replace with:
```python
start_poller, start_watcher = _make_task_starters(message.bot)  # or callback.bot
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "refactor(telegram-bridge): extract _make_task_starters helper

Reduces code duplication from 9 places to 1.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Improve project name validation

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add validation function after is_admin**

Add around line 47:

```python
def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names contain only: letters, digits, dash, underscore.
    """
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
```

**Step 2: Update awaiting_project_name handler**

Find the handler in `on_message` and update validation:

```python
if state["state"] == "awaiting_project_name":
    project_name = message.text.strip()
    if not project_name or not is_valid_project_name(project_name):
        await message.answer(
            "Имя проекта может содержать только буквы, цифры, `-` и `_`.",
            parse_mode="Markdown",
        )
        return
    # ... rest unchanged
```

**Step 3: Also validate in cmd_start**

In `cmd_start`, when args provided, validate:

```python
if args:
    project_name = args[0]
    if not is_valid_project_name(project_name):
        await message.answer(
            "Имя проекта может содержать только буквы, цифры, `-` и `_`.",
            parse_mode="Markdown",
        )
        return
    # ... rest unchanged
```

**Step 4: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): improve project name validation

Only allow alphanumeric, dash, underscore. Prevents directory traversal.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Fix is_claude_running to check watcher

**Files:**
- Modify: `src/telegram_bridge/bot.py:69-87`

**Step 1: Update is_claude_running**

Replace the function:

```python
def is_claude_running(project: ProjectState) -> bool:
    """Check if Claude is fully running for project.

    Returns True if:
    - tmux session exists
    - poller_task is running
    - watcher_task is running (session discovered)
    """
    if not project or not project.tmux_session:
        return False

    if not is_tmux_session_exists(project.tmux_session):
        return False

    if not project.poller_task or project.poller_task.done():
        return False

    if not project.watcher_task or project.watcher_task.done():
        return False

    return True
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "fix(telegram-bridge): is_claude_running checks watcher_task too

Previously only checked poller, now requires both tasks running.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add error handling in launch_claude_new

**Files:**
- Modify: `src/telegram_bridge/bot.py` (launch_claude_new function)

**Step 1: Check create_tmux_with_claude result**

Update the function to check results:

```python
async def launch_claude_new(message: Message, project: ProjectState, start_poller, start_watcher):
    """Launch Claude in tmux session using new ProjectState."""
    import subprocess

    convention = f"claude-{project.project_name}"

    # Case 1: Our tmux exists - reuse
    if project.tmux_session == convention and is_tmux_session_exists(convention):
        subprocess.run(["tmux", "send-keys", "-t", convention, "claude", "Enter"], capture_output=True)
    # Case 2: Foreign tmux - create new alongside
    elif project.tmux_session and project.tmux_session != convention and is_tmux_session_exists(project.tmux_session):
        result = create_tmux_with_claude(convention, project.cwd)
        if not result.success:
            await message.answer(f"Ошибка запуска: {result.error}")
            return
        project.tmux_session = convention
    # Case 3: No tmux - create
    else:
        result = create_tmux_with_claude(convention, project.cwd)
        if not result.success:
            await message.answer(f"Ошибка запуска: {result.error}")
            return
        project.tmux_session = convention

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`\n\n"
        f"⏳ Ожидаю регистрацию...",
        parse_mode="Markdown",
    )
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "fix(telegram-bridge): handle errors in launch_claude_new

Check create_tmux_with_claude result and report errors to user.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update usage section**

Find the "Register project" section and update:

```markdown
### Register project

```bash
# In Telegram:
/start              # Auto-detect or ask for project name
/start myproject    # Start with specific project
```
```

**Step 2: Remove any references to old /start format**

Search for `/start <project_name> <cwd>` and remove.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(telegram-bridge): update CLAUDE.md for new /start format

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Run tests and verify

**Files:**
- None (verification only)

**Step 1: Run all tests**

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass

**Step 2: Verify bot imports**

```bash
python -c "from telegram_bridge.bot import router; print('OK')"
```

Expected: "OK"

**Step 3: Check syntax**

```bash
python -m py_compile src/telegram_bridge/bot.py
```

Expected: No output (success)

---

## Task 12: Add delay between text and Enter in tmux.send

**Files:**
- Modify: `src/telegram_bridge/tmux.py:1-16`

**Problem:** Sometimes text from Telegram is sent to tmux but Enter doesn't register. Race condition between two `subprocess.run` calls.

**Step 1: Add time import and delay**

```python
import subprocess
import shlex
import time  # ADD THIS
from dataclasses import dataclass

@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text to tmux session and press Enter."""
        session = shlex.quote(self.name)
        escaped = text.replace("'", "'\\''")
        # Send text with -l (literal) flag, then Enter separately
        subprocess.run(f"tmux send-keys -t {session} -l -- '{escaped}'", shell=True, check=True)
        time.sleep(0.05)  # 50ms delay to ensure text is processed
        subprocess.run(f"tmux send-keys -t {session} Enter", shell=True, check=True)
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/tmux.py
git commit -m "fix(telegram-bridge): add delay between text and Enter in tmux.send

Fixes race condition where Enter was sent before text was fully processed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Type |
|------|-------------|------|
| 1 | Fix _stop_tasks crash | Critical bug |
| 2 | Remove backwards compat | Breaking change |
| 3 | Remove dead code | Cleanup |
| 4 | Move asyncio import | Cleanup |
| 5 | Move InlineKeyboard import | Cleanup |
| 6 | Extract task starter | DRY |
| 7 | Improve validation | Security |
| 8 | Fix is_claude_running | Bug fix |
| 9 | Handle launch errors | Error handling |
| 10 | Update CLAUDE.md | Docs |
| 11 | Verify | Testing |
| 12 | Add tmux.send delay | Bug fix |
