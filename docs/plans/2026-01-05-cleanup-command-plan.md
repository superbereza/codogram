# /cleanup Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit `/cleanup` command to delete archived branches when disk space or git cleanup is needed.

**Architecture:** New handler `handlers/cleanup.py` with list/delete functionality, path validation for safety, unmerged commits check before deletion.

**Tech Stack:** Python 3.11, aiogram 3.x, git

**Prerequisites:** menu-redesign and session-resume plans (for archived topic handling)

---

## Task 1: Add get_days_inactive Helper

**Files:**
- Create: `src/codogram/utils/cleanup.py`
- Test: `tests/test_cleanup_utils.py`

**Step 1: Write the failing test**

Create `tests/test_cleanup_utils.py`:

```python
"""Tests for cleanup utilities."""
import pytest
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock


def test_get_days_inactive_no_jsonl_path():
    """Should return 0 if no jsonl_path."""
    from codogram.utils.cleanup import get_days_inactive
    from codogram.session_manager import ThreadInfo

    thread = MagicMock(spec=ThreadInfo)
    thread.jsonl_path = None

    assert get_days_inactive(thread) == 0


def test_get_days_inactive_file_not_exists():
    """Should return 0 if jsonl file doesn't exist."""
    from codogram.utils.cleanup import get_days_inactive
    from codogram.session_manager import ThreadInfo

    thread = MagicMock(spec=ThreadInfo)
    thread.jsonl_path = "/nonexistent/path.jsonl"

    assert get_days_inactive(thread) == 0


def test_get_days_inactive_calculates_from_mtime():
    """Should calculate days from file mtime."""
    from codogram.utils.cleanup import get_days_inactive
    from codogram.session_manager import ThreadInfo
    import os

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        # Set mtime to 10 days ago
        ten_days_ago = time.time() - (10 * 86400)
        os.utime(f.name, (ten_days_ago, ten_days_ago))

        thread = MagicMock(spec=ThreadInfo)
        thread.jsonl_path = f.name

        days = get_days_inactive(thread)
        assert 9 <= days <= 11  # Allow some tolerance

        os.unlink(f.name)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py -v`
Expected: FAIL - module not found

**Step 3: Create cleanup utils module**

Create `src/codogram/utils/__init__.py` (if not exists):
```python
"""Utility modules."""
```

Create `src/codogram/utils/cleanup.py`:

```python
"""Cleanup utilities for /cleanup command."""
import time
from pathlib import Path

from ..session_manager import ThreadInfo


def get_days_inactive(thread: ThreadInfo) -> int:
    """Get days since last Claude activity.

    Uses jsonl file modification time as indicator of last activity.

    Args:
        thread: Thread to check

    Returns:
        Days since last activity, or 0 if no jsonl file
    """
    if not thread.jsonl_path:
        return 0

    jsonl = Path(thread.jsonl_path)
    if not jsonl.exists():
        return 0

    mtime = jsonl.stat().st_mtime
    return int((time.time() - mtime) / 86400)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/utils/__init__.py src/codogram/utils/cleanup.py tests/test_cleanup_utils.py
git commit -m "feat(cleanup): add get_days_inactive helper"
```

---

## Task 2: Add validate_worktree_path Helper

**Files:**
- Modify: `src/codogram/utils/cleanup.py`
- Test: `tests/test_cleanup_utils.py`

**Step 1: Write the failing test**

Add to `tests/test_cleanup_utils.py`:

