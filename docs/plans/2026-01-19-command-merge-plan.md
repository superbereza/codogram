# Command Merge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge /thread and /branch into unified /new_chat command with simplified menu.

**Architecture:** New `handlers/new_chat.py` contains all logic. Old handlers become pure aliases. Menu order and /help completely rewritten.

**Tech Stack:** aiogram, Python 3.11+

---

## Task 1: Add new strings for /new_chat flow

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add new chat creation strings**

Add after line ~456 (after BRANCH_CREATED):

```python
# --- New Chat Flow ---

NEW_CHAT_CONTEXT = """{status} Creating chat from:
📁 `{directory}`
🌿 `{branch}`

To branch from main, run /new_chat in General"""

NEW_CHAT_CONTEXT_MAIN = """{status} Creating chat from:
📁 `{directory}`
🌿 `{branch}`"""

NEW_CHAT_CHOOSE = "Where to create?"
NEW_CHAT_CREATING = f"{STATUS_PENDING} Creating chat `{{name}}`..."
NEW_CHAT_CREATED = f"{STATUS_OK} Chat `{{name}}` created"

BTN_CREATE_HERE = "Create here"
BTN_CREATE_ISOLATED = "Create isolated"
```

**Step 2: Add new /help text**

Add after the new chat strings:

```python
# --- Help ---

HELP_TEXT = """Troubleshoot

If bot isn't responding, try /reset\\_chat — it's safe for context\\.

To wipe project and start fresh: /hard\\_reset\\. 🚨 Dangerous zone\\!

─────────────────

Chats
/new\\_chat — create new chat: topic \\& Claude session
/finish\\_chat — archive chat and stop Claude
/start — connect or resume
/reset\\_chat — restart Claude process

Context
/clear\\_context — clear current Claude context

Operations
/esc — send Esc, stop current operation
/shift\\_tab — cycle Claude approval mode
/auto\\_accept — accept every Claude permission 🚧

Settings
/settings — show settings
/get\\_debug\\_ids — debug info"""
```

**Step 3: Run linter**

```bash
cd /home/superbereza/dev/codogram/.worktrees/thread-n-branch-merge && python -m py_compile src/codogram/strings.py
```

Expected: No errors

