# Phase 9: Extract Remaining Handlers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract all remaining handlers from bot.py into dedicated handler modules (threads, branches, sessions, settings)

**Architecture:** Each handler module follows the pattern established in handlers/start.py - thin handlers that delegate to services where applicable. This is primarily an extraction task moving existing working code from bot.py to new files.

**Tech Stack:** Python, aiogram 3.x, pytest

---

## Background

### Current State
- `handlers/start.py` contains /start and /restart handlers (Phase 8 complete)
- `bot.py` still contains ~800+ lines of handlers for threads, branches, sessions, settings
- All handlers are working and tested via E2E

### Target State
- `handlers/threads.py` - /thread_create, /thread_delete
- `handlers/branches.py` - /branch_create, /branch_finish
- `handlers/sessions.py` - /new, /clear, /esc, /resume
- `handlers/settings.py` - /settings, /auto_accept, /help, /get_debug_ids

### Key Principle
This is **extraction** not rewrite. Move existing working code, preserve behavior, verify tests pass.

---

## Phase 9a: handlers/threads.py

### Task 1: Create handlers/threads.py with /thread_delete

**Files:**
- Create: `src/codogram/handlers/threads.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create the file with imports and /thread_delete**

Create `src/codogram/handlers/threads.py`:

```python
"""Thread management: create and delete forum topics."""
import subprocess

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager

router = Router(name="threads")


# ===== /thread_delete =====

@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message):
    """Close current thread and its Claude session."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    if thread_id is None:
        await message.answer("This command can only be used in a topic")
        return

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("This topic is not linked to a Claude session")
        return

    # Confirmation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, delete", callback_data=f"thread_delete:{thread_id}"),
            InlineKeyboardButton(text="Cancel", callback_data="thread_delete:cancel"),
        ]
    ])
    await message.answer(
        f"Delete thread '{thread.name}'?\n"
        "Topic and tmux session will be deleted.",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("thread_delete:"))
async def on_thread_delete_callback(callback: CallbackQuery):
    """Handle thread close confirmation."""
    data = callback.data.split(":")[1]
    if data == "cancel":
        await callback.message.edit_text("Cancelled")
        await callback.answer()
        return

    thread_id = int(data)
    chat_id = callback.message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Stop tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Delete topic
    try:
        await callback.bot.delete_forum_topic(chat_id, thread_id)
    except Exception as e:
        await callback.message.edit_text(f"Error deleting topic: {e}")
        await callback.answer()
        return

    # Remove from project
    del project.threads[thread_id]
    project_manager._save()

    await callback.answer("Thread closed")
```

**Step 2: Update handlers/__init__.py**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads


def register_handlers(dp: Dispatcher):
    """Register all handler routers."""
    dp.include_router(permissions.router)
    dp.include_router(start.router)
    dp.include_router(threads.router)
```

**Step 3: Verify import works**

```bash
PYTHONPATH=src python -c "from codogram.handlers.threads import router; print('Router:', router.name)"
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add threads.py with /thread_delete"
```

---

### Task 2: Add /thread_create to handlers/threads.py

**Files:**
- Modify: `src/codogram/handlers/threads.py`

**Step 1: Add imports and helper**

Add at top of `src/codogram/handlers/threads.py`:

```python
from ..bot import require_forum_group, _start_state
from ..magic_names import get_random_magic_name
from ..services.launch import create_thread_with_session
```

**Step 2: Add /thread_create handler**

Add after /thread_delete handlers:

```python
# ===== /thread_create =====

@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message):
    """Create a new thread (topic) with its own Claude session."""
    if not await require_forum_group(message):
        return

    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Project not found. Use /start first")
        return

    # Parse optional name from command
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
    else:
        existing_names = {t.name for t in project.threads.values()}
        name = get_random_magic_name(existing_names)

    # Check if any non-worktree threads exist (excluding main)
    non_worktree_threads = [
        t for t in project.threads.values()
        if t.thread_id is not None and not t.worktree_path
    ]

    if non_worktree_threads:
        # Store pending thread name for confirmation
        _start_state[chat_id] = {
            "state": "thread_create_pending",
            "name": name,
        }
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create in main repo", callback_data="thread_create_confirm")],
            [InlineKeyboardButton(text="Use /branch_create instead", callback_data="branch_create_redirect")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
        ])
        await message.answer(
            "Non-worktree threads exist. For isolated work, consider /branch_create.\n"
            "Create thread in main repo anyway?",
            reply_markup=keyboard
        )
        return

    # Create directly
    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await message.answer("Error creating topic")


@router.callback_query(F.data == "thread_create_confirm")
async def on_thread_create_confirm(callback: CallbackQuery):
    """Handle thread_create confirmation (create in main anyway)."""
    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)

    if not state or state.get("state") != "thread_create_pending":
        await callback.answer("Session expired")
        return

    name = state.get("name")
    _start_state.pop(chat_id, None)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()

    thread = await create_thread_with_session(
        bot=callback.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await callback.bot.send_message(chat_id, "Error creating topic")

    await callback.answer()
```

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.threads import cmd_thread_create; print('OK')"
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py
git commit -m "feat(handlers): add /thread_create to threads.py"
```

---

## Phase 9b: handlers/branches.py

### Task 3: Create handlers/branches.py with /branch_create

**Files:**
- Create: `src/codogram/handlers/branches.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create the file**

Create `src/codogram/handlers/branches.py`:

```python
"""Branch management: git worktrees + threads."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..bot import require_forum_group, _start_state, _do_branch_create
from ..magic_names import get_random_magic_name
from ..git_utils import (
    is_git_repo,
    sanitize_branch_name,
    max_branch_name_length,
    has_uncommitted_changes,
    get_default_branch,
)
from ..tmux import TmuxSession

