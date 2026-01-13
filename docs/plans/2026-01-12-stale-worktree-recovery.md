# Stale Worktree Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Handle deleted worktrees gracefully with recovery options instead of crashing.

**Architecture:** Add `WorktreeState` detection before operations. Show inline keyboard with recovery options. New `handlers/worktree_recovery.py` module for recovery callbacks. Reuse existing `archive_thread()`.

**Tech Stack:** Python, aiogram, git commands

---

## Task 1: Add WorktreeState enum and detection

**Files:**
- Create: `src/codogram/domain/worktree_state.py`
- Test: `tests/unit/domain/test_worktree_state.py`

**Step 1: Write the failing test**

```python
# tests/unit/domain/test_worktree_state.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codogram.domain.worktree_state import WorktreeState, get_worktree_state
from codogram.session_manager import ThreadInfo


class TestGetWorktreeState:
    def test_no_worktree_returns_ok(self):
        """Thread without worktree_path returns OK."""
        thread = ThreadInfo(thread_id=1, name="test")
        result = get_worktree_state(thread, Path("/repo"))
        assert result == WorktreeState.OK

    def test_valid_worktree_returns_ok(self, tmp_path):
        """Existing worktree path returns OK."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        thread = ThreadInfo(thread_id=1, name="test", worktree_path=str(worktree_path))
        result = get_worktree_state(thread, Path("/repo"))
        assert result == WorktreeState.OK

    @patch("codogram.domain.worktree_state.branch_exists")
    def test_missing_worktree_with_branch_returns_missing_with_branch(self, mock_branch_exists, tmp_path):
        """Missing worktree but branch exists returns MISSING_WITH_BRANCH."""
        mock_branch_exists.return_value = True
        thread = ThreadInfo(thread_id=1, name="my-feature", worktree_path="/nonexistent")
        result = get_worktree_state(thread, tmp_path)
        assert result == WorktreeState.MISSING_WITH_BRANCH
        mock_branch_exists.assert_called_once_with(tmp_path, "my-feature")

    @patch("codogram.domain.worktree_state.branch_exists")
    def test_missing_worktree_no_branch_returns_missing_no_branch(self, mock_branch_exists, tmp_path):
        """Missing worktree and no branch returns MISSING_NO_BRANCH."""
        mock_branch_exists.return_value = False
        thread = ThreadInfo(thread_id=1, name="my-feature", worktree_path="/nonexistent")
        result = get_worktree_state(thread, tmp_path)
        assert result == WorktreeState.MISSING_NO_BRANCH
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_worktree_state.py -v`
Expected: FAIL with "No module named 'codogram.domain.worktree_state'"

**Step 3: Write minimal implementation**

```python
# src/codogram/domain/worktree_state.py
from enum import Enum
from pathlib import Path

from codogram.session_manager import ThreadInfo
from codogram.git_utils import branch_exists


class WorktreeState(Enum):
    OK = "ok"
    MISSING_WITH_BRANCH = "missing_with_branch"
    MISSING_NO_BRANCH = "missing_no_branch"


def get_worktree_state(thread: ThreadInfo, project_cwd: Path) -> WorktreeState:
    """Check worktree state for a thread."""
    if not thread.worktree_path:
        return WorktreeState.OK

    if Path(thread.worktree_path).exists():
        return WorktreeState.OK

    if branch_exists(project_cwd, thread.name):
        return WorktreeState.MISSING_WITH_BRANCH

    return WorktreeState.MISSING_NO_BRANCH
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_worktree_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/domain/worktree_state.py tests/unit/domain/test_worktree_state.py
git commit -m "feat: add WorktreeState enum and detection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add worktree recovery keyboard

**Files:**
- Modify: `src/codogram/keyboards/keyboards.py`
- Test: `tests/unit/keyboards/test_keyboards.py`

**Step 1: Write the failing test**

Add to `tests/unit/keyboards/test_keyboards.py`:

```python
class TestWorktreeRecoveryKeyboard:
    def test_missing_with_branch_keyboard(self):
        """Keyboard for missing worktree when branch exists."""
        from codogram.keyboards.keyboards import worktree_recovery_keyboard
        from codogram.domain.worktree_state import WorktreeState

        kb = worktree_recovery_keyboard(thread_id=123, state=WorktreeState.MISSING_WITH_BRANCH)
        buttons = kb.inline_keyboard

        assert len(buttons) == 3
        assert buttons[0][0].text == "Recreate worktree"
        assert buttons[0][0].callback_data == "wr_recreate:123"
        assert buttons[1][0].text == "Resume in main"
        assert buttons[1][0].callback_data == "wr_main:123"
        assert buttons[2][0].text == "Cancel"
        assert buttons[2][0].callback_data == "wr_cancel:123"

    def test_missing_no_branch_keyboard(self):
        """Keyboard for missing worktree when branch also missing."""
        from codogram.keyboards.keyboards import worktree_recovery_keyboard
        from codogram.domain.worktree_state import WorktreeState

        kb = worktree_recovery_keyboard(thread_id=456, state=WorktreeState.MISSING_NO_BRANCH)
        buttons = kb.inline_keyboard

        assert len(buttons) == 3
        assert buttons[0][0].text == "Create new"
        assert buttons[0][0].callback_data == "wr_create:456"
        assert buttons[1][0].text == "Resume in main"
        assert buttons[1][0].callback_data == "wr_main:456"
        assert buttons[2][0].text == "Cancel"
        assert buttons[2][0].callback_data == "wr_cancel:456"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/keyboards/test_keyboards.py::TestWorktreeRecoveryKeyboard -v`
Expected: FAIL with "cannot import name 'worktree_recovery_keyboard'"

**Step 3: Write minimal implementation**

Add to `src/codogram/keyboards/keyboards.py`:

```python
from codogram.domain.worktree_state import WorktreeState

