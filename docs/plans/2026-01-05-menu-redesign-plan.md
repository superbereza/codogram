# Menu Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize bot menu, add command aliases, create unified `/finish` command that keeps worktrees.

**Architecture:** Modify menu in main.py, add aliases as separate handlers, create new `/finish` handler that reuses branch merge logic but skips worktree deletion. Change `do_branch_cleanup` to preserve worktree and git branch.

**Tech Stack:** Python 3.11, aiogram 3.x, Telegram Bot API

---

## Task 1: Update Menu Structure in main.py

**Files:**
- Modify: `src/codogram/main.py:43-58`

**Step 1: Update command list**

Replace current menu commands with new structure:

```python
COMMANDS = [
    BotCommand(command="esc", description="Cancel current operation"),
    BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
    BotCommand(command="thread", description="New topic in project directory"),
    BotCommand(command="branch", description="New isolated feature branch + topic"),
    BotCommand(command="clear", description="Clear context, start fresh"),
    BotCommand(command="finish", description="Merge branch, archive topic"),
    BotCommand(command="start", description="Connect Claude or show status"),
    BotCommand(command="settings", description="View current settings"),
    BotCommand(command="restart", description="Force restart Claude"),
    BotCommand(command="my_chat_id", description="Show chat and thread IDs"),
    BotCommand(command="help", description="List all commands"),
]
```

**Step 2: Verify changes**

Run: `python -m py_compile src/codogram/main.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor(menu): reorganize command menu structure"
```

---

## Task 2: Add /thread and /branch Aliases

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Add /thread alias in threads.py**

After line 20 (router definition), add:

```python
@router.message(Command("thread"))
async def cmd_thread(message: Message, telegram_queue: TelegramQueue):
    """Alias for /thread_create."""
    await cmd_thread_create(message, telegram_queue)
```

**Step 2: Add /branch alias in branches.py**

After line 24 (router definition), add:

```python
@router.message(Command("branch"))
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /branch_create."""
    await cmd_branch_create(message, telegram_queue)
```

**Step 3: Verify changes**

Run: `python -m py_compile src/codogram/handlers/threads.py src/codogram/handlers/branches.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/handlers/threads.py src/codogram/handlers/branches.py
git commit -m "feat(commands): add /thread and /branch aliases"
```

---

## Task 3: Add Hidden Command Aliases

**Files:**
- Modify: `src/codogram/handlers/sessions.py`

**Step 1: Add /new alias for /clear**

The `/new` command already exists in sessions.py:55-58. Change it to be an alias for `/clear`:

```python
@router.message(Command("new"))
async def cmd_new(message: Message, telegram_queue: TelegramQueue):
    """Alias for /clear - clear context and start fresh."""
    await cmd_clear(message, telegram_queue)
```

**Step 2: Verify changes**

Run: `python -m py_compile src/codogram/handlers/sessions.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/handlers/sessions.py
git commit -m "refactor(commands): make /new alias for /clear"
```

---

## Task 4: Add Deprecated Command Handlers

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Add /thread_delete redirect in threads.py**

After the /thread alias, add:

```python
@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, "`[i]` Use /finish to archive topics")
```

**Step 2: Add /branch_finish redirect in branches.py**

After the /branch alias, add:

```python
@router.message(Command("branch_finish_deprecated"))
async def cmd_branch_finish_deprecated(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, "`[i]` Use /finish to complete branches")
```

Note: Keep existing /branch_finish for now, it will be replaced by /finish in Task 6.

**Step 3: Verify changes**

Run: `python -m py_compile src/codogram/handlers/threads.py src/codogram/handlers/branches.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/handlers/threads.py src/codogram/handlers/branches.py
git commit -m "feat(commands): add deprecated command redirects"
```

---

## Task 5: Modify do_branch_cleanup to Preserve Worktree

**Files:**
- Modify: `src/codogram/services/branch.py:12-59`
- Test: `tests/test_branch_service.py`

**Step 1: Write the failing test**

Create test file `tests/test_branch_service.py`:

```python
"""Tests for branch service."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.codogram.services.branch import do_branch_cleanup
from src.codogram.session_manager import ProjectState, ThreadInfo


@pytest.fixture
def mock_project():
    project = MagicMock(spec=ProjectState)
    project.cwd = "/tmp/test-project"
    project.project_name = "test-project"
    return project


@pytest.fixture
def mock_thread():
    thread = MagicMock(spec=ThreadInfo)
    thread.name = "feature-x"
    thread.thread_id = 123
    thread.worktree_path = "/tmp/test-project/.worktrees/feature-x"
    thread.watcher_task = None
    thread.poller_task = None
    thread.binding_task = None
    thread.get_tmux_session = MagicMock(return_value="test-project-feature-x")
    return thread


@pytest.mark.asyncio
async def test_do_branch_cleanup_preserves_worktree(mock_project, mock_thread):
    """do_branch_cleanup should NOT delete worktree when keep_worktree=True."""
    bot = AsyncMock()

    with patch("src.codogram.services.branch.subprocess.run") as mock_run, \
         patch("src.codogram.services.branch.remove_worktree") as mock_remove, \
         patch("src.codogram.services.branch.project_manager") as mock_pm:

        await do_branch_cleanup(
            bot=bot,
            chat_id=-100123,
            project=mock_project,
            thread=mock_thread,
            force=False,
            keep_worktree=True,  # NEW parameter
        )

        # Should NOT call remove_worktree
        mock_remove.assert_not_called()

        # Should still kill tmux
        mock_run.assert_called_once()

        # worktree_path should be preserved
        assert mock_thread.worktree_path == "/tmp/test-project/.worktrees/feature-x"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_branch_service.py -v`
Expected: FAIL - `keep_worktree` parameter doesn't exist

**Step 3: Implement keep_worktree parameter**

Modify `src/codogram/services/branch.py`:

```python
async def do_branch_cleanup(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    thread: ThreadInfo,
    force: bool,
    keep_worktree: bool = False,  # NEW: for /finish (preserve worktree)
) -> None:
    """Clean up worktree, tmux, and archive topic.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for the topic
        project: Project state
        thread: Thread to cleanup
        force: If True, force delete branch even if unmerged
        keep_worktree: If True, preserve worktree and git branch (for /finish)
    """
    main_repo = Path(project.cwd)
    worktree_path = Path(thread.worktree_path) if thread.worktree_path else None
    branch_name = thread.name

    # Cancel background tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Remove worktree and branch (only if not keeping)
    if worktree_path and not keep_worktree:
        remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True, force=force)
        thread.worktree_path = None

    # Archive topic
    try:
        await bot.close_forum_topic(chat_id, thread.thread_id)
        await bot.edit_forum_topic(chat_id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")
    except Exception:
        pass  # Topic may already be closed

    # Update thread state
    thread.archived = True
    # Only clear session_id if deleting worktree
    if not keep_worktree:
        thread.session_id = None
    project_manager._save()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_branch_service.py -v`
Expected: PASS

**Step 5: Add test for default behavior (backward compatibility)**

Add to `tests/test_branch_service.py`:

```python
@pytest.mark.asyncio
async def test_do_branch_cleanup_deletes_worktree_by_default(mock_project, mock_thread):
    """do_branch_cleanup should delete worktree by default (backward compat)."""
    bot = AsyncMock()

    with patch("src.codogram.services.branch.subprocess.run") as mock_run, \
         patch("src.codogram.services.branch.remove_worktree") as mock_remove, \
         patch("src.codogram.services.branch.project_manager") as mock_pm:

        await do_branch_cleanup(
            bot=bot,
            chat_id=-100123,
            project=mock_project,
            thread=mock_thread,
            force=False,
            # keep_worktree not passed - defaults to False
        )

        # Should call remove_worktree
        mock_remove.assert_called_once()
```

**Step 6: Run all tests**

Run: `PYTHONPATH=src pytest tests/test_branch_service.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/codogram/services/branch.py tests/test_branch_service.py
git commit -m "feat(branch): add keep_worktree param to do_branch_cleanup"
```

---

## Task 6: Create /finish Handler

**Files:**
- Create: `src/codogram/handlers/finish.py`
- Modify: `src/codogram/main.py` (add router)
- Test: `tests/test_finish_handler.py`

**Step 1: Write the failing test**

Create `tests/test_finish_handler.py`:

```python
"""Tests for /finish command."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.message_thread_id = 456
    msg.text = "/finish"
    return msg


@pytest.mark.asyncio
async def test_finish_in_regular_topic_shows_confirmation(mock_message):
    """In regular topic (no worktree), /finish should show archive confirmation."""
    from src.codogram.handlers.finish import cmd_finish

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_thread = MagicMock()
    mock_thread.worktree_path = None  # Regular topic
    mock_thread.name = "test-thread"
    mock_project.threads = {456: mock_thread}
    mock_project.get_thread = MagicMock(return_value=mock_thread)

    with patch("src.codogram.handlers.finish.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_finish(mock_message, mock_queue)

        # Should show confirmation
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Archive" in call_args[0][1] or "archive" in str(call_args)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_finish_handler.py -v`
Expected: FAIL - module not found

**Step 3: Create finish.py handler**

Create `src/codogram/handlers/finish.py`:

```python
"""Unified /finish command for archiving topics and completing branches."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group
from ..services.branch import do_branch_cleanup
from ..git_utils import (
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
)
from ..worktree import merge_branch, push_branch

router = Router(name="finish")


@router.message(Command("finish"))
async def cmd_finish(message: Message, telegram_queue: TelegramQueue):
    """Finish current topic: archive (regular) or merge+archive (branch)."""
    thread_id = message.message_thread_id

    # Check if in General (no thread_id)
    if thread_id is None:
        await telegram_queue.reply(
            message,
            "`[i]` Nothing to finish here. Use /clear to start fresh."
        )
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await telegram_queue.reply(message, "`[!]` Thread not found.")
        return

    # Branch topic (has worktree)
    if thread.worktree_path:
        await _show_branch_finish_options(message, telegram_queue, project, thread)
    else:
        # Regular topic - show archive confirmation
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Yes, archive", callback_data=f"finish:archive:{thread_id}")],
            [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
        ])
        await telegram_queue.reply(
            message,
            f"Archive topic `{thread.name}`?\n\n"
            "This will:\n"
            "- Close tmux session\n"
            "- Close topic in Telegram",
            reply_markup=keyboard,
        )


async def _show_branch_finish_options(
    message: Message,
    telegram_queue: TelegramQueue,
    project,
    thread,
):
    """Show merge options for branch topics."""
    thread_id = thread.thread_id
    worktree_path = Path(thread.worktree_path)

    # Check uncommitted changes in worktree
    if worktree_path.exists() and has_uncommitted_changes(worktree_path):
        await telegram_queue.reply(message, "`[!]` Uncommitted changes. Commit or stash first.")
        return

    # Build merge options
    default_branch = get_default_branch(Path(project.cwd))
    buttons = [
        [InlineKeyboardButton(
            text=f"Merge -> {default_branch}",
            callback_data=f"finish:merge:{thread_id}:{default_branch}"
        )]
    ]

    # Add base_branch option if different
    if thread.base_branch and thread.base_branch != default_branch:
        if branch_exists(Path(project.cwd), thread.base_branch):
            buttons.append([InlineKeyboardButton(
                text=f"Merge -> {thread.base_branch}",
                callback_data=f"finish:merge:{thread_id}:{thread.base_branch}"
            )])

    buttons.append([InlineKeyboardButton(
        text="Archive without merge",
        callback_data=f"finish:archive_branch:{thread_id}"
    )])
    buttons.append([InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await telegram_queue.reply(message, f"Finish `{thread.name}` branch:", reply_markup=keyboard)


# ===== Callbacks =====

@router.callback_query(F.data.startswith("finish:archive:"))
async def on_finish_archive(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive regular topic."""
    thread_id = int(callback.data.split(":")[2])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Archiving {thread.name}...")
    await callback.answer()

    # Use do_branch_cleanup with keep_worktree=True (no worktree anyway)
    await do_branch_cleanup(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
        force=False,
        keep_worktree=True,
    )

    await telegram_queue.edit(callback.message, f"`[v]` Topic `{thread.name}` archived")


@router.callback_query(F.data.startswith("finish:merge:"))
async def on_finish_merge(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show merge confirmation for branch."""
    parts = callback.data.split(":")
    thread_id = int(parts[2])
    target_branch = parts[3]

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
        await telegram_queue.edit(
            callback.message,
            "`[!]` Uncommitted changes in target directory. Commit or stash first."
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Yes, merge and archive",
            callback_data=f"finish:do_merge:{thread_id}:{target_branch}"
        )],
        [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
    ])

    await telegram_queue.edit(
        callback.message,
        f"Merge `{thread.name}` -> `{target_branch}`?\n\n"
        "This will:\n"
        "- Merge branch and push\n"
        "- Close tmux session\n"
        "- Archive topic\n\n"
        "Worktree and branch preserved for /start resume.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("finish:do_merge:"))
async def on_finish_do_merge(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Execute merge and archive (keep worktree)."""
    parts = callback.data.split(":")
    thread_id = int(parts[2])
    target_branch = parts[3]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Merging {thread.name} -> {target_branch}...")
    await callback.answer()

    main_repo = Path(project.cwd)
    branch_name = thread.name

    # Merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        if "conflicts" in result.error.lower():
            await telegram_queue.edit(
                callback.message,
                "`[!]` Merge conflicts. Resolve and run /finish again."
            )
        else:
            await telegram_queue.edit(callback.message, f"`[x]` Merge failed: {result.error}")
        return

    # Push (optional)
    push_result = push_branch(main_repo, target_branch)
    push_warning = "" if push_result.success else "\n`[!]` Push failed. Run `git push` manually."

    # Archive (keep worktree!)
    await do_branch_cleanup(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
        force=False,
        keep_worktree=True,  # KEY: preserve worktree for resume
    )

    await telegram_queue.edit(
        callback.message,
        f"`[v]` Branch {branch_name} merged and archived{push_warning}"
    )


@router.callback_query(F.data.startswith("finish:archive_branch:"))
async def on_finish_archive_branch(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive branch without merging."""
    thread_id = int(callback.data.split(":")[2])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Archiving {thread.name}...")
    await callback.answer()

    await do_branch_cleanup(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
        force=False,
        keep_worktree=True,  # Preserve worktree
    )

    await telegram_queue.edit(
        callback.message,
        f"`[v]` Branch `{thread.name}` archived (not merged)\n\n"
        "Use /start in this topic to resume."
    )
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_finish_handler.py -v`
Expected: PASS