router = Router(name="branches")


# ===== /branch_create =====

@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("`[!]` Project not registered. Use /start first.", parse_mode="Markdown")
        return

    # Check git repo
    if not is_git_repo(Path(project.cwd)):
        await message.answer("`[x]` Git repository required for /branch_create", parse_mode="Markdown")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # Generate magic name if not provided
    if not branch_name:
        existing_names = {t.name for t in project.threads.values()}
        branch_name = get_random_magic_name(existing_names)

    # Sanitize branch name
    branch_name = sanitize_branch_name(branch_name)

    # Check length
    max_len = max_branch_name_length(project.project_name)
    if len(branch_name) > max_len:
        await message.answer(f"`[x]` Name too long (max {max_len} chars for this project)", parse_mode="Markdown")
        return

    # Get default branch
    default_branch = get_default_branch(Path(project.cwd))

    # Check if creating from worktree topic or main
    current_thread = project.threads.get(message.message_thread_id)
    if current_thread and current_thread.worktree_path:
        # From worktree topic - show base branch selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"From {default_branch}", callback_data=f"bc_base:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text=f"From {current_thread.name}", callback_data=f"bc_base:{branch_name}:{current_thread.name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await message.answer("Create branch from:", reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await message.answer("`[!]` Uncommitted changes detected", reply_markup=keyboard, parse_mode="Markdown")
        return

    # No uncommitted changes - create directly
    await _do_branch_create(message, project, branch_name, default_branch)