def worktree_recovery_keyboard(thread_id: int, state: WorktreeState) -> InlineKeyboardMarkup:
    """Build keyboard for worktree recovery options."""
    builder = InlineKeyboardBuilder()

    if state == WorktreeState.MISSING_WITH_BRANCH:
        builder.button(text="Recreate worktree", callback_data=f"wr_recreate:{thread_id}")
    elif state == WorktreeState.MISSING_NO_BRANCH:
        builder.button(text="Create new", callback_data=f"wr_create:{thread_id}")

    builder.button(text="Resume in main", callback_data=f"wr_main:{thread_id}")
    builder.button(text="Cancel", callback_data=f"wr_cancel:{thread_id}")
    builder.adjust(1)

    return builder.as_markup()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/keyboards/test_keyboards.py::TestWorktreeRecoveryKeyboard -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/keyboards/keyboards.py tests/unit/keyboards/test_keyboards.py
git commit -m "feat: add worktree recovery keyboard

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add stale worktree detection to /finish

**Files:**
- Modify: `src/codogram/handlers/finish.py`
- Test: `tests/unit/handlers/test_finish.py`

**Step 1: Write the failing test**

Add to `tests/unit/handlers/test_finish.py`:

```python
class TestFinishStaleWorktree:
    @pytest.mark.asyncio
    async def test_finish_with_stale_worktree_shows_warning(self, finish_handler, mock_message, mock_queue):
        """Finish with stale worktree shows warning and archives."""
        from codogram.session_manager import ThreadInfo

        thread = ThreadInfo(
            thread_id=123,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        with patch.object(finish_handler.project_manager, "get_thread", return_value=thread):
            with patch("codogram.handlers.finish.archive_thread") as mock_archive:
                mock_archive.return_value = True
                await finish_handler.handle_finish(mock_message)

        # Should show warning about stale worktree
        call_args = mock_queue.enqueue.call_args_list
        messages = [str(call[1].get("text", call[0][1] if len(call[0]) > 1 else "")) for call in call_args]
        assert any("[!]" in msg and "not found" in msg.lower() for msg in messages)

        # Should still archive
        mock_archive.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/handlers/test_finish.py::TestFinishStaleWorktree -v`
Expected: FAIL (currently crashes with FileNotFoundError)

**Step 3: Write minimal implementation**

Modify `src/codogram/handlers/finish.py` around line 70-80:

```python
# Before has_uncommitted_changes check, add stale detection:
if thread.worktree_path and not Path(thread.worktree_path).exists():
    # Stale worktree - warn and skip git operations
    relative_path = Path(thread.worktree_path).relative_to(Path(project.cwd))
    await self.queue.enqueue(
        chat_id=message.chat.id,
        text=f"`[!]` Worktree not found: `{relative_path}`\n\nArchiving topic without git cleanup.",
        message_thread_id=thread_id,
    )
    # Skip to archive
    await archive_thread(...)
    return
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/handlers/test_finish.py::TestFinishStaleWorktree -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/finish.py tests/unit/handlers/test_finish.py
git commit -m "fix: handle stale worktree in /finish without crashing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add stale worktree detection to /start in topic

**Files:**
- Modify: `src/codogram/handlers/start.py`
- Test: `tests/unit/handlers/test_start.py`

**Step 1: Write the failing test**

Add to `tests/unit/handlers/test_start.py`:

```python
class TestStartStaleWorktree:
    @pytest.mark.asyncio
    async def test_start_with_stale_worktree_and_branch_shows_recovery(self, start_handler, mock_message, mock_queue):
        """Start in topic with stale worktree but branch exists shows recovery options."""
        from codogram.session_manager import ThreadInfo
        from codogram.domain.worktree_state import WorktreeState

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        with patch.object(start_handler.project_manager, "get_thread", return_value=thread):
            with patch("codogram.handlers.start.get_worktree_state", return_value=WorktreeState.MISSING_WITH_BRANCH):
                with patch("codogram.handlers.start.worktree_recovery_keyboard") as mock_kb:
                    mock_kb.return_value = MagicMock()
                    await start_handler.handle_start(mock_message, None)

        # Should show recovery message with keyboard
        call_args = mock_queue.enqueue.call_args_list
        assert any("[!]" in str(call) for call in call_args)
        mock_kb.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_with_stale_worktree_no_branch_shows_create_new(self, start_handler, mock_message, mock_queue):
        """Start in topic with stale worktree and no branch shows create new option."""
        from codogram.session_manager import ThreadInfo
        from codogram.domain.worktree_state import WorktreeState

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        with patch.object(start_handler.project_manager, "get_thread", return_value=thread):
            with patch("codogram.handlers.start.get_worktree_state", return_value=WorktreeState.MISSING_NO_BRANCH):
                with patch("codogram.handlers.start.worktree_recovery_keyboard") as mock_kb:
                    mock_kb.return_value = MagicMock()
                    await start_handler.handle_start(mock_message, None)

        mock_kb.assert_called_once_with(thread_id=123, state=WorktreeState.MISSING_NO_BRANCH)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/handlers/test_start.py::TestStartStaleWorktree -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `src/codogram/handlers/start.py`, add stale detection early in topic handling:

```python
from codogram.domain.worktree_state import WorktreeState, get_worktree_state
from codogram.keyboards.keyboards import worktree_recovery_keyboard

# In handle_start, after getting thread for topic:
if thread and thread.worktree_path:
    state = get_worktree_state(thread, Path(project.cwd))
    if state != WorktreeState.OK:
        # Show recovery options
        relative_path = Path(thread.worktree_path).relative_to(Path(project.cwd))
        if state == WorktreeState.MISSING_WITH_BRANCH:
            text = (
                f"`[!]` Worktree not found: `{relative_path}`\n\n"
                f"Branch `{thread.name}` exists.\n\n"
                "• Recreate worktree — recreate folder and resume session\n"
                "• Resume in main — archive topic, continue in main\n"
                "• Cancel"
            )
        else:
            text = (
                f"`[!]` Worktree not found: `{relative_path}`\n\n"
                f"Branch `{thread.name}` not found (merged?).\n\n"
                "• Create new — create branch + worktree, resume session\n"
                "• Resume in main — archive topic, continue in main\n"
                "• Cancel"
            )

        await self.queue.enqueue(
            chat_id=message.chat.id,
            text=text,
            message_thread_id=thread.thread_id,
            reply_markup=worktree_recovery_keyboard(thread.thread_id, state),
        )
        return
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/handlers/test_start.py::TestStartStaleWorktree -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/start.py tests/unit/handlers/test_start.py
git commit -m "feat: add stale worktree detection to /start in topic

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add create_worktree and create_branch_with_worktree helpers

**Files:**
- Modify: `src/codogram/services/branch.py`
- Test: `tests/unit/services/test_branch.py`

**Step 1: Write the failing test**

Add to `tests/unit/services/test_branch.py`:

```python
class TestWorktreeHelpers:
    def test_create_worktree_from_existing_branch(self, tmp_path):
        """Create worktree when branch already exists."""
        from codogram.services.branch import create_worktree

        # Setup git repo with branch
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", "my-feature"], cwd=tmp_path, check=True)

        success, path = create_worktree(tmp_path, "my-feature")

        assert success
        assert Path(path).exists()
        assert "my-feature" in path

    def test_create_branch_with_worktree(self, tmp_path):
        """Create new branch and worktree from scratch."""
        from codogram.services.branch import create_branch_with_worktree

        # Setup git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)

        success, path = create_branch_with_worktree(tmp_path, "new-feature")

        assert success
        assert Path(path).exists()
        assert "new-feature" in path
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_branch.py::TestWorktreeHelpers -v`
Expected: FAIL with "cannot import name 'create_worktree'"

**Step 3: Write minimal implementation**

Add to `src/codogram/services/branch.py`:

```python
def create_worktree(project_cwd: Path, branch_name: str) -> tuple[bool, str]:
    """Create worktree for existing branch.

    Returns (success, path_or_error).
    """
    worktree_path = project_cwd / ".worktrees" / branch_name

    try:
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            cwd=project_cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, str(worktree_path)
    except Exception as e:
        return False, str(e)


