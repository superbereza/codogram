# Session Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ability to resume previous Claude session using `--resume` flag when thread has stored `session_id`.

**Architecture:** Modify `launch_with_animation` to accept `session_id` and `cwd` params, update `/start` flow to check session existence before launch, add callback handlers for error recovery.

**Tech Stack:** Python 3.11, aiogram 3.x, tmux

**Prerequisites:** menu-redesign plan (for archived topic handling)

---

## Task 1: Add session_id and cwd Parameters to launch_with_animation

**Files:**
- Modify: `src/codogram/launch_animation.py:63-70`
- Test: `tests/test_launch_animation.py`

**Step 1: Write the failing test**

Add to `tests/test_launch_animation.py`:

```python
"""Tests for launch_with_animation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.cwd = "/home/user/project"
    project.project_name = "test-project"
    return project


@pytest.fixture
def mock_thread():
    thread = MagicMock()
    thread.name = "feature-x"
    thread.worktree_path = "/home/user/project/.worktrees/feature-x"
    thread.session_id = "abc-123-def"
    thread.awaiting_new_session = False
    thread.start_requested_at = None
    thread.launch_task = None
    thread.poller_task = None
    thread.get_tmux_session = MagicMock(return_value="test-project-feature-x")
    return thread


@pytest.mark.asyncio
async def test_launch_with_session_id_uses_resume_flag(mock_project, mock_thread):
    """When session_id provided, should use 'claude --resume {id}'."""
    from codogram.launch_animation import launch_with_animation

    bot = AsyncMock()
    queue = AsyncMock()
    queue.send = AsyncMock(return_value=[123])

    with patch("codogram.launch_animation.TmuxSession") as MockTmux, \
         patch("codogram.launch_animation.project_manager"), \
         patch("codogram.launch_animation._start_monitoring"):

        mock_tmux = MagicMock()
        mock_tmux.exists.return_value = False
        mock_tmux.is_claude_ready.return_value = True  # Skip wait loop
        MockTmux.return_value = mock_tmux

        await launch_with_animation(
            bot=bot,
            chat_id=-100123,
            thread_id=456,
            project=mock_project,
            thread=mock_thread,
            queue=queue,
            session_id="abc-123-def",  # NEW param
        )

        # Should send "claude --resume abc-123-def"
        mock_tmux.send.assert_called_with("claude --resume abc-123-def")


@pytest.mark.asyncio
async def test_launch_with_cwd_uses_custom_directory(mock_project, mock_thread):
    """When cwd provided, TmuxSession should use that cwd."""
    from codogram.launch_animation import launch_with_animation

    bot = AsyncMock()
    queue = AsyncMock()
    queue.send = AsyncMock(return_value=[123])

    with patch("codogram.launch_animation.TmuxSession") as MockTmux, \
         patch("codogram.launch_animation.project_manager"), \
         patch("codogram.launch_animation._start_monitoring"):

        mock_tmux = MagicMock()
        mock_tmux.exists.return_value = False
        mock_tmux.is_claude_ready.return_value = True
        MockTmux.return_value = mock_tmux

        await launch_with_animation(
            bot=bot,
            chat_id=-100123,
            thread_id=456,
            project=mock_project,
            thread=mock_thread,
            queue=queue,
            cwd="/home/user/project/.worktrees/feature-x",  # NEW param
        )

        # TmuxSession should be created with custom cwd
        MockTmux.assert_called_with(
            "test-project-feature-x",
            "/home/user/project/.worktrees/feature-x"
        )
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_launch_animation.py::test_launch_with_session_id_uses_resume_flag -v`
Expected: FAIL - `session_id` parameter doesn't exist

**Step 3: Add parameters to launch_with_animation**

Modify `src/codogram/launch_animation.py`:

```python
async def launch_with_animation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
    session_id: str | None = None,  # NEW: for --resume
    cwd: str | None = None,         # NEW: override for branches
) -> bool:
    """Launch Claude with animated status messages.

    Args:
        bot: Telegram bot instance
        chat_id: Telegram chat ID
        thread_id: Telegram thread ID (for topics)
        project: Project state
        thread: Thread info
        queue: Telegram message queue
        session_id: If provided, resume with `claude --resume {session_id}`
        cwd: Override working directory (for branches with worktrees)
    """
    # Use provided cwd or default to project.cwd
    actual_cwd = cwd or project.cwd

    if not actual_cwd:
        await queue.send(
            chat_id,
            "`[x]` Project cwd not set. Re-register with /start",
            thread_id=thread_id,
            parse_mode="MarkdownV2",
        )
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, actual_cwd)  # Use actual_cwd

    try:
        thread.awaiting_new_session = True
        thread.start_requested_at = time.time()

        # 1. Create tmux
        await queue.send(chat_id, "`[~]` Creating tmux session...", thread_id=thread_id, parse_mode="MarkdownV2")

        if not tmux.exists():
            tmux.create()

        # 2. Launch Claude (with or without resume)
        if session_id:
            await queue.send(chat_id, "`[~]` Resuming session...", thread_id=thread_id, parse_mode="MarkdownV2")
            tmux.send(f"claude --resume {session_id}")
        else:
            await queue.send(chat_id, "`[~]` Starting Claude...", thread_id=thread_id, parse_mode="MarkdownV2")
            tmux.send("claude")

        # ... rest of the function unchanged ...
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_launch_animation.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/launch_animation.py tests/test_launch_animation.py
git commit -m "feat(launch): add session_id and cwd params for resume"
```

---

## Task 2: Add jsonl_path Existence Check Helper

**Files:**
- Modify: `src/codogram/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_thread_has_valid_session():
    """ThreadInfo.has_valid_session checks jsonl exists."""
    from codogram.session_manager import ThreadInfo
    from pathlib import Path
    import tempfile
    import os

    # No session_id
    thread = ThreadInfo(name="test", thread_id=123)
    assert thread.has_valid_session() is False

    # session_id but no jsonl_path
    thread.session_id = "abc-123"
    assert thread.has_valid_session() is False

    # session_id and jsonl_path but file doesn't exist
    thread.jsonl_path = "/nonexistent/path.jsonl"
    assert thread.has_valid_session() is False

    # session_id and jsonl_path and file exists
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        try:
            thread.jsonl_path = f.name
            assert thread.has_valid_session() is True
        finally:
            os.unlink(f.name)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_has_valid_session -v`
Expected: FAIL - `has_valid_session` method doesn't exist

**Step 3: Add has_valid_session method to ThreadInfo**

Add to `ThreadInfo` class in `src/codogram/session_manager.py`:

```python
def has_valid_session(self) -> bool:
    """Check if thread has a valid resumable session.

    Returns True only if:
    - session_id is set
    - jsonl_path is set
    - jsonl file exists on disk
    """
    if not self.session_id or not self.jsonl_path:
        return False
    return Path(self.jsonl_path).exists()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_has_valid_session -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add has_valid_session method to ThreadInfo"
```

---

## Task 3: Add Worktree Existence Check Helper

**Files:**
- Modify: `src/codogram/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
def test_thread_has_valid_worktree():
    """ThreadInfo.has_valid_worktree checks worktree exists."""
    from codogram.session_manager import ThreadInfo
    import tempfile
    import os

    # No worktree_path
    thread = ThreadInfo(name="test", thread_id=123)
    assert thread.has_valid_worktree() is False

    # worktree_path but doesn't exist
    thread.worktree_path = "/nonexistent/worktree"
    assert thread.has_valid_worktree() is False

    # worktree_path exists
    with tempfile.TemporaryDirectory() as tmpdir:
        thread.worktree_path = tmpdir
        assert thread.has_valid_worktree() is True
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_has_valid_worktree -v`
Expected: FAIL

**Step 3: Add has_valid_worktree method**