@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery):
    """Handle base branch selection for branch_create."""
    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    # Check uncommitted in selected base
    base_path = project.cwd
    if base_branch != get_default_branch(Path(project.cwd)):
        # Find worktree path for this branch
        for t in project.threads.values():
            if t.name == base_branch and t.worktree_path:
                base_path = t.worktree_path
                break

    if has_uncommitted_changes(Path(base_path)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create from last commit", callback_data=f"bc_create:{branch_name}:{base_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await callback.message.edit_text(f"`[!]` Uncommitted changes in {base_branch}", reply_markup=keyboard, parse_mode="Markdown")
        return

    await callback.message.delete()
    await _do_branch_create(callback.message, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery):
    """Create branch from last commit."""
    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()
    await _do_branch_create(callback.message, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_commit:"))
async def on_branch_commit_request(callback: CallbackQuery):
    """Send commit request to Claude."""
    _, branch_name = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(callback.message.message_thread_id)

    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await callback.message.edit_text(
        "`[~]` Sent: \"Commit current changes in logical chunks with descriptive messages.\"\n\n"
        f"Run `/branch_create {branch_name}` again after commit.",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "branch_create_redirect")
async def on_branch_redirect(callback: CallbackQuery):
    """Handle redirect to /branch_create."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)

    await callback.message.edit_text(
        "Use `/branch_create` or `/branch_create <name>` to create isolated worktree branch.",
        parse_mode="Markdown"
    )
    await callback.answer()
```

**Step 2: Update handlers/__init__.py**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches


def register_handlers(dp: Dispatcher):
    """Register all handler routers."""
    dp.include_router(permissions.router)
    dp.include_router(start.router)
    dp.include_router(threads.router)
    dp.include_router(branches.router)
```

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.branches import router; print('Router:', router.name)"
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/branches.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add branches.py with /branch_create"
```

---

### Task 4: Add /branch_finish to handlers/branches.py

**Files:**
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Add imports**

Add to imports in `src/codogram/handlers/branches.py`:

```python
from ..bot import _do_branch_cleanup
from ..git_utils import branch_exists
from ..worktree import merge_branch, push_branch
```

**Step 2: Add /branch_finish handlers**

Add at end of file:

```python
# ===== /branch_finish =====

@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message):
    """Finish branch: merge and cleanup worktree."""
    if not await require_forum_group(message):
        return

    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(message.chat.id)

    if not project:
        await message.answer("`[!]` Project not registered.", parse_mode="Markdown")
        return

    thread = project.get_thread(thread_id)
    if not thread or not thread.worktree_path:
        await message.answer("`[!]` /branch_finish only works in worktree topics. Use /thread_delete for this topic.", parse_mode="Markdown")
        return

    # Check uncommitted changes
    worktree_path = Path(thread.worktree_path)

    if worktree_path.exists() and has_uncommitted_changes(worktree_path):
        await message.answer("`[!]` Uncommitted changes. Commit or stash first.", parse_mode="Markdown")
        return

    # Build keyboard
    default_branch = get_default_branch(Path(project.cwd))
    buttons = [[InlineKeyboardButton(text=f"Merge -> {default_branch}", callback_data=f"bf_merge:{thread_id}:{default_branch}")]]

    # Add base_branch option if it exists and is different
    if thread.base_branch and thread.base_branch != default_branch:
        if branch_exists(Path(project.cwd), thread.base_branch):
            buttons.append([InlineKeyboardButton(text=f"Merge -> {thread.base_branch}", callback_data=f"bf_merge:{thread_id}:{thread.base_branch}")])

    buttons.append([InlineKeyboardButton(text="[!!] Delete without merge", callback_data=f"bf_delete:{thread_id}")])
    buttons.append([InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(f"Finish `{thread.name}` branch:", reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("bf_merge:"))
async def on_branch_merge_selected(callback: CallbackQuery):
    """Show merge confirmation."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Check target has no uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        await callback.message.edit_text("`[!]` Uncommitted changes in target directory. Commit or stash first.", parse_mode="Markdown")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, finish", callback_data=f"bf_do_merge:{thread_id}:{target_branch}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"Merge `{thread.name}` -> `{target_branch}` will:\n"
        "- Merge branch and push\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        "- Archive topic\n\n"
        "Continue?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_merge:"))
async def on_branch_do_merge(callback: CallbackQuery):
    """Execute merge and cleanup."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Merging {thread.name} -> {target_branch}...", parse_mode="Markdown")
    await callback.answer()

    main_repo = Path(project.cwd)
    branch_name = thread.name

    # Merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        if "conflicts" in result.error.lower():
            await callback.message.edit_text("`[!]` Merge conflicts. Resolve and run /branch_finish again.", parse_mode="Markdown")
        else:
            await callback.message.edit_text(f"`[x]` Merge failed: {result.error}", parse_mode="Markdown")
        return

    # Push (optional, don't fail on error)
    push_result = push_branch(main_repo, target_branch)
    push_warning = "" if push_result.success else "\n`[!]` Push failed. Run `git push` manually."

    # Cleanup
    await _do_branch_cleanup(callback.message, project, thread, force=False)

    await callback.message.edit_text(f"`[v]` Branch {branch_name} merged and cleaned up{push_warning}", parse_mode="Markdown")


@router.callback_query(F.data.startswith("bf_delete:"))
async def on_branch_delete_selected(callback: CallbackQuery):
    """Show delete confirmation."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, delete", callback_data=f"bf_do_delete:{thread_id}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"`[!!]` Delete `{thread.name}` WITHOUT merging?\n\n"
        "This will:\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        "- Delete local branch\n"
        "- Archive topic\n\n"
        "⚠️ Changes will be LOST!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_delete:"))