**Step 4: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat: add strings for /new_chat flow and new /help"
```

---

## Task 2: Update domain/create_flow.py for new CreateType

**Files:**
- Modify: `src/codogram/domain/create_flow.py`

**Step 1: Read current file**

```bash
cat src/codogram/domain/create_flow.py
```

**Step 2: Add CHAT type or keep existing**

The `CreateType` enum likely has THREAD and BRANCH. We can reuse them for now, or add CHAT. Check file first, then decide minimal change.

**Step 3: Commit if changed**

```bash
git add src/codogram/domain/create_flow.py
git commit -m "refactor: update CreateType for new_chat flow"
```

---

## Task 3: Create handlers/new_chat.py

**Files:**
- Create: `src/codogram/handlers/new_chat.py`

**Step 1: Create new handler file**

```python
"""Unified /new_chat command for creating topics with Claude sessions."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import (
    require_forum_group,
    require_claude_ready,
    set_flow_state,
    get_flow_state,
    clear_flow_state,
)
from ..domain.create_flow import CreateType
from ..domain.worktree_state import WorktreeState, get_worktree_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import create_flow_service
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..git_utils import (
    is_git_repo,
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
    get_current_branch,
)

router = Router(name="new_chat")


# ===== Main command =====

@router.message(Command("new_chat", "nc", ignore_case=True))
async def cmd_new_chat(message: Message, telegram_queue: TelegramQueue):
    """Create a new chat (topic + Claude session)."""
    if not await require_forum_group(message, telegram_queue):
        return
    if not await require_claude_ready(message, telegram_queue):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    # Determine current context (directory and branch)
    current_thread = project.threads.get(thread_id)

    if current_thread and current_thread.worktree_path:
        # From worktree topic
        state = get_worktree_state(current_thread, Path(project.cwd))
        if state == WorktreeState.OK:
            directory = current_thread.worktree_path
            branch = current_thread.name
        else:
            # Stale worktree - use main
            directory = project.cwd
            branch = get_default_branch(Path(project.cwd))
    else:
        # From main/General
        directory = project.cwd
        branch = get_default_branch(Path(project.cwd))

    # Check if git repo exists (for isolated option)
    has_git = is_git_repo(Path(project.cwd))

    # Build context message and keyboard
    if has_git:
        # Show both options
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=strings.BTN_CREATE_HERE, callback_data="nc_here"),
                InlineKeyboardButton(text=strings.BTN_CREATE_ISOLATED, callback_data="nc_isolated"),
            ],
            [InlineKeyboardButton(text=strings.BTN_CANCEL, callback_data="nc_cancel")],
        ])

        # Different message for main vs worktree
        if branch == get_default_branch(Path(project.cwd)):
            context_text = strings.NEW_CHAT_CONTEXT_MAIN.format(
                status=strings.STATUS_QUESTION,
                directory=directory,
                branch=branch,
            )
        else:
            context_text = strings.NEW_CHAT_CONTEXT.format(
                status=strings.STATUS_QUESTION,
                directory=directory,
                branch=branch,
            )
    else:
        # No git - skip to name prompt (only "create here" option)
        prompt_ids = await telegram_queue.reply(
            message,
            "Chat name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.THREAD),
        )
        set_flow_state(chat_id, thread_id, {
            "type": "awaiting_create_name",
            "create_type": "thread",
            "prompt_message_id": prompt_ids[0] if prompt_ids else None,
        })
        return

    # Save context for callbacks
    set_flow_state(chat_id, thread_id, {
        "type": "new_chat_context",
        "directory": directory,
        "branch": branch,
    })

    await telegram_queue.reply(message, f"{context_text}\n\n{strings.NEW_CHAT_CHOOSE}", reply_markup=keyboard)


# ===== Step 1 callbacks: Create here vs Isolated =====

@router.callback_query(F.data == "nc_here")
async def on_nc_here(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create chat in current directory (same as old /thread)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    clear_flow_state(chat_id, thread_id)

    # Show name prompt
    await telegram_queue.edit(
        callback.message,
        "Chat name?\n\nSend name or pick random",
        reply_markup=build_name_prompt_keyboard(CreateType.THREAD),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "awaiting_create_name",
        "create_type": "thread",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_isolated")
async def on_nc_isolated(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create isolated branch (same as old /branch)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    clear_flow_state(chat_id, thread_id)

    # Show name prompt for branch
    await telegram_queue.edit(
        callback.message,
        "Chat name?\n\nSend name or pick random",
        reply_markup=build_name_prompt_keyboard(CreateType.BRANCH),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "awaiting_create_name",
        "create_type": "branch",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_cancel")
async def on_nc_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Cancel new chat creation."""
    clear_flow_state(callback.message.chat.id, callback.message.message_thread_id)
    await callback.message.delete()
    await callback.answer()
```

**Step 2: Run linter**

```bash
python -m py_compile src/codogram/handlers/new_chat.py
```

Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/handlers/new_chat.py
git commit -m "feat: add handlers/new_chat.py with unified chat creation"
```

---

## Task 4: Update handlers/threads.py to pure alias

**Files:**
- Modify: `src/codogram/handlers/threads.py`

**Step 1: Replace entire file with alias**

```python
"""Thread aliases - redirect to /new_chat."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..telegram_queue import TelegramQueue
from .new_chat import cmd_new_chat

router = Router(name="threads")


@router.message(Command("thread", "thread_create", ignore_case=True))
async def cmd_thread(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("thread_delete", ignore_case=True))
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, "`[i]` Use /finish_chat to archive topics")
```

**Step 2: Run linter**

```bash
python -m py_compile src/codogram/handlers/threads.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/threads.py
git commit -m "refactor: threads.py now pure alias to new_chat"
```

---

## Task 5: Update handlers/branches.py to pure alias