```python
def has_valid_worktree(self) -> bool:
    """Check if thread has a valid worktree directory.

    Returns True only if worktree_path is set and directory exists.
    """
    if not self.worktree_path:
        return False
    return Path(self.worktree_path).is_dir()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_session_manager.py::test_thread_has_valid_worktree -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add has_valid_worktree method to ThreadInfo"
```

---

## Task 4: Update /start Handler to Check Tmux Running First

**Files:**
- Modify: `src/codogram/handlers/start.py`
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Read current StartFlowService to understand structure**

The key is to check if tmux is already running BEFORE any launch logic.

**Step 2: Add import for is_tmux_session_exists at top of start.py**

Add near other imports at top of `src/codogram/handlers/start.py`:

```python
from ..project_launcher import is_tmux_session_exists
```

**Step 3: Add tmux check at the beginning of thread flow**

In `_launch_claude_in_thread` (start.py:231), add check:

```python
async def _launch_claude_in_thread(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Launch Claude in a specific thread."""
    from ..launch_animation import launch_with_animation

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    # Check if tmux already running
    tmux_name = thread.get_tmux_session(project.project_name)
    actual_cwd = thread.worktree_path or project.cwd
    if is_tmux_session_exists(tmux_name):
        # Check if Claude is ready in tmux
        from ..tmux import TmuxSession
        tmux = TmuxSession(tmux_name, actual_cwd)
        if tmux.is_claude_ready():
            await telegram_queue.reply(
                message,
                f"`[v]` Already running\n\nAttach: `tmux attach -t {tmux_name}`"
            )
            return
        else:
            # tmux exists but Claude not ready - kill and restart
            import subprocess
            subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # ... rest unchanged
```

**Step 4: Verify changes**

Run: `python -m py_compile src/codogram/handlers/start.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(start): check tmux running before launch"
```

---

## Task 5: Implement Resume Logic in /start Handler

**Files:**
- Modify: `src/codogram/handlers/start.py:231-255`
- Test: `tests/test_start_resume.py`

**Step 1: Write the failing test**

Create `tests/test_start_resume.py`:

```python
"""Tests for /start resume logic."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_start_resumes_when_session_valid():
    """When thread has valid session, /start should resume."""
    from codogram.handlers.start import _launch_claude_in_thread
    from codogram.services.start_flow import FlowResult, FlowAction

    # Setup mocks
    message = MagicMock()
    message.chat.id = -100123
    message.bot = AsyncMock()

    queue = AsyncMock()
    queue.send = AsyncMock(return_value=[123])

    result = FlowResult(action=FlowAction.THREAD_LAUNCH, thread_id=456)

    mock_thread = MagicMock()
    mock_thread.name = "feature-x"
    mock_thread.session_id = "abc-123"
    mock_thread.jsonl_path = "/tmp/test.jsonl"
    mock_thread.worktree_path = "/tmp/worktree"
    mock_thread.has_valid_session = MagicMock(return_value=True)
    mock_thread.has_valid_worktree = MagicMock(return_value=True)
    mock_thread.launch_task = None
    mock_thread.get_tmux_session = MagicMock(return_value="proj-feature-x")

    mock_project = MagicMock()
    mock_project.cwd = "/tmp/project"
    mock_project.project_name = "proj"
    mock_project.threads = {456: mock_thread}

    with patch("codogram.handlers.start.project_manager") as mock_pm, \
         patch("codogram.handlers.start.is_tmux_session_exists", return_value=False), \
         patch("codogram.handlers.start.launch_with_animation") as mock_launch:

        mock_pm.get_by_chat.return_value = mock_project

        await _launch_claude_in_thread(message, result, queue)

        # Should call launch_with_animation with session_id and cwd
        mock_launch.assert_called_once()
        call_kwargs = mock_launch.call_args[1]
        assert call_kwargs.get("session_id") == "abc-123"
        assert call_kwargs.get("cwd") == "/tmp/worktree"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_start_resume.py -v`
Expected: FAIL