async def on_branch_do_delete(callback: CallbackQuery):
    """Execute delete without merge."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Deleting {thread.name}...", parse_mode="Markdown")
    await callback.answer()

    # Cleanup with force=True to delete branch
    await _do_branch_cleanup(callback.message, project, thread, force=True)

    await callback.message.edit_text(f"`[v]` Branch {thread.name} deleted", parse_mode="Markdown")
```

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.branches import cmd_branch_finish; print('OK')"
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/branches.py
git commit -m "feat(handlers): add /branch_finish to branches.py"
```

---

## Phase 9c: handlers/sessions.py

### Task 5: Create handlers/sessions.py

**Files:**
- Create: `src/codogram/handlers/sessions.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create the file**

Create `src/codogram/handlers/sessions.py`:

```python
"""Session management: /new, /clear, /esc, /resume."""
import time

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..project_launcher import is_tmux_session_exists
from ..tmux import TmuxSession
from ..logging_config import logger

router = Router(name="sessions")


async def _send_session_command(message: Message, command: str, status_text: str) -> bool:
    """Common logic for /new and /clear commands.

    Returns True if command was sent successfully, False otherwise.
    """
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Project not registered. Use /start")
        return False

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread not found. Use /start")
        return False

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux session not found. Start Claude in terminal.")
        return False

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()
    thread.last_sent_message = None
    project_manager._save()

    # Send command to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys(command)

    await message.answer(status_text)
    return True


@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    await _send_session_command(message, "/new", "`[~]` Creating new session...")


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    await _send_session_command(message, "/clear", "`[~]` Clearing session...")


@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape to current thread's tmux."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get correct thread (topic or main)
    thread = project.threads.get(thread_id)
    if not thread:
        return

    if not project.cwd:
        logger.error(f"esc: project {project.project_name} has no cwd")
        return

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_key("Escape")


@router.message(Command("resume"))
async def cmd_resume(message: Message):
    """Handle /resume command - not supported in multi-session mode."""
    thread_id = message.message_thread_id
    if thread_id is not None:
        # In a topic - resume not supported
        await message.answer(
            "`[!]` /resume not supported in multi-session mode.\n"
            "Use /thread_create for a new thread.",
            parse_mode="Markdown"
        )
    else:
        # In private/general - just inform
        await message.answer(
            "`[!]` /resume not supported.\n"
            "Use /start to connect to existing session.",
            parse_mode="Markdown"
        )
```

**Step 2: Update handlers/__init__.py**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches, sessions


def register_handlers(dp: Dispatcher):
    """Register all handler routers."""
    dp.include_router(permissions.router)
    dp.include_router(start.router)
    dp.include_router(threads.router)
    dp.include_router(branches.router)
    dp.include_router(sessions.router)
```

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.sessions import router; print('Router:', router.name)"
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/sessions.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add sessions.py with /new, /clear, /esc, /resume"
```

---

## Phase 9d: handlers/settings.py

### Task 6: Create handlers/settings.py

**Files:**
- Create: `src/codogram/handlers/settings.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create the file**

Create `src/codogram/handlers/settings.py`:

```python
"""Settings and info commands."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager

router = Router(name="settings")


@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message):
    """Show debug IDs - admin only (protected by middleware)."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await message.answer(
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}",
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show available commands."""
    text = """**Commands**

`/start` — Start Claude / show status
`/new` — Start new Claude session
`/restart` — Kill and restart Claude tmux

**Threads**
`/thread_create [name]` — Create new Claude thread
`/thread_delete` — Delete thread (in topic)

**Git worktrees**
`/branch_create [name]` — Create worktree + thread
`/branch_finish` — Merge and cleanup

**Settings**
`/settings` — Show current settings
`/auto_accept` — Toggle auto-accept
`/auto_accept reset all` — Reset all to off

**Other**
`/esc` — Send Escape to Claude
`/get_debug_ids` — Show debug IDs"""

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show current settings."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        auto_status = "⚡ ON" if thread.auto_accept else "OFF"
        text = (
            f"**Settings** (thread `{thread.name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )
    else:
        auto_status = "⚡ ON" if project.auto_accept else "OFF"
        text = (
            f"**Settings** (`{project.project_name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept or reset all."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await message.answer("Auto-accept reset to **OFF** for project and all threads.", parse_mode="Markdown")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "⚡ ON" if thread.auto_accept else "OFF"
        await message.answer(f"Auto-accept for `{thread.name}`: **{status}**", parse_mode="Markdown")
    else:
        project.auto_accept = not project.auto_accept
        status = "⚡ ON" if project.auto_accept else "OFF"
        await message.answer(f"Auto-accept: **{status}**", parse_mode="Markdown")
    project_manager._save()
```

**Step 2: Update handlers/__init__.py**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches, sessions, settings


def register_handlers(dp: Dispatcher):
    """Register all handler routers."""
    dp.include_router(permissions.router)
    dp.include_router(start.router)
    dp.include_router(threads.router)
    dp.include_router(branches.router)
    dp.include_router(sessions.router)
    dp.include_router(settings.router)
```

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.settings import router; print('Router:', router.name)"
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/settings.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add settings.py with /settings, /auto_accept, /help, /get_debug_ids"
```

---

## Task 7: Final verification

**Step 1: Run full test suite**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: All tests PASS

**Step 2: Verify all routers registered**

```bash
PYTHONPATH=src python -c "
from codogram.handlers import register_handlers
from aiogram import Dispatcher
dp = Dispatcher()
register_handlers(dp)
print('Routers:', [r.name for r in dp._sub_routers])
"
```

Expected: `['permissions', 'start', 'threads', 'branches', 'sessions', 'settings']`

**Step 3: Count lines extracted**

```bash
wc -l src/codogram/handlers/*.py
```

---

## Summary

**New files:**
- `src/codogram/handlers/threads.py` (~120 LOC) - /thread_create, /thread_delete
- `src/codogram/handlers/branches.py` (~300 LOC) - /branch_create, /branch_finish
- `src/codogram/handlers/sessions.py` (~80 LOC) - /new, /clear, /esc, /resume
- `src/codogram/handlers/settings.py` (~100 LOC) - /settings, /auto_accept, /help, /get_debug_ids

**Commands extracted:**
- Phase 9a: /thread_create, /thread_delete
- Phase 9b: /branch_create, /branch_finish
- Phase 9c: /new, /clear, /esc, /resume
- Phase 9d: /settings, /auto_accept, /help, /get_debug_ids

**Note:** This plan imports helper functions from bot.py (`require_forum_group`, `_start_state`, `_do_branch_create`, `_do_branch_cleanup`). These can be refactored into services in Phase 10-11.