```python
def test_validate_worktree_path_must_be_in_project():
    """Worktree path must be child of project directory."""
    from codogram.utils.cleanup import validate_worktree_path

    # Path outside project - NOT valid
    assert validate_worktree_path("/tmp/worktree", "/home/user/project") is False

    # Path inside project - valid
    assert validate_worktree_path(
        "/home/user/project/.worktrees/feature",
        "/home/user/project"
    ) is True


def test_validate_worktree_path_must_contain_worktrees():
    """Worktree path must contain .worktrees segment."""
    from codogram.utils.cleanup import validate_worktree_path

    # Path without .worktrees - NOT valid (safety check)
    assert validate_worktree_path(
        "/home/user/project/src/feature",
        "/home/user/project"
    ) is False

    # Path with .worktrees - valid
    assert validate_worktree_path(
        "/home/user/project/.worktrees/feature",
        "/home/user/project"
    ) is True


def test_validate_worktree_path_handles_symlinks():
    """Should resolve symlinks before validation."""
    from codogram.utils.cleanup import validate_worktree_path
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir) / "project"
        project.mkdir()
        worktrees = project / ".worktrees"
        worktrees.mkdir()
        feature = worktrees / "feature"
        feature.mkdir()

        # Create symlink outside project pointing inside
        outside_link = Path(tmpdir) / "link"
        outside_link.symlink_to(feature)

        # Even with symlink, resolved path is inside project
        assert validate_worktree_path(str(outside_link), str(project)) is True
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py::test_validate_worktree_path_must_be_in_project -v`
Expected: FAIL

**Step 3: Add validate_worktree_path function**

Add to `src/codogram/utils/cleanup.py`:

```python
def validate_worktree_path(worktree_path: str, project_cwd: str) -> bool:
    """Safety check: ensure path is within project and is a worktree.

    Args:
        worktree_path: Path to validate
        project_cwd: Project root directory

    Returns:
        True if path is safe to delete, False otherwise
    """
    path = Path(worktree_path).resolve()
    project = Path(project_cwd).resolve()

    # Must be child of project
    try:
        path.relative_to(project)
    except ValueError:
        return False

    # Must contain .worktrees segment (safety) - use path.parts for robustness
    if ".worktrees" not in path.parts:
        return False

    return True
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/utils/cleanup.py tests/test_cleanup_utils.py
git commit -m "feat(cleanup): add validate_worktree_path helper"
```

---

## Task 3: Add check_unmerged_commits Helper

**Files:**
- Modify: `src/codogram/utils/cleanup.py`
- Test: `tests/test_cleanup_utils.py`

**Step 1: Write the failing test**

Add to `tests/test_cleanup_utils.py`:

```python
def test_check_unmerged_commits_returns_list():
    """Should return list of unmerged commit summaries."""
    from codogram.utils.cleanup import check_unmerged_commits
    from unittest.mock import patch, MagicMock

    # Mock subprocess.run to return unmerged commits
    mock_result = MagicMock()
    mock_result.stdout = "abc1234 Add feature X\ndef5678 Fix bug Y"
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        commits = check_unmerged_commits("/project", "feature-x", "main")

        assert len(commits) == 2
        assert "abc1234 Add feature X" in commits
        assert "def5678 Fix bug Y" in commits


def test_check_unmerged_commits_empty_when_merged():
    """Should return empty list when no unmerged commits."""
    from codogram.utils.cleanup import check_unmerged_commits
    from unittest.mock import patch, MagicMock

    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        commits = check_unmerged_commits("/project", "feature-x", "main")

        assert commits == []
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py::test_check_unmerged_commits_returns_list -v`
Expected: FAIL

**Step 3: Add check_unmerged_commits function**

Add to `src/codogram/utils/cleanup.py`:

```python
import subprocess


def check_unmerged_commits(project_cwd: str, branch_name: str, base_branch: str) -> list[str]:
    """Check if branch has commits not in base branch.

    Args:
        project_cwd: Project root directory
        branch_name: Branch to check
        base_branch: Base branch to compare against

    Returns:
        List of commit summaries (oneline format), empty if fully merged
    """
    result = subprocess.run(
        ["git", "log", f"{base_branch}..{branch_name}", "--oneline"],
        cwd=project_cwd,
        capture_output=True,
        text=True
    )

    if result.stdout.strip():
        return result.stdout.strip().split("\n")
    return []
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_cleanup_utils.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/utils/cleanup.py tests/test_cleanup_utils.py
git commit -m "feat(cleanup): add check_unmerged_commits helper"
```

---

## Task 4: Create delete_thread_files Function in Services

**Files:**
- Create: `src/codogram/services/thread_lifecycle.py`
- Test: `tests/test_thread_lifecycle.py`

**Note:** Following project architecture, orchestration functions go in `services/`, pure functions stay in `utils/`. This is consistent with `archive_thread` in `services/branch.py`.

**Step 1: Write the failing test**

Create `tests/test_thread_lifecycle.py`:

```python
"""Tests for thread lifecycle service."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_delete_thread_files_deletes_worktree_and_branch():
    """delete_thread_files should delete worktree dir and git branch."""
    from codogram.services.thread_lifecycle import delete_thread_files

    mock_thread = MagicMock()
    mock_thread.name = "feature-x"
    mock_thread.worktree_path = "/project/.worktrees/feature-x"
    mock_thread.watcher_task = None
    mock_thread.poller_task = None
    mock_thread.binding_task = None
    mock_thread.get_tmux_session = MagicMock(return_value="proj-feature-x")

    mock_project = MagicMock()
    mock_project.cwd = "/project"
    mock_project.project_name = "proj"

    with patch("codogram.services.thread_lifecycle.validate_worktree_path", return_value=True), \
         patch("codogram.services.thread_lifecycle.is_tmux_session_exists", return_value=False), \
         patch("codogram.services.thread_lifecycle.shutil.rmtree") as mock_rmtree, \
         patch("codogram.services.thread_lifecycle.subprocess.run") as mock_run, \
         patch("codogram.services.thread_lifecycle.project_manager") as mock_pm:

        await delete_thread_files(mock_thread, mock_project)

        # Should delete worktree directory
        mock_rmtree.assert_called_once_with(
            "/project/.worktrees/feature-x",
            ignore_errors=True
        )

        # Should delete git branch
        mock_run.assert_called()
        branch_delete_call = [c for c in mock_run.call_args_list
                             if "branch" in str(c) and "-D" in str(c)]
        assert len(branch_delete_call) == 1

        # Should mark thread as deleted
        assert mock_thread.deleted is True
        assert mock_thread.worktree_path is None


def test_can_delete_returns_true_for_archived():
    """can_delete should return True for archived, non-deleted threads."""
    from codogram.services.thread_lifecycle import can_delete

    mock_thread = MagicMock()
    mock_thread.archived = True
    mock_thread.deleted = False

    assert can_delete(mock_thread) is True


def test_can_delete_returns_false_for_active():
    """can_delete should return False for non-archived threads."""
    from codogram.services.thread_lifecycle import can_delete

    mock_thread = MagicMock()
    mock_thread.archived = False
    mock_thread.deleted = False

    assert can_delete(mock_thread) is False
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_thread_lifecycle.py -v`
Expected: FAIL - module not found

**Step 3: Create thread_lifecycle service**

Create `src/codogram/services/thread_lifecycle.py`:

```python
"""Thread lifecycle management: delete archived threads."""
import shutil
import subprocess

from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..project_launcher import is_tmux_session_exists
from ..utils.cleanup import validate_worktree_path


def can_delete(thread: ThreadInfo) -> bool:
    """Check if thread can be deleted.

    Returns True if thread is archived and not already deleted.
    """
    return thread.archived and not thread.deleted


async def delete_thread_files(thread: ThreadInfo, project: ProjectState) -> None:
    """Delete worktree directory and git branch.

    Used by /cleanup command. Does NOT require Telegram bot.

    Args:
        thread: Thread to delete
        project: Project state

    Raises:
        ValueError: If worktree path is invalid (safety check)
    """
    # Cancel background tasks (if any still running)
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux if running
    tmux_name = thread.get_tmux_session(project.project_name)
    if is_tmux_session_exists(tmux_name):
        subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Validate and delete worktree directory
    if thread.worktree_path:
        if not validate_worktree_path(thread.worktree_path, project.cwd):
            raise ValueError(f"Invalid worktree path: {thread.worktree_path}")
        shutil.rmtree(thread.worktree_path, ignore_errors=True)

    # Delete git branch
    subprocess.run(
        ["git", "branch", "-D", thread.name],
        cwd=project.cwd,
        capture_output=True
    )

    # Mark as deleted (keep ThreadInfo for history)
    thread.deleted = True
    thread.worktree_path = None

    # Save config
    project_manager._save()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_thread_lifecycle.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/thread_lifecycle.py tests/test_thread_lifecycle.py
git commit -m "feat(services): add delete_thread_files to thread_lifecycle"
```

---