**Files:**
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Replace with alias + keep callback handlers**

The callbacks (bc_base, bc_create, bc_commit) are still needed. Keep them, but make the command an alias.

```python
"""Branch aliases and callbacks - command redirects to /new_chat."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import clear_flow_state
from ..services.branch import do_branch_create
from ..git_utils import has_uncommitted_changes, get_default_branch
from ..tmux import TmuxSession
from .new_chat import cmd_new_chat

router = Router(name="branches")


@router.message(Command("branch", "branch_create", ignore_case=True))
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("branch_finish", ignore_case=True))
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, strings.BRANCH_FINISH_USE_FINISH)


# ===== Callbacks (kept for branch creation flow) =====

@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle base branch selection for branch_create."""
    _, branch_name, base_branch = callback.data.split(":")
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    # Check uncommitted in selected base
    base_path = project.cwd
    if base_branch != get_default_branch(Path(project.cwd)):
        for t in project.threads.values():
            if t.name == base_branch and t.worktree_path:
                base_path = t.worktree_path
                break

    if has_uncommitted_changes(Path(base_path)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create from last commit", callback_data=f"bc_create:{branch_name}:{base_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="cancel")]
        ])
        await telegram_queue.edit(
            callback.message,
            strings.BRANCH_UNCOMMITTED_IN_BASE.format(base_branch=base_branch),
            reply_markup=keyboard,
        )
        return

    await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
    await callback.answer()

    await do_branch_create(callback.bot, chat_id, project, branch_name, base_branch)
    await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)


@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create branch from last commit."""
    _, branch_name, base_branch = callback.data.split(":")
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
    await callback.answer()

    await do_branch_create(callback.bot, chat_id, project, branch_name, base_branch)
    await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)


@router.callback_query(F.data.startswith("bc_commit:"))
async def on_branch_commit_request(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Send commit request to Claude."""
    _, branch_name = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    thread = project.threads.get(callback.message.message_thread_id)

    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        strings.BRANCH_COMMIT_SENT.format(branch_name=branch_name),
    )
    await callback.answer()


@router.callback_query(F.data == "branch_create_redirect")
async def on_branch_redirect(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle redirect to /branch_create (now /new_chat)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    await telegram_queue.edit(
        callback.message,
        "Use `/new_chat` and select 'Create isolated' for isolated branches.",
    )
    await callback.answer()
```

**Step 2: Run linter**

```bash
python -m py_compile src/codogram/handlers/branches.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/branches.py
git commit -m "refactor: branches.py command as alias, keep callbacks"
```

---

## Task 6: Update handlers/finish.py for /finish_chat aliases

**Files:**
- Modify: `src/codogram/handlers/finish.py`

**Step 1: Update Command decorator to include aliases**

Change line ~22:
```python
@router.message(Command("finish", "finish_chat", "archive", "archive_chat", "fc", ignore_case=True))
```

**Step 2: Run linter**

```bash
python -m py_compile src/codogram/handlers/finish.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/finish.py
git commit -m "feat: add finish_chat, archive, fc aliases to /finish"
```

---

## Task 7: Update handlers/sessions.py for /clear_context

**Files:**
- Modify: `src/codogram/handlers/sessions.py`

**Step 1: Add clear_context as main command with aliases**

Change lines ~87-88 and ~97-98:
```python
@router.message(Command("clear_context", "clear", "new", ignore_case=True))
async def cmd_clear_context(message: Message, telegram_queue: TelegramQueue):
    """Clear Claude context and start fresh."""
```

And update the /new handler to use /clear logic:
```python
# Remove separate cmd_new - now alias handled by cmd_clear_context
```

**Step 2: Add reset_chat alias**

Find the restart handler (if exists) or add new:
```python
@router.message(Command("reset_chat", "restart", ignore_case=True))
async def cmd_reset_chat(message: Message, telegram_queue: TelegramQueue):
    """Restart Claude process."""
    # ... existing restart logic
```

**Step 3: Run linter**