**Step 3: Implement resume logic in _launch_claude_in_thread**

Update `src/codogram/handlers/start.py`:

```python
async def _launch_claude_in_thread(message: Message, result: FlowResult, telegram_queue: TelegramQueue):
    """Launch Claude in a specific thread."""
    from ..launch_animation import launch_with_animation
    from ..project_launcher import is_tmux_session_exists

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    # Check if tmux already running
    tmux_name = thread.get_tmux_session(project.project_name)
    if is_tmux_session_exists(tmux_name):
        from ..tmux import TmuxSession
        actual_cwd = thread.worktree_path or project.cwd
        tmux = TmuxSession(tmux_name, actual_cwd)
        if tmux.is_claude_ready():
            await telegram_queue.reply(
                message,
                f"`[v]` Already running\n\nAttach: `tmux attach -t {tmux_name}`"
            )
            return
        else:
            import subprocess
            subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    if thread.launch_task and not thread.launch_task.done():
        return

    # Handle archived topic - reopen it (already implemented in menu-redesign)
    if thread.archived:
        thread.archived = False
        project_manager._save()
        try:
            await message.bot.edit_forum_topic(
                message.chat.id, result.thread_id, icon_custom_emoji_id=""
            )
        except Exception:
            pass  # May fail if no icon was set

    # Determine cwd (worktree or project)
    cwd = thread.worktree_path if thread.has_valid_worktree() else None

    # Check for session resume
    session_id = None
    if thread.has_valid_session():
        session_id = thread.session_id
    elif thread.session_id and not thread.has_valid_session():
        # Session ID exists but jsonl missing - show error
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Start new session",
                callback_data=f"resume:start_new:{result.thread_id}"
            )],
            [InlineKeyboardButton(text="Cancel", callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await telegram_queue.reply(
            message,
            "`[!]` Previous session not found",
            reply_markup=keyboard,
        )
        return

    # Check worktree exists for branch topics
    if thread.worktree_path and not thread.has_valid_worktree():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Recreate worktree",
                callback_data=f"resume:recreate:{result.thread_id}"
            )],
            [InlineKeyboardButton(text="Cancel", callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await telegram_queue.reply(
            message,
            f"`[!]` Worktree not found: `{thread.worktree_path}`",
            reply_markup=keyboard,
        )
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=result.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
            session_id=session_id,  # Pass session_id for resume
            cwd=cwd,                # Pass worktree cwd for branches
        )
    )
```

**Step 4: Add import for InlineKeyboardMarkup**

Add at top of start.py:
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
```

**Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_start_resume.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/handlers/start.py tests/test_start_resume.py
git commit -m "feat(start): implement session resume logic"
```

---

## Task 6: Add Resume Callback Handlers

**Files:**
- Modify: `src/codogram/handlers/start.py` (add callbacks)

**Step 1: Add callback handler for resume:start_new**

Add to `src/codogram/handlers/start.py`:

```python
@router.callback_query(F.data.startswith("resume:"))
async def on_resume_callback(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle resume error recovery callbacks."""
    parts = callback.data.split(":")
    action = parts[1]
    thread_id = int(parts[2]) if parts[2] != "None" else None

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id) if thread_id else None

    if action == "start_new":
        # Clear stale session and start fresh
        if thread:
            thread.session_id = None
            thread.jsonl_path = None
            project_manager._save()

        await telegram_queue.edit(callback.message, "`[~]` Starting new session...")
        await callback.answer()

        # Trigger launch
        from ..launch_animation import launch_with_animation
        cwd = thread.worktree_path if thread and thread.has_valid_worktree() else None

        if thread:
            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot,
                    chat_id=callback.message.chat.id,
                    thread_id=thread_id,
                    project=project,
                    thread=thread,
                    queue=telegram_queue,
                    cwd=cwd,
                )
            )

    elif action == "recreate":
        # Recreate worktree from existing branch
        if not thread:
            await callback.answer("Thread not found")
            return

        await telegram_queue.edit(callback.message, "`[~]` Recreating worktree...")
        await callback.answer()

        # Attach worktree to existing branch (not create new!)
        from pathlib import Path
        import subprocess

        main_repo = Path(project.cwd)
        branch_name = thread.name
        worktree_path = main_repo / ".worktrees" / branch_name

        try:
            # Ensure .worktrees/ directory exists
            worktree_path.parent.mkdir(parents=True, exist_ok=True)

            # git worktree add <path> <existing-branch>
            # Use asyncio.to_thread to avoid blocking event loop
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=str(main_repo),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

            thread.worktree_path = str(worktree_path)
            project_manager._save()

            await telegram_queue.edit(callback.message, "`[v]` Worktree recreated. Use /start to launch.")
        except Exception as e:
            await telegram_queue.edit(callback.message, f"`[x]` Failed to recreate: {e}")

    elif action == "cancel":
        await telegram_queue.edit(callback.message, "Cancelled.")
        await callback.answer()
```