def create_branch_with_worktree(project_cwd: Path, branch_name: str) -> tuple[bool, str]:
    """Create new branch and worktree.

    Returns (success, path_or_error).
    """
    worktree_path = project_cwd / ".worktrees" / branch_name

    try:
        # Create worktree with new branch
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=project_cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, str(worktree_path)
    except Exception as e:
        return False, str(e)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_branch.py::TestWorktreeHelpers -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/branch.py tests/unit/services/test_branch.py
git commit -m "feat: add create_worktree and create_branch_with_worktree helpers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create worktree recovery handler module

**Files:**
- Create: `src/codogram/handlers/worktree_recovery.py`
- Create: `tests/unit/handlers/test_worktree_recovery.py`

**Step 1: Write the failing tests**

```python
# tests/unit/handlers/test_worktree_recovery.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from codogram.handlers.worktree_recovery import WorktreeRecoveryHandler
from codogram.session_manager import ThreadInfo


@pytest.fixture
def recovery_handler():
    handler = WorktreeRecoveryHandler(
        project_manager=MagicMock(),
        queue=MagicMock(),
        bot=MagicMock(),
    )
    return handler


@pytest.fixture
def mock_callback():
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.chat.id = 123
    return callback


class TestWorktreeRecoveryCallbacks:
    @pytest.mark.asyncio
    async def test_wr_recreate_recreates_worktree(self, recovery_handler, mock_callback):
        """wr_recreate callback recreates worktree and starts Claude."""
        mock_callback.data = "wr_recreate:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_worktree") as mock_create:
            mock_create.return_value = (True, "/repo/.worktrees/my-feature")
            with patch.object(recovery_handler, "_start_claude_session", new_callable=AsyncMock):
                await recovery_handler.handle_wr_recreate(mock_callback)

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_create_creates_branch_and_worktree(self, recovery_handler, mock_callback):
        """wr_create callback creates new branch and worktree."""
        mock_callback.data = "wr_create:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_branch_with_worktree") as mock_create:
            mock_create.return_value = (True, "/repo/.worktrees/my-feature")
            with patch.object(recovery_handler, "_start_claude_session", new_callable=AsyncMock):
                await recovery_handler.handle_wr_create(mock_callback)

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_main_archives_topic(self, recovery_handler, mock_callback):
        """wr_main callback archives topic."""
        mock_callback.data = "wr_main:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread

        with patch("codogram.handlers.worktree_recovery.archive_thread", new_callable=AsyncMock) as mock_archive:
            mock_archive.return_value = True
            await recovery_handler.handle_wr_main(mock_callback)

        mock_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_cancel_deletes_message(self, recovery_handler, mock_callback):
        """wr_cancel callback just deletes the message."""
        mock_callback.data = "wr_cancel:123"

        await recovery_handler.handle_wr_cancel(mock_callback)

        mock_callback.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_recreate_shows_error_on_failure(self, recovery_handler, mock_callback):
        """wr_recreate shows error message with options on failure."""
        mock_callback.data = "wr_recreate:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_worktree") as mock_create:
            mock_create.return_value = (False, "branch already checked out")
            await recovery_handler.handle_wr_recreate(mock_callback)

        # Should show error with options
        call_args = mock_callback.message.edit_text.call_args
        text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        assert "[x]" in text
        assert "/finish" in text
        assert "/thread" in text
        assert "/branch" in text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/handlers/test_worktree_recovery.py -v`