```bash
python -m py_compile src/codogram/handlers/sessions.py
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/sessions.py
git commit -m "feat: add clear_context and reset_chat as main commands"
```

---

## Task 8: Update services/menu.py

**Files:**
- Modify: `src/codogram/services/menu.py`

**Step 1: Replace _ALL_COMMANDS with new order**

```python
_ALL_COMMANDS = [
    ("esc", "Send Esc, stop current operation", True),
    ("shift_tab", "Cycle Claude approval mode", True),
    ("auto_accept", "Accept every Claude permission 🚧", True),
    ("new_chat", "Create new chat: topic & Claude session", True),
    ("finish_chat", "Archive chat and stop Claude", False),  # forum only
    ("start", "Connect or resume", True),
    ("settings", "Show settings", True),
    ("clear_context", "Clear current Claude context", True),
    ("reset_chat", "Restart Claude process", True),
    ("get_debug_ids", "Debug info", True),
    ("help", "Show help", True),
    ("hard_reset", "Full project reset", True),
]
```

**Step 2: Run linter**

```bash
python -m py_compile src/codogram/services/menu.py
```

**Step 3: Commit**

```bash
git add src/codogram/services/menu.py
git commit -m "feat: update menu with new command names and order"
```

---

## Task 9: Update handlers/settings.py /help

**Files:**
- Modify: `src/codogram/handlers/settings.py`

**Step 1: Update cmd_help to use new HELP_TEXT with Close button**

```python
@router.message(Command("help", ignore_case=True))
async def cmd_help(message: Message, telegram_queue: TelegramQueue):
    """Show help."""
    from ..keyboards import close_keyboard

    await telegram_queue.reply(message, strings.HELP_TEXT, reply_markup=close_keyboard())
```

**Step 2: Add close_keyboard if not exists**

Check if `keyboards/__init__.py` has `close_keyboard`, if not add to `keyboards/common.py`:

```python
def close_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with just Close button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Close", callback_data="help_close")]
    ])
```

**Step 3: Add callback handler for help close**

In settings.py:
```python
@router.callback_query(F.data == "help_close")
async def on_help_close(callback: CallbackQuery):
    """Close help message."""
    await callback.message.delete()
    await callback.answer()
```

**Step 4: Run linter**

```bash
python -m py_compile src/codogram/handlers/settings.py
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/settings.py src/codogram/keyboards/
git commit -m "feat: update /help with new text and Close button"
```

---

## Task 10: Register new_chat router in main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Find router registration section**

Look for where routers are registered (dp.include_router).

**Step 2: Add new_chat router**

```python
from .handlers import new_chat
# ...
dp.include_router(new_chat.router)
```

**Step 3: Run linter**

```bash
python -m py_compile src/codogram/main.py
```

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat: register new_chat router"
```

---

## Task 11: Add missing BTN_CANCEL string

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Check and add BTN_CANCEL if missing**

```python
BTN_CANCEL = "[<<] Cancel"
```

**Step 2: Commit**

```bash
git add src/codogram/strings.py
git commit -m "fix: add BTN_CANCEL string"
```

---

## Task 12: Add hard_reset alias

**Files:**
- Find and modify reset handler

**Step 1: Find reset_all handler**

```bash
grep -r "reset_all" src/codogram/handlers/
```

**Step 2: Add hard_reset alias**

Update Command decorator to include "hard_reset".

**Step 3: Commit**

```bash
git add src/codogram/handlers/
git commit -m "feat: add hard_reset alias to reset_all"
```

---

## Task 13: Manual E2E test

**Steps:**
1. Start bot from worktree: `./kill-instance-and-start-from-worktree.sh`
2. Test `/new_chat` shows context and options
3. Test `/thread` redirects to `/new_chat`
4. Test `/branch` redirects to `/new_chat`
5. Test `/help` shows new text with Close button
6. Test `/finish_chat` works
7. Test `/clear_context` works
8. Check menu shows new commands

---

## Task 14: Final commit

```bash
git add -A
git commit -m "feat: complete command merge and menu simplification"
```