## Task 5: Add deleted Field to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_thread_deleted_field_serialization():
    """deleted field should serialize/deserialize properly."""
    from codogram.session_manager import ThreadInfo

    # Default value
    thread = ThreadInfo(name="test", thread_id=123)
    assert thread.deleted is False

    # Serialize
    data = thread.to_dict()
    assert "deleted" in data
    assert data["deleted"] is False

    # Mark as deleted
    thread.deleted = True
    data = thread.to_dict()
    assert data["deleted"] is True

    # Deserialize
    restored = ThreadInfo.from_dict(data)
    assert restored.deleted is True
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_deleted_field_serialization -v`
Expected: FAIL - deleted field not found

**Step 3: Add deleted field to ThreadInfo**

Add to ThreadInfo dataclass:

```python
deleted: bool = False  # True after /cleanup
```

**Step 4: Update to_dict method**

Add to to_dict:

```python
"deleted": self.deleted,
```

**Step 5: Update from_dict method**

Add to from_dict:

```python
deleted=data.get("deleted", False),
```

**Step 6: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_deleted_field_serialization -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add deleted field to ThreadInfo"
```

---

## Task 6: Create /cleanup Handler

**Files:**
- Create: `src/codogram/handlers/cleanup.py`
- Modify: `src/codogram/main.py` (add router)
- Test: `tests/test_cleanup_handler.py`

**Step 1: Write the failing test**

Create `tests/test_cleanup_handler.py`:

```python
"""Tests for /cleanup command."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_message():
    msg = MagicMock()
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.message_thread_id = None  # General chat
    msg.text = "/cleanup"
    return msg


@pytest.mark.asyncio
async def test_cleanup_no_args_shows_archived_list(mock_message):
    """Without args, /cleanup should list archived branches."""
    from codogram.handlers.cleanup import cmd_cleanup

    mock_queue = AsyncMock()
    mock_project = MagicMock()

    mock_thread1 = MagicMock()
    mock_thread1.name = "feature-x"
    mock_thread1.archived = True
    mock_thread1.deleted = False
    mock_thread1.worktree_path = "/project/.worktrees/feature-x"

    mock_thread2 = MagicMock()
    mock_thread2.name = "main"
    mock_thread2.archived = False
    mock_thread2.deleted = False
    mock_thread2.worktree_path = None

    mock_project.threads = {123: mock_thread1, None: mock_thread2}

    with patch("codogram.handlers.cleanup.project_manager") as mock_pm, \
         patch("codogram.handlers.cleanup.get_days_inactive", return_value=45):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_cleanup(mock_message, mock_queue)

        # Should show list with archived branches
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "feature-x" in call_args[0][1]
        assert "45 days" in call_args[0][1]
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cleanup_handler.py -v`
Expected: FAIL - module not found

**Step 3: Create cleanup handler**

Create `src/codogram/handlers/cleanup.py`:

```python
"""Cleanup command for deleting archived branches."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..utils.cleanup import get_days_inactive, check_unmerged_commits
from ..services.thread_lifecycle import delete_thread_files
from ..git_utils import get_default_branch
from pathlib import Path

router = Router(name="cleanup")


def _get_archived_threads(project):
    """Get list of archived, non-deleted threads with worktrees."""
    return [
        t for t in project.threads.values()
        if t.archived and not t.deleted and t.worktree_path
    ]


@router.message(Command("cleanup"))
async def cmd_cleanup(message: Message, telegram_queue: TelegramQueue):
    """Handle /cleanup command."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    args = message.text.split(maxsplit=1)

    if len(args) == 1:
        # No args - list archived branches
        await _show_archived_list(message, telegram_queue, project)
    else:
        # With branch name - confirm delete
        branch_name = args[1]
        await _confirm_delete_branch(message, telegram_queue, project, branch_name)


async def _show_archived_list(message: Message, telegram_queue: TelegramQueue, project):
    """Show list of archived branches."""
    archived = _get_archived_threads(project)

    if not archived:
        await telegram_queue.reply(message, "`[i]` No archived branches to clean up")
        return

    # Build list
    lines = ["`[i]` Archived branches:\n"]
    for t in archived:
        days = get_days_inactive(t)
        lines.append(f"• `{t.name}` — {days} days inactive")

    # Count old branches (>30 days)
    old_count = sum(1 for t in archived if get_days_inactive(t) > 30)

    # Build keyboard
    buttons = []
    if old_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"Delete old (>{30}d): {old_count}",
            callback_data="cleanup:delete_old"
        )])
    buttons.append([InlineKeyboardButton(
        text=f"Delete all: {len(archived)}",
        callback_data="cleanup:delete_all"
    )])
    buttons.append([InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await telegram_queue.reply(message, "\n".join(lines), reply_markup=keyboard)


async def _confirm_delete_branch(message: Message, telegram_queue: TelegramQueue, project, branch_name: str):
    """Show confirmation for deleting specific branch."""
    # Find thread by name
    thread = None
    for t in project.threads.values():
        if t.name == branch_name:
            thread = t
            break

    if not thread:
        await telegram_queue.reply(message, f"`[!]` Branch `{branch_name}` not found")
        return

    if not thread.archived:
        await telegram_queue.reply(
            message,
            f"`[!]` Branch `{branch_name}` is active\n\nUse /finish first to archive it."
        )
        return

    if thread.deleted:
        await telegram_queue.reply(message, f"`[!]` Branch `{branch_name}` already deleted")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Delete",
            callback_data=f"cleanup:delete:{thread.thread_id}"
        )],
        [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
    ])

    await telegram_queue.reply(
        message,
        f"Delete `{branch_name}`?\n"
        f"- Worktree: `{thread.worktree_path}`\n"
        f"- Git branch: `{branch_name}`",
        reply_markup=keyboard,
    )


# ===== Callbacks =====

@router.callback_query(F.data == "cleanup:delete_old")
async def on_delete_old(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show confirmation for deleting old branches."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    archived = _get_archived_threads(project)
    old_threads = [t for t in archived if get_days_inactive(t) > 30]

    if not old_threads:
        await telegram_queue.edit(callback.message, "`[i]` No branches older than 30 days")
        await callback.answer()
        return

    lines = [f"`[!]` Delete {len(old_threads)} branches inactive >30 days?\n"]
    for t in old_threads:
        days = get_days_inactive(t)
        lines.append(f"• `{t.name}` ({days} days)")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, delete old", callback_data="cleanup:confirm_old")],
        [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
    ])

    await telegram_queue.edit(callback.message, "\n".join(lines), reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "cleanup:confirm_old")
async def on_confirm_old(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Delete all branches >30 days inactive."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    archived = _get_archived_threads(project)
    old_threads = [t for t in archived if get_days_inactive(t) > 30]

    await telegram_queue.edit(callback.message, f"`[~]` Deleting {len(old_threads)} branches...")
    await callback.answer()

    deleted = []
    for thread in old_threads:
        try:
            await delete_thread_files(thread, project)
            deleted.append(thread.name)
        except Exception as e:
            pass  # Continue with others

    await telegram_queue.edit(
        callback.message,
        f"`[v]` Deleted {len(deleted)} branches:\n" + "\n".join(f"• `{n}`" for n in deleted)
    )


@router.callback_query(F.data == "cleanup:delete_all")
async def on_delete_all(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show confirmation for deleting all archived branches."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    archived = _get_archived_threads(project)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, delete all", callback_data="cleanup:confirm_all")],
        [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
    ])

    await telegram_queue.edit(
        callback.message,
        f"`[!]` Delete ALL {len(archived)} archived branches?\n\n"
        "This cannot be undone.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "cleanup:confirm_all")
async def on_confirm_all(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Delete all archived branches."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    archived = _get_archived_threads(project)

    await telegram_queue.edit(callback.message, f"`[~]` Deleting {len(archived)} branches...")
    await callback.answer()

    deleted = []
    for thread in archived:
        try:
            await delete_thread_files(thread, project)
            deleted.append(thread.name)
        except Exception as e:
            pass

    await telegram_queue.edit(
        callback.message,
        f"`[v]` Deleted {len(deleted)} branches:\n" + "\n".join(f"• `{n}`" for n in deleted)
    )


@router.callback_query(F.data.startswith("cleanup:delete:"))
async def on_delete_specific(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Delete specific branch with unmerged check."""
    thread_id = int(callback.data.split(":")[2])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Check for unmerged commits
    default_branch = get_default_branch(Path(project.cwd))
    unmerged = check_unmerged_commits(project.cwd, thread.name, default_branch)

    if unmerged:
        # Show warning with unmerged commits
        lines = ["`[!]` Branch has unmerged commits:\n"]
        for commit in unmerged[:5]:  # Limit to 5
            lines.append(f"• `{commit}`")
        if len(unmerged) > 5:
            lines.append(f"• ... and {len(unmerged) - 5} more")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Delete anyway",
                callback_data=f"cleanup:force_delete:{thread_id}"
            )],
            [InlineKeyboardButton(text="[<<] Cancel", callback_data="cancel")]
        ])

        await telegram_queue.edit(callback.message, "\n".join(lines), reply_markup=keyboard)
        await callback.answer()
        return

    # No unmerged - delete directly
    await telegram_queue.edit(callback.message, f"`[~]` Deleting {thread.name}...")
    await callback.answer()

    try:
        await delete_thread_files(thread, project)
        await telegram_queue.edit(callback.message, f"`[v]` Deleted: `{thread.name}`")
    except Exception as e:
        await telegram_queue.edit(callback.message, f"`[x]` Delete failed: {e}")


@router.callback_query(F.data.startswith("cleanup:force_delete:"))
async def on_force_delete(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Force delete branch despite unmerged commits."""
    thread_id = int(callback.data.split(":")[2])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Deleting {thread.name}...")
    await callback.answer()

    try:
        await delete_thread_files(thread, project)
        await telegram_queue.edit(callback.message, f"`[v]` Deleted: `{thread.name}`")
    except Exception as e:
        await telegram_queue.edit(callback.message, f"`[x]` Delete failed: {e}")
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cleanup_handler.py -v`
Expected: PASS