**Step 2: Verify changes**

Run: `python -m py_compile src/codogram/handlers/start.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(start): add resume error recovery callbacks"
```

---

## Task 7: Update Worktree Path to Use .worktrees/ Directory

**Files:**
- Modify: `src/codogram/services/launch.py`
- Test: Check worktree creation path

**Note:** Existing worktrees use the old path format (`{repo}-{branch}` next to repo). The resume logic (Task 5) uses `thread.worktree_path` from config, so existing worktrees will continue to work. Only NEW branches will use `.worktrees/` format.

**Step 1: Find worktree path creation**

Search for where worktree_path is set when creating branches.

**Step 2: Update to use .worktrees/ subdirectory**

In `src/codogram/services/launch.py` or `services/branch.py`, change:

```python
# Old: worktree next to main repo
worktree_path = main_repo.parent / f"{main_repo.name}-{branch_name}"

# New: worktree inside .worktrees/
worktree_path = main_repo / ".worktrees" / branch_name

# Ensure .worktrees/ directory exists before creating worktree
worktree_path.parent.mkdir(parents=True, exist_ok=True)
```

**Step 3: Ensure .worktrees/ is in .gitignore**

Check/add to project's .gitignore:
```
.worktrees/
```

**Step 4: Verify changes**

Run: `python -m py_compile src/codogram/services/launch.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add src/codogram/services/launch.py
git commit -m "feat(worktree): use .worktrees/ subdirectory for branches"
```

---

## Task 8: Integration Test - Session Resume

**Files:**
- Test with Telegram MCP

**Step 1: Restart bot**

Run: `./restart.sh`

**Step 2: Create branch topic and get session**

1. Send `/branch test-resume`
2. Wait for Claude to start
3. Send a message to establish session
4. Note session_id in .config.json

**Step 3: Archive branch (simulate /finish)**

Send `/finish` and merge/archive the branch.

**Step 4: Test resume**

1. Manually reopen archived topic in Telegram
2. Send `/start`
3. Verify:
   - Session resumes with same context
   - Shows "Resuming session..." message
   - Worktree is used for cwd

**Step 5: Test error cases**

1. Delete jsonl file manually
2. Send `/start`
3. Verify "Previous session not found" error with "Start new" button

**Step 6: Commit**

```bash
git add -A
git commit -m "test: verify session-resume integration"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add session_id, cwd params to launch_animation | launch_animation.py |
| 2 | Add has_valid_session helper | session_manager.py |
| 3 | Add has_valid_worktree helper | session_manager.py |
| 4 | Check tmux running before launch | start.py |
| 5 | Implement resume logic in /start | start.py |
| 6 | Add resume callback handlers | start.py |
| 7 | Use .worktrees/ for worktree paths | services/launch.py |
| 8 | Integration test | - |

**Prerequisites:** menu-redesign plan (Task 7 for archived handling)

**Depends on:** cleanup-command plan (for explicit deletion)