Expected: FAIL with "No module named 'codogram.handlers.worktree_recovery'"

**Step 3: Write minimal implementation**

```python
# src/codogram/handlers/worktree_recovery.py
"""Worktree recovery callbacks for stale worktree handling."""
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from codogram.services.branch import archive_thread, create_worktree, create_branch_with_worktree
from codogram.session_manager import ProjectManager
from codogram.telegram_queue import TelegramQueue


class WorktreeRecoveryHandler:
    """Handle worktree recovery callbacks."""

    def __init__(self, project_manager: ProjectManager, queue: TelegramQueue, bot: Bot):
        self.project_manager = project_manager
        self.queue = queue
        self.bot = bot

    async def handle_wr_recreate(self, callback: CallbackQuery) -> None:
        """Recreate worktree from existing branch."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        project = self.project_manager.get_project()
        success, path = create_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager.save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await callback.message.edit_text(
                f"`[x]` Failed to recreate worktree: {path}\n\n"
                "What to do:\n"
                "• /finish — archive this topic\n"
                "• /thread — create new topic in main\n"
                "• /branch — create new worktree branch"
            )

    async def handle_wr_create(self, callback: CallbackQuery) -> None:
        """Create new branch and worktree."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        project = self.project_manager.get_project()
        success, path = create_branch_with_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager.save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await callback.message.edit_text(
                f"`[x]` Failed to create branch: {path}\n\n"
                "What to do:\n"
                "• /finish — archive this topic\n"
                "• /thread — create new topic in main\n"
                "• /branch — create new worktree branch"
            )

    async def handle_wr_main(self, callback: CallbackQuery) -> None:
        """Resume in main by archiving topic."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        success = await archive_thread(callback.message.chat.id, thread_id, self.bot)
        if success:
            await callback.message.edit_text(
                "`[v]` Topic archived\n\n"
                "Use General or /thread for new session."
            )
        else:
            await callback.message.edit_text("`[x]` Failed to archive topic")

    async def handle_wr_cancel(self, callback: CallbackQuery) -> None:
        """Cancel recovery - just delete message."""
        await callback.answer()
        await callback.message.delete()

    async def _start_claude_session(self, message, thread) -> None:
        """Start Claude session in recovered worktree.

        Note: This delegates to StartHandler._start_claude_session.
        Implemented during integration.
        """
        # Will be connected during router setup
        pass


def register_worktree_recovery_handlers(router: Router, handler: WorktreeRecoveryHandler) -> None:
    """Register worktree recovery callback handlers."""
    router.callback_query.register(handler.handle_wr_recreate, F.data.startswith("wr_recreate:"))
    router.callback_query.register(handler.handle_wr_create, F.data.startswith("wr_create:"))
    router.callback_query.register(handler.handle_wr_main, F.data.startswith("wr_main:"))
    router.callback_query.register(handler.handle_wr_cancel, F.data.startswith("wr_cancel:"))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/handlers/test_worktree_recovery.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/worktree_recovery.py tests/unit/handlers/test_worktree_recovery.py
git commit -m "feat: add worktree recovery handler module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Register worktree recovery handler in main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Add import and handler setup**

In `src/codogram/main.py`, add:

```python
from codogram.handlers.worktree_recovery import WorktreeRecoveryHandler, register_worktree_recovery_handlers