**Step 5: Register router in handlers/__init__.py**

Add import in `src/codogram/handlers/__init__.py`:

```python
from . import cleanup
```

Add router registration in `register_handlers` function (before common.router):

```python
dp.include_router(cleanup.router)
```

**Step 6: Verify all compiles**

Run: `python -m py_compile src/codogram/handlers/cleanup.py src/codogram/handlers/__init__.py`
Expected: No output (success)

**Step 7: Commit**

```bash
git add src/codogram/handlers/cleanup.py src/codogram/handlers/__init__.py tests/test_cleanup_handler.py
git commit -m "feat(cleanup): add /cleanup command handler"
```

---

## Task 7: Integration Test - Cleanup

**Files:**
- Test with Telegram MCP

**Step 1: Restart bot**

Run: `./restart.sh`

**Step 2: Create and archive a branch**

1. `/branch test-cleanup`
2. Wait for Claude to start
3. `/finish` and merge

**Step 3: Test /cleanup list**

Send `/cleanup` and verify:
- Shows archived branches
- Shows days inactive
- Has "Delete old" and "Delete all" buttons

**Step 4: Test /cleanup with branch name**

Send `/cleanup test-cleanup` and verify:
- Shows confirmation with worktree path
- Has "Delete" button

**Step 5: Test deletion**

Click "Delete" and verify:
- Worktree directory deleted
- Git branch deleted
- Thread marked as deleted
- Not shown in /help

**Step 6: Commit**

```bash
git add -A
git commit -m "test: verify /cleanup integration"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add get_days_inactive helper | utils/cleanup.py |
| 2 | Add validate_worktree_path helper | utils/cleanup.py |
| 3 | Add check_unmerged_commits helper | utils/cleanup.py |
| 4 | Add delete_thread_files function | services/thread_lifecycle.py |
| 5 | Add deleted field to ThreadInfo | session_manager.py |
| 6 | Create /cleanup handler | handlers/cleanup.py, handlers/__init__.py |
| 7 | Integration test | - |

**Architecture notes:**
- Pure functions (validation, queries) in `utils/cleanup.py`
- Orchestration (state mutation + I/O) in `services/thread_lifecycle.py`
- Consistent with `archive_thread` in `services/branch.py`

**Prerequisites:** menu-redesign and session-resume plans

**Notes:**
- jsonl files are NOT deleted (preserve history)
- ThreadInfo kept in config (just marked deleted)
- Path validation prevents accidental deletion of non-worktree paths
