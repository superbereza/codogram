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

## Task 3: Replace Deprecated Commands with Redirects

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

**Step 2: Replace /branch_finish handler in branches.py**

Find and **replace** the existing `/branch_finish` handler (lines 190-228) with a simple redirect:

```python
@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, "`[i]` Use /finish to complete branches")
```

Also **delete** all related callback handlers:
- `on_branch_merge_selected` (bf_merge:)
- `on_branch_do_merge` (bf_do_merge:)
- `on_branch_delete_selected` (bf_delete:)
- `on_branch_do_delete` (bf_do_delete:)

These are replaced by `/finish` callbacks in the new handler.

**Step 3: Verify changes**

Run: `python -m py_compile src/codogram/handlers/threads.py src/codogram/handlers/branches.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/codogram/handlers/threads.py src/codogram/handlers/branches.py
git commit -m "refactor(commands): replace /branch_finish with redirect to /finish"
```

---

## Task 4: Rename and Modify do_branch_cleanup -> archive_thread

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

from codogram.services.branch import archive_thread
from codogram.session_manager import ProjectState, ThreadInfo


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
async def test_archive_thread_preserves_worktree(mock_project, mock_thread):
    """archive_thread should keep worktree and session_id for resume."""
    bot = AsyncMock()

    with patch("codogram.services.branch.subprocess.run") as mock_run, \
         patch("codogram.services.branch.project_manager") as mock_pm:

        await archive_thread(
            bot=bot,
            chat_id=-100123,
            project=mock_project,
            thread=mock_thread,
        )

        # Should kill tmux
        mock_run.assert_called_once()

        # worktree_path should be preserved (not deleted)
        assert mock_thread.worktree_path == "/tmp/test-project/.worktrees/feature-x"
        assert mock_thread.archived is True
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_branch_service.py -v`
Expected: FAIL - `archive_thread` function doesn't exist

**Step 3: Rename do_branch_cleanup to archive_thread and simplify**

Modify `src/codogram/services/branch.py`:

```python
async def archive_thread(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    thread: ThreadInfo,
) -> None:
    """Archive thread: kill tmux, close topic, keep worktree for resume.

    Used by /finish command. Does NOT delete worktree or git branch.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for the topic
        project: Project state
        thread: Thread to archive
    """
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

    # Archive topic in Telegram
    try:
        await bot.close_forum_topic(chat_id, thread.thread_id)
        await bot.edit_forum_topic(chat_id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")
    except Exception:
        pass  # Topic may already be closed

    # Update thread state (keep worktree_path and session_id for resume!)
    thread.archived = True
    project_manager._save()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_branch_service.py -v`
Expected: PASS

**Step 5: Update all callers to use new function name**

Search and replace `do_branch_cleanup` with `archive_thread` in:
- `handlers/branches.py` (if any remaining)
- `handlers/finish.py` (will be created in Task 5)

**Step 6: Commit**

```bash
git add src/codogram/services/branch.py tests/test_branch_service.py
git commit -m "refactor(branch): rename do_branch_cleanup to archive_thread"
```

---

## Task 5: Create /finish Handler

**Files:**
- Create: `src/codogram/handlers/finish.py`
- Modify: `src/codogram/handlers/__init__.py` (add router)
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
    from codogram.handlers.finish import cmd_finish

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_thread = MagicMock()
    mock_thread.worktree_path = None  # Regular topic
    mock_thread.name = "test-thread"
    mock_project.threads = {456: mock_thread}
    mock_project.get_thread = MagicMock(return_value=mock_thread)

    with patch("codogram.handlers.finish.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_finish(mock_message, mock_queue)

        # Should show confirmation with "Archive" in text
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Archive" in call_args[0][1]


@pytest.mark.asyncio
async def test_finish_in_general_shows_nothing_to_finish(mock_message):
    """In General (thread_id=None), /finish should suggest /clear."""
    from codogram.handlers.finish import cmd_finish

    mock_message.message_thread_id = None
    mock_queue = AsyncMock()

    await cmd_finish(mock_message, mock_queue)

    mock_queue.reply.assert_called_once()
    call_args = mock_queue.reply.call_args
    assert "Nothing to finish" in call_args[0][1]
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
from ..services.branch import archive_thread
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

    # Archive the thread (keeps worktree and session_id)
    await archive_thread(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
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

    # Archive (keeps worktree for resume!)
    await archive_thread(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
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

    await archive_thread(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        project=project,
        thread=thread,
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

**Step 5: Register router in handlers/__init__.py**

Modify `src/codogram/handlers/__init__.py`:

```python
# Add import at top (with other imports):
from . import finish

# In register_handlers function, add AFTER settings.router and BEFORE common.router:
dp.include_router(settings.router)      # /settings, /auto_accept, /help
dp.include_router(finish.router)        # /finish (NEW)
dp.include_router(common.router)        # cb_cancel
```

**Important:** Router must be added before `common.router` because common has catch-all handlers.

**Step 6: Verify all compiles**

Run: `python -m py_compile src/codogram/handlers/finish.py src/codogram/handlers/__init__.py`
Expected: No output (success)

**Step 7: Commit**

```bash
git add src/codogram/handlers/finish.py src/codogram/handlers/__init__.py tests/test_finish_handler.py
git commit -m "feat(finish): add unified /finish command"
```

---

## Task 6: Handle Archived Topics in /start Handler

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Background:** `StartFlowService` is synchronous and returns `FlowResult`. Archived topic handling requires async Telegram API calls, so it must be in the handler layer.

**Step 1: Add archived handling in _launch_claude_in_thread**

In `src/codogram/handlers/start.py`, find `_launch_claude_in_thread` function (around line 231).

**ADD** this block AFTER the `thread = project.threads.get(...)` null check and BEFORE `if thread.launch_task`:

```python
    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    # === ADD THIS BLOCK ===
    # Handle archived topic - reopen it
    if thread.archived:
        thread.archived = False
        project_manager._save()
        # Remove archive icon
        try:
            await message.bot.edit_forum_topic(
                message.chat.id, result.thread_id, icon_custom_emoji_id=""
            )
        except Exception:
            pass  # May fail if no icon was set
    # === END OF ADDED BLOCK ===

    if thread.launch_task and not thread.launch_task.done():
        return
```

**Note:** This is an INSERT, not a replacement. The rest of the function stays unchanged.

**Step 2: Verify changes**

Run: `python -m py_compile src/codogram/handlers/start.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(start): handle archived topic reopening in handler"
```

---

## Task 7: Update /help to Show New Menu

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

## Task 8: Integration Test

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
| 3 | Replace deprecated commands with redirects | threads.py, branches.py |
| 4 | Rename do_branch_cleanup -> archive_thread | services/branch.py |
| 5 | Create /finish handler | handlers/finish.py, handlers/__init__.py |
| 6 | Handle archived topics in /start | handlers/start.py |
| 7 | Update /help text | handlers/settings.py |
| 8 | Integration test | - |

**Prerequisites:** None (this is the first plan)

**Depends on:** session-resume plan (for full /start resume flow)