**Step 5: Register router in main.py**

Add import and include router in `src/codogram/main.py`:

```python
# After other handler imports (around line 26):
from .handlers.finish import router as finish_router

# In register_handlers function (around line 115):
dp.include_router(finish_router)
```

**Step 6: Verify all compiles**

Run: `python -m py_compile src/codogram/main.py src/codogram/handlers/finish.py`
Expected: No output (success)

**Step 7: Commit**

```bash
git add src/codogram/handlers/finish.py src/codogram/main.py tests/test_finish_handler.py
git commit -m "feat(finish): add unified /finish command"
```

---

## Task 7: Update /start to Handle Archived Topics

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Test: `tests/test_start_flow.py`

**Step 1: Read current start_flow.py to understand structure**

This task requires understanding the existing flow. Check if archived handling exists.

**Step 2: Add archived topic handling**

In `handle_start` method, after thread lookup, add:

```python
# Reopen archived topic
if thread and thread.archived:
    thread.archived = False
    project_manager._save()
    # Remove archive icon
    try:
        await self.bot.edit_forum_topic(
            chat_id, thread_id, icon_custom_emoji_id=None
        )
    except Exception:
        pass
```

**Step 3: Verify changes**

Run: `python -m py_compile src/codogram/services/start_flow.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/services/start_flow.py
git commit -m "feat(start): handle archived topic reopening"
```

---

## Task 8: Update /help to Show New Menu

**Files:**
- Modify: `src/codogram/handlers/settings.py`

**Step 1: Update help text**

Find the `/help` command handler and update the help text to match new menu structure:

```python
HELP_TEXT = """
*Everyday:*
/esc — Cancel current operation
/auto\\_accept — Toggle auto\\-accept mode

*Create:*
/thread — New topic in project directory
/branch — New isolated feature branch \\+ topic

*Complete:*
/clear — Clear context, start fresh
/finish — Merge branch, archive topic

*Settings:*
/start — Connect Claude or show status
/settings — View current settings
/restart — Force restart Claude
/my\\_chat\\_id — Show chat and thread IDs

*Help:*
/help — This message
"""
```

**Step 2: Verify changes**

Run: `python -m py_compile src/codogram/handlers/settings.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "docs(help): update /help with new menu structure"
```

---

## Task 9: Integration Test

**Files:**
- Test with Telegram MCP

**Step 1: Restart bot**

Run: `./restart.sh`

**Step 2: Test /help shows new menu**

Send `/help` via Telegram MCP and verify new menu structure.

**Step 3: Test /thread alias**

Send `/thread` and verify it works same as `/thread_create`.

**Step 4: Test /branch alias**

Send `/branch test-branch` and verify it creates branch.

**Step 5: Test /finish in branch topic**

Send `/finish` in branch topic and verify:
- Shows merge options
- After merge, worktree is preserved
- Topic is archived

**Step 6: Test /start in archived topic**

Reopen archived topic manually, send `/start`, verify:
- Topic is unarchived
- Claude can resume

**Step 7: Commit integration test results**

```bash
git add -A
git commit -m "test: verify menu-redesign integration"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Update menu structure | main.py |
| 2 | Add /thread, /branch aliases | threads.py, branches.py |
| 3 | Make /new alias for /clear | sessions.py |
| 4 | Add deprecated command redirects | threads.py, branches.py |
| 5 | Add keep_worktree to do_branch_cleanup | services/branch.py |
| 6 | Create /finish handler | handlers/finish.py, main.py |
| 7 | Handle archived topics in /start | services/start_flow.py |
| 8 | Update /help text | handlers/settings.py |
| 9 | Integration test | - |

**Prerequisites:** None (this is the first plan)

**Depends on:** session-resume plan (for full /start resume flow)