# In setup_handlers() or similar:
worktree_recovery_handler = WorktreeRecoveryHandler(
    project_manager=project_manager,
    queue=queue,
    bot=bot,
)
register_worktree_recovery_handlers(router, worktree_recovery_handler)
```

**Step 2: Connect _start_claude_session**

The `WorktreeRecoveryHandler._start_claude_session` needs to delegate to `StartHandler._start_claude_session`. Add connection:

```python
# After creating both handlers:
worktree_recovery_handler._start_claude_session = start_handler._start_claude_session
```

**Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat: register worktree recovery handler

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add stale worktree detection to /branch

**Files:**
- Modify: `src/codogram/handlers/branches.py`
- Test: `tests/unit/handlers/test_branches.py`

**Step 1: Write the failing test**

Add to `tests/unit/handlers/test_branches.py`:

```python
class TestBranchStaleWorktree:
    @pytest.mark.asyncio
    async def test_branch_with_stale_worktree_shows_warning_and_continues_flow(self, branch_handler, mock_message, mock_queue):
        """Branch from topic with stale worktree warns and continues with name prompt."""
        from codogram.session_manager import ThreadInfo

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="old-feature",
            worktree_path="/nonexistent/path"
        )

        with patch.object(branch_handler.project_manager, "get_thread", return_value=thread):
            # Call without name argument to trigger name prompt
            await branch_handler.handle_branch(mock_message, None)

        # Should show warning about stale worktree
        call_args = mock_queue.enqueue.call_args_list
        warning_shown = any("[!]" in str(call) and "main" in str(call).lower() for call in call_args)
        assert warning_shown, "Should show warning about stale worktree"

        # Should show name prompt with Magic name button (normal flow continues)
        name_prompt_shown = any("name" in str(call).lower() for call in call_args)
        assert name_prompt_shown, "Should show branch name prompt after warning"

    @pytest.mark.asyncio
    async def test_branch_with_stale_worktree_uses_main_as_base(self, branch_handler, mock_message, mock_queue):
        """Branch from topic with stale worktree uses main as base branch."""
        from codogram.session_manager import ThreadInfo

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="old-feature",
            worktree_path="/nonexistent/path"
        )

        with patch.object(branch_handler.project_manager, "get_thread", return_value=thread):
            with patch.object(branch_handler, "_create_branch_worktree") as mock_create:
                # Call with name to skip prompt and go to creation
                await branch_handler.handle_branch(mock_message, "new-feature")

        # Should use main as base branch (not old-feature)
        if mock_create.called:
            call_args = mock_create.call_args
            # Verify base_branch is "main" not "old-feature"
            assert "main" in str(call_args) or thread.name not in str(call_args)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/handlers/test_branches.py::TestBranchStaleWorktree -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `src/codogram/handlers/branches.py` to detect stale worktree:

```python
# When determining base branch for new worktree:
if thread and thread.worktree_path:
    if not Path(thread.worktree_path).exists():
        # Stale worktree - warn and use main
        await self.queue.enqueue(
            chat_id=message.chat.id,
            text="`[!]` Worktree not found, using main as base",
            message_thread_id=thread.thread_id,
        )
        base_branch = "main"  # fallback
    else:
        base_branch = thread.name
# Then continue with normal /branch flow (name prompt or creation)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/handlers/test_branches.py::TestBranchStaleWorktree -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/branches.py tests/unit/handlers/test_branches.py
git commit -m "fix: /branch falls back to main when worktree is stale

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Run full test suite and verify

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (319+ tests)

**Step 2: Manual E2E test with Telegram MCP**

Test scenarios:
1. `/finish` in topic with deleted worktree - should show warning and archive
2. `/start` in topic with deleted worktree but branch exists - should show recreate option
3. `/start` in topic with deleted worktree and deleted branch - should show create new option
4. Click "Resume in main" - should archive topic
5. `/branch` from topic with stale worktree - should warn and use main

**Step 3: Commit any fixes**

If any tests fail, fix and commit.

---

## Task 10: Update documentation

**Files:**
- Move: `docs/designs/2026-01-12-stale-worktree-recovery.md` → `docs/designs/done/`
- Move: `docs/bugs/active/2026-01-12-stale-worktree-path-crash.md` → `docs/bugs/fixed/`
- Update: `docs/ROADMAP.md` - move to Done section
- Update: `docs/ROADMAP.ru.md` - move to Done section

**Step 1: Move design doc**

```bash
mv docs/designs/2026-01-12-stale-worktree-recovery.md docs/designs/done/
```

**Step 2: Move bug report**

```bash
mv docs/bugs/active/2026-01-12-stale-worktree-path-crash.md docs/bugs/fixed/
```

**Step 3: Update ROADMAP.md**

Move "Stale worktree recovery" section from Backlog to Done.

**Step 4: Update ROADMAP.ru.md**

Move "Stale worktree recovery" section from Backlog to Done.

**Step 5: Commit**

```bash
git add docs/
git commit -m "docs: mark stale worktree recovery as done

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
