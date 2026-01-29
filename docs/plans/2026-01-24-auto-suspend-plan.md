# Auto-Suspend & Auto-Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-suspend idle Claude sessions after 12h to save RAM, auto-resume when user sends message

**Architecture:** Activity tracking via `last_activity_at` field, suspend check in coordinator loop, resume flow in message router with pending action queue

**Tech Stack:** Python asyncio, aiogram, tmux subprocess

---

## Task 1: Add PendingAction dataclass

**Files:**
- Modify: `src/codogram/domain/models.py`
- Test: `tests/domain/test_pending_action.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/domain/test_pending_action.py
"""Tests for PendingAction model."""
import pytest
from codogram.domain.models import PendingAction


def test_pending_action_message():
    """PendingAction stores message type correctly."""
    action = PendingAction(type="message", text="hello world")
    assert action.type == "message"
    assert action.text == "hello world"


def test_pending_action_command():
    """PendingAction stores command type correctly."""
    action = PendingAction(type="command", text="/help")
    assert action.type == "command"
    assert action.text == "/help"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/domain/test_pending_action.py -v`

Expected: FAIL with "cannot import name 'PendingAction'"

**Step 3: Write implementation**

Add to `src/codogram/domain/models.py`:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class PendingAction:
    """Pending action to execute after resume."""
    type: Literal["message", "command"]
    text: str
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/domain/test_pending_action.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/domain/test_pending_action.py src/codogram/domain/models.py
git commit -m "$(cat <<'EOF'
feat(domain): add PendingAction dataclass for auto-resume

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add new ThreadInfo fields

**Files:**
- Modify: `src/codogram/core/session_manager.py`
- Test: `tests/test_session_manager.py` (add to existing)

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_thread_info_suspend_fields():
    """ThreadInfo has suspend/resume fields."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=None, name="main")

    # Default values
    assert thread.last_activity_at is None
    assert thread.suspended is False
    assert thread.resuming is False
    assert thread.pending_action is None


def test_thread_info_suspend_fields_persist():
    """Persisted fields are saved and loaded."""
    from codogram.core.session_manager import ThreadInfo
    from codogram.domain.models import PendingAction
    import time

    thread = ThreadInfo(thread_id=None, name="main")
    thread.last_activity_at = time.time()
    thread.suspended = True

    # These should be persisted
    assert thread.last_activity_at is not None
    assert thread.suspended is True

    # These are runtime-only
    assert thread.resuming is False
    assert thread.pending_action is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_session_manager.py::test_thread_info_suspend_fields tests/test_session_manager.py::test_thread_info_suspend_fields_persist -v`

Expected: FAIL with "has no attribute 'last_activity_at'"

**Step 3: Write implementation**

Modify `ThreadInfo` in `src/codogram/core/session_manager.py`:

```python
# Add import at top
from ..domain.models import PendingAction

# Add to ThreadInfo dataclass (after response_mode field):
    # Auto-suspend/resume:
    last_activity_at: float | None = None  # Persisted - last user interaction
    suspended: bool = False                 # Persisted - session was suspended

    # Runtime-only (not persisted):
    resuming: bool = False                  # Resume in progress
    pending_action: PendingAction | None = None  # Held action during resume
```

Update `_load_projects` to load new fields:

```python
# In threads loading section, add:
last_activity_at=thread_data.get("last_activity_at"),
suspended=thread_data.get("suspended", False),
```

Update `_save` to persist new fields:

```python
# In thread_data building, add:
if t.last_activity_at:
    thread_data["last_activity_at"] = t.last_activity_at
if t.suspended:
    thread_data["suspended"] = t.suspended
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_session_manager.py::test_thread_info_suspend_fields tests/test_session_manager.py::test_thread_info_suspend_fields_persist -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/core/session_manager.py src/codogram/domain/models.py tests/test_session_manager.py
git commit -m "$(cat <<'EOF'
feat(session): add last_activity_at, suspended fields to ThreadInfo

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add SUSPEND_TIMEOUT_HOURS config

**Files:**
- Modify: `src/codogram/config.py`
- Test: `tests/test_config.py` (add to existing)

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_suspend_timeout_default():
    """SUSPEND_TIMEOUT_HOURS has default value of 12."""
    from codogram.config import settings

    assert hasattr(settings, 'suspend_timeout_hours')
    assert settings.suspend_timeout_hours == 12
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_config.py::test_suspend_timeout_default -v`

Expected: FAIL with "has no attribute 'suspend_timeout_hours'"

**Step 3: Write implementation**

Add to `Settings` class in `src/codogram/config.py`:

```python
    # Auto-suspend
    suspend_timeout_hours: int = 12
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_config.py::test_suspend_timeout_default -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add suspend_timeout_hours setting (default 12h)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add resume messages to strings.py

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add strings**

Add to `src/codogram/strings.py` after "--- Session management ---" section:

```python
# --- Auto-suspend/resume ---

RESUME_SUSPENDED = f"{STATUS_PENDING} Session was suspended\\. Resuming\\.\\.\\."
RESUME_TMUX_MISSING = f"{STATUS_PENDING} Tmux not found\\. Launching\\.\\.\\."
RESUME_CLAUDE_DEAD = f"{STATUS_PENDING} Claude not responding\\. Relaunching\\.\\.\\."
RESUME_AFTER_COMMAND = f"{STATUS_INFO} Resumed\\. Please send your command again\\."
RESUME_AFTER_MESSAGE = f"{STATUS_PENDING} Processing your message\\.\\.\\."
RESUME_IN_PROGRESS = f"{STATUS_WARN} Session is resuming, please wait\\.\\.\\."
RESUME_FAILED = f"{STATUS_ERR} Failed to resume\\. Try /start again\\."
```

**Step 2: Run linter to verify syntax**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -c "from codogram import strings; print('OK')"`

Expected: OK (no import errors)

**Step 3: Commit**

```bash
git add src/codogram/strings.py
git commit -m "$(cat <<'EOF'
feat(strings): add auto-resume messages

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create ResumeService with detect and handle methods

**Files:**
- Create: `src/codogram/services/resume.py`
- Test: `tests/services/test_resume.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/services/test_resume.py
"""Tests for ResumeService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def resume_service():
    from codogram.services.resume import ResumeService
    return ResumeService()


@pytest.fixture
def mock_project():
    from codogram.core.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main")
    project.threads[None] = thread
    return project


def test_detect_resume_reason_suspended(resume_service, mock_project):
    """Detects suspended session."""
    thread = mock_project.threads[None]
    thread.suspended = True

    with patch('codogram.services.resume.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        reason = resume_service.detect_resume_reason(mock_project, thread)

    assert reason == "suspended"


def test_detect_resume_reason_tmux_missing(resume_service, mock_project):
    """Detects missing tmux."""
    thread = mock_project.threads[None]
    thread.suspended = False

    with patch('codogram.services.resume.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = False
        reason = resume_service.detect_resume_reason(mock_project, thread)

    assert reason == "tmux_missing"


def test_detect_resume_reason_claude_dead(resume_service, mock_project):
    """Detects dead Claude in existing tmux."""
    thread = mock_project.threads[None]
    thread.suspended = False
    thread.session_id = "abc123"  # Has session, so should check if Claude ready

    with patch('codogram.services.resume.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        mock_tmux.return_value.is_claude_ready.return_value = False
        reason = resume_service.detect_resume_reason(mock_project, thread)

    assert reason == "claude_dead"


def test_detect_resume_reason_none(resume_service, mock_project):
    """No resume needed when Claude is running."""
    thread = mock_project.threads[None]
    thread.suspended = False
    thread.session_id = "abc123"

    with patch('codogram.services.resume.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        mock_tmux.return_value.is_claude_ready.return_value = True
        reason = resume_service.detect_resume_reason(mock_project, thread)

    assert reason is None


@pytest.mark.asyncio
async def test_handle_resume_stores_pending_message(resume_service, mock_project):
    """handle_resume stores pending message action."""
    from codogram.domain.models import PendingAction

    thread = mock_project.threads[None]
    thread.suspended = True
    mock_queue = AsyncMock()
    mock_bot = AsyncMock()

    with patch('codogram.services.resume.launch_with_animation', new_callable=AsyncMock) as mock_launch:
        mock_launch.return_value = True

        with patch('codogram.services.resume.project_manager'):
            await resume_service.handle_resume(
                bot=mock_bot,
                chat_id=123,
                thread_id=None,
                project=mock_project,
                thread=thread,
                queue=mock_queue,
                pending_text="hello world",
                is_command=False,
                reason="suspended",
            )

    # Pending action should be stored then cleared after success
    assert thread.pending_action is None  # Cleared after handling
    assert thread.suspended is False


@pytest.mark.asyncio
async def test_handle_resume_stores_pending_command(resume_service, mock_project):
    """handle_resume stores pending command action."""
    thread = mock_project.threads[None]
    thread.suspended = True
    mock_queue = AsyncMock()
    mock_bot = AsyncMock()

    with patch('codogram.services.resume.launch_with_animation', new_callable=AsyncMock) as mock_launch:
        mock_launch.return_value = True

        with patch('codogram.services.resume.project_manager'):
            await resume_service.handle_resume(
                bot=mock_bot,
                chat_id=123,
                thread_id=None,
                project=mock_project,
                thread=thread,
                queue=mock_queue,
                pending_text="/help",
                is_command=True,
                reason="suspended",
            )

    # For commands, we just notify user to resend
    mock_queue.send.assert_called()  # Should have sent messages
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/services/test_resume.py -v`

Expected: FAIL with "No module named 'codogram.services.resume'"

**Step 3: Write implementation**

Create `src/codogram/services/resume.py`:

```python
# src/codogram/services/resume.py
"""Resume service for auto-resume functionality."""
from typing import Literal, TYPE_CHECKING

from aiogram import Bot

from .. import strings
from ..core.session_manager import ProjectState, ThreadInfo, project_manager
from ..domain.models import PendingAction
from ..tmux.session import TmuxSession
from ..logging_config import logger

if TYPE_CHECKING:
    from ..telegram.queue import TelegramQueue


ResumeReason = Literal["suspended", "tmux_missing", "claude_dead"]

REASON_MESSAGES = {
    "suspended": strings.RESUME_SUSPENDED,
    "tmux_missing": strings.RESUME_TMUX_MISSING,
    "claude_dead": strings.RESUME_CLAUDE_DEAD,
}


class ResumeService:
    """Service for detecting and handling auto-resume scenarios."""

    def detect_resume_reason(
        self,
        project: ProjectState,
        thread: ThreadInfo,
    ) -> ResumeReason | None:
        """Detect if session needs resume and why.

        Checks in order:
        1. suspended=True -> "suspended"
        2. tmux doesn't exist -> "tmux_missing"
        3. tmux exists but Claude not ready -> "claude_dead"
        4. All good -> None

        Returns:
            Resume reason or None if no resume needed.
        """
        # 1. Check suspended flag
        if thread.suspended:
            return "suspended"

        # 2. Check tmux exists
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)

        if not tmux.exists():
            return "tmux_missing"

        # 3. Check Claude ready (only if we have a session)
        if thread.session_id and not tmux.is_claude_ready():
            return "claude_dead"

        return None

    async def handle_resume(
        self,
        bot: Bot,
        chat_id: int,
        thread_id: int | None,
        project: ProjectState,
        thread: ThreadInfo,
        queue: "TelegramQueue",
        pending_text: str,
        is_command: bool,
        reason: ResumeReason,
    ) -> bool:
        """Handle auto-resume flow.

        1. Store pending action
        2. Send status message to user
        3. Kill tmux if Claude dead
        4. Launch Claude with animation
        5. After success: send pending message or ask to resend command

        Returns True if resume was triggered (regardless of success).
        """
        from ..telegram.launch_animation import launch_with_animation

        # 1. Store pending action
        thread.pending_action = PendingAction(
            type="command" if is_command else "message",
            text=pending_text,
        )

        # 2. Send status message
        await queue.send(
            chat_id,
            REASON_MESSAGES.get(reason, strings.RESUME_TMUX_MISSING),
            thread_id=thread_id,
            parse_mode="MarkdownV2",
        )

        # 3. Kill tmux if Claude dead (but tmux exists)
        if reason == "claude_dead":
            tmux_name = thread.get_tmux_session(project.project_name)
            tmux = TmuxSession(tmux_name, project.cwd)
            if tmux.exists():
                tmux.kill()
                logger.info(f"resume: killed dead tmux {tmux_name}")

        # 4. Start resume
        thread.resuming = True
        thread.suspended = False

        try:
            success = await launch_with_animation(
                bot=bot,
                chat_id=chat_id,
                thread_id=thread_id,
                project=project,
                thread=thread,
                queue=queue,
                session_id=thread.session_id if thread.has_valid_session() else None,
                cwd=thread.worktree_path or project.cwd,
            )

            if not success:
                await queue.send(
                    chat_id,
                    strings.RESUME_FAILED,
                    thread_id=thread_id,
                    parse_mode="MarkdownV2",
                )
                thread.pending_action = None
                return True

            # 5. Handle pending action
            action = thread.pending_action
            if action:
                if action.type == "command":
                    await queue.send(
                        chat_id,
                        strings.RESUME_AFTER_COMMAND,
                        thread_id=thread_id,
                        parse_mode="MarkdownV2",
                    )
                else:
                    await queue.send(
                        chat_id,
                        strings.RESUME_AFTER_MESSAGE,
                        thread_id=thread_id,
                        parse_mode="MarkdownV2",
                    )
                    # Send the message to Claude
                    tmux_name = thread.get_tmux_session(project.project_name)
                    actual_cwd = thread.worktree_path or project.cwd
                    tmux = TmuxSession(tmux_name, actual_cwd)
                    if tmux.exists():
                        tmux.send(action.text)
                        thread.last_activity_at = __import__('time').time()

                thread.pending_action = None

            return True

        finally:
            thread.resuming = False
            project_manager._save()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/services/test_resume.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/resume.py tests/services/test_resume.py
git commit -m "$(cat <<'EOF'
feat(resume): add ResumeService with detect_resume_reason and handle_resume

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add suspend check to coordinator

**Files:**
- Modify: `src/codogram/core/coordinator.py`
- Test: `tests/test_coordinator_suspend.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/test_coordinator_suspend.py
"""Tests for auto-suspend in coordinator."""
import pytest
import time
from unittest.mock import patch, MagicMock


def test_check_suspend_timeout_suspends_idle_session():
    """Suspends session idle for more than timeout."""
    from codogram.core.session_manager import ProjectState, ThreadInfo

    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    thread.last_activity_at = time.time() - (13 * 3600)  # 13 hours ago
    project.threads[None] = thread

    with patch('codogram.core.coordinator.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        mock_tmux.return_value.kill.return_value = None

        with patch('codogram.core.coordinator.settings') as mock_settings:
            mock_settings.suspend_timeout_hours = 12

            from codogram.core.coordinator import _check_suspend_timeout
            _check_suspend_timeout(project, thread)

    assert thread.suspended is True
    mock_tmux.return_value.kill.assert_called_once()


def test_check_suspend_timeout_ignores_active_session():
    """Does not suspend recently active session."""
    from codogram.core.session_manager import ProjectState, ThreadInfo

    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    thread.last_activity_at = time.time() - (1 * 3600)  # 1 hour ago
    project.threads[None] = thread

    with patch('codogram.core.coordinator.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True

        with patch('codogram.core.coordinator.settings') as mock_settings:
            mock_settings.suspend_timeout_hours = 12

            from codogram.core.coordinator import _check_suspend_timeout
            _check_suspend_timeout(project, thread)

    assert thread.suspended is False
    mock_tmux.return_value.kill.assert_not_called()


def test_check_suspend_timeout_uses_jsonl_mtime():
    """Uses jsonl mtime if more recent than last_activity_at."""
    from codogram.core.session_manager import ProjectState, ThreadInfo

    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    thread.last_activity_at = time.time() - (13 * 3600)  # 13 hours ago
    thread.jsonl_path = "/tmp/test.jsonl"
    project.threads[None] = thread

    # Mock jsonl mtime to be recent
    with patch('codogram.core.coordinator.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True

        with patch('codogram.core.coordinator.Path') as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.stat.return_value.st_mtime = time.time() - (1 * 3600)  # 1 hour ago

            with patch('codogram.core.coordinator.settings') as mock_settings:
                mock_settings.suspend_timeout_hours = 12

                from codogram.core.coordinator import _check_suspend_timeout
                _check_suspend_timeout(project, thread)

    assert thread.suspended is False  # Not suspended because jsonl was recent
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_coordinator_suspend.py -v`

Expected: FAIL with "cannot import name '_check_suspend_timeout'"

**Step 3: Write implementation**

Add to `src/codogram/core/coordinator.py`:

```python
# Add imports at top
from pathlib import Path
from ..config import settings

# Add function (can be called from _check_for_changes):
def _check_suspend_timeout(project: ProjectState, thread: ThreadInfo) -> bool:
    """Check if thread should be suspended due to inactivity.

    Returns True if thread was suspended.
    """
    # Skip if no session or already suspended
    if not thread.session_id or thread.suspended:
        return False

    # Skip if no tmux (nothing to suspend)
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)
    if not tmux.exists():
        return False

    # Calculate effective last activity
    last_activity = thread.last_activity_at or 0

    # Also check jsonl mtime (Claude-side activity)
    if thread.jsonl_path:
        jsonl_path = Path(thread.jsonl_path)
        if jsonl_path.exists():
            try:
                jsonl_mtime = jsonl_path.stat().st_mtime
                last_activity = max(last_activity, jsonl_mtime)
            except Exception:
                pass

    # Check if idle too long
    idle_seconds = time.time() - last_activity
    timeout_seconds = settings.suspend_timeout_hours * 3600

    if idle_seconds > timeout_seconds:
        # Suspend: kill tmux and mark as suspended
        tmux.kill()
        thread.suspended = True
        logger.info(
            f"session_suspended: project={project.project_name}, "
            f"thread={thread.name}, idle={idle_seconds/3600:.1f}h"
        )
        return True

    return False
```

Then call this from `_check_for_changes` method in `HistoryWatcher` class, inside the thread loop:

```python
# In _check_for_changes, after thread health checks:
# 2.5. Check suspend timeout
for thread in list(project.threads.values()):
    if _check_suspend_timeout(project, thread):
        self.project_manager._save()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_coordinator_suspend.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/core/coordinator.py tests/test_coordinator_suspend.py
git commit -m "$(cat <<'EOF'
feat(coordinator): add auto-suspend check for idle sessions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add activity tracking to message router

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Test: `tests/unit/handlers/test_messages_activity.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/unit/handlers/test_messages_activity.py
"""Tests for activity tracking in message handler."""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_message():
    msg = MagicMock()
    msg.chat.id = 123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = None
    msg.text = "hello"
    msg.from_user.id = 456
    msg.photo = None
    msg.document = None
    msg.video = None
    msg.forward_date = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.entities = []
    msg.caption_entities = []
    msg.caption = None
    msg.reply_to_message = None
    return msg


@pytest.fixture
def mock_project():
    from codogram.core.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    project.threads[None] = thread
    return project


@pytest.mark.asyncio
async def test_route_message_updates_last_activity(mock_message, mock_project):
    """Sending message updates last_activity_at."""
    from codogram.handlers.messages import _route_message

    thread = mock_project.threads[None]
    assert thread.last_activity_at is None

    with patch('codogram.handlers.messages._message_router') as mock_router:
        from codogram.services.message_router import RouteResult, RouteAction
        mock_router.route.return_value = RouteResult(
            action=RouteAction.SEND_TO_TMUX,
            project=mock_project,
            thread=thread,
            tmux_name="claude-test",
            cwd="/tmp/test",
        )
        mock_router.send_to_tmux.return_value = True

        mock_queue = AsyncMock()

        with patch('codogram.handlers.messages.project_manager'):
            with patch('codogram.handlers.messages._delete_active_ask_prompt'):
                with patch('codogram.handlers.messages._handle_ask_other_pending', return_value=False):
                    with patch('codogram.handlers.messages.handle_name_input', return_value=False):
                        await _route_message(mock_message, mock_queue)

    # Activity should be updated
    assert thread.last_activity_at is not None
    assert time.time() - thread.last_activity_at < 2  # Within 2 seconds
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/unit/handlers/test_messages_activity.py -v`

Expected: FAIL (activity not updated)

**Step 3: Write implementation**

Add to `_route_message` in `src/codogram/handlers/messages.py`, after successful send to tmux:

```python
# In SEND_TO_TMUX case, after success check:
case RouteAction.SEND_TO_TMUX:
    # ... existing code ...
    success = await _send_content(message, result, telegram_queue)
    if success and result.thread:
        # Update activity timestamp
        result.thread.last_activity_at = time.time()
    # ... rest of existing code ...
```

Add import at top:

```python
import time
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/unit/handlers/test_messages_activity.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/messages.py tests/unit/handlers/test_messages_activity.py
git commit -m "$(cat <<'EOF'
feat(messages): update last_activity_at on message send

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Wire up ResumeService in message router

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Test: `tests/unit/handlers/test_messages_resume.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/unit/handlers/test_messages_resume.py
"""Tests for auto-resume in message handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_message():
    msg = MagicMock()
    msg.chat.id = 123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = None
    msg.text = "hello"
    msg.from_user.id = 456
    msg.photo = None
    msg.document = None
    msg.video = None
    msg.forward_date = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.entities = []
    msg.caption_entities = []
    msg.caption = None
    msg.reply_to_message = None
    msg.bot = AsyncMock()
    return msg


@pytest.fixture
def mock_project():
    from codogram.core.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    thread.suspended = True  # Suspended session
    project.threads[None] = thread
    return project


@pytest.mark.asyncio
async def test_route_message_triggers_resume_for_suspended(mock_message, mock_project):
    """Message to suspended session triggers resume via ResumeService."""
    thread = mock_project.threads[None]

    with patch('codogram.handlers.messages._message_router') as mock_router:
        from codogram.services.message_router import RouteResult, RouteAction
        mock_router.route.return_value = RouteResult(
            action=RouteAction.SEND_TO_TMUX,
            project=mock_project,
            thread=thread,
            tmux_name="claude-test",
            cwd="/tmp/test",
        )

        with patch('codogram.handlers.messages._resume_service') as mock_resume:
            mock_resume.detect_resume_reason.return_value = "suspended"
            mock_resume.handle_resume = AsyncMock(return_value=True)

            mock_queue = AsyncMock()

            with patch('codogram.handlers.messages._handle_ask_other_pending', return_value=False):
                with patch('codogram.handlers.messages.handle_name_input', return_value=False):
                    from codogram.handlers.messages import _route_message
                    await _route_message(mock_message, mock_queue)

    # ResumeService.handle_resume should have been called
    mock_resume.handle_resume.assert_called_once()


@pytest.mark.asyncio
async def test_route_message_blocks_during_resume(mock_message, mock_project):
    """Message during active resume shows wait message."""
    thread = mock_project.threads[None]
    thread.resuming = True  # Resume in progress

    with patch('codogram.handlers.messages._message_router') as mock_router:
        from codogram.services.message_router import RouteResult, RouteAction
        mock_router.route.return_value = RouteResult(
            action=RouteAction.SEND_TO_TMUX,
            project=mock_project,
            thread=thread,
            tmux_name="claude-test",
            cwd="/tmp/test",
        )

        mock_queue = AsyncMock()

        with patch('codogram.handlers.messages._handle_ask_other_pending', return_value=False):
            with patch('codogram.handlers.messages.handle_name_input', return_value=False):
                from codogram.handlers.messages import _route_message
                await _route_message(mock_message, mock_queue)

    # Should have sent wait message
    mock_queue.reply.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/unit/handlers/test_messages_resume.py -v`

Expected: FAIL (no _resume_service)

**Step 3: Write implementation**

Add to `src/codogram/handlers/messages.py`:

```python
# Add import after existing service imports
from ..services.resume import ResumeService

# Add service instance after _file_input
_resume_service = ResumeService()
```

Modify `_route_message` SEND_TO_TMUX case:

```python
case RouteAction.SEND_TO_TMUX:
    # Check if resume in progress
    if result.thread and result.thread.resuming:
        await telegram_queue.reply(message, strings.RESUME_IN_PROGRESS)
        return

    # Check if resume needed
    if result.thread and result.project:
        resume_reason = _resume_service.detect_resume_reason(result.project, result.thread)
        if resume_reason:
            text = message.text or ""
            await _resume_service.handle_resume(
                bot=message.bot,
                chat_id=message.chat.id,
                thread_id=message.message_thread_id,
                project=result.project,
                thread=result.thread,
                queue=telegram_queue,
                pending_text=text,
                is_command=text.startswith("/"),
                reason=resume_reason,
            )
            return

    # Delete active AskUserQuestion if user is sending a message
    await _delete_active_ask_prompt(message)

    success = await _send_content(message, result, telegram_queue)
    if success and result.thread:
        # Update activity timestamp
        result.thread.last_activity_at = time.time()
    if not success and message.chat.id < 0:
        await telegram_queue.reply(message, "No active Claude session. Use /start to launch.")
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/unit/handlers/test_messages_resume.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/messages.py tests/unit/handlers/test_messages_resume.py
git commit -m "$(cat <<'EOF'
feat(messages): wire up ResumeService for auto-resume

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Integration test

**Files:**
- Test: `tests/test_auto_suspend_resume.py`

**Step 1: Write integration test**

```python
# tests/test_auto_suspend_resume.py
"""Integration tests for auto-suspend and auto-resume."""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_project_with_session():
    """Project with active Claude session."""
    from codogram.core.session_manager import ProjectState, ThreadInfo

    project = ProjectState(project_name="test", cwd="/tmp/test")
    project.chat_id = 123
    thread = ThreadInfo(
        thread_id=None,
        name="main",
        session_id="abc123",
        jsonl_path="/tmp/test.jsonl",
    )
    thread.last_activity_at = time.time()
    project.threads[None] = thread
    return project


def test_full_suspend_resume_cycle(mock_project_with_session):
    """Test complete suspend -> resume cycle."""
    thread = mock_project_with_session.threads[None]

    # 1. Simulate idle for 13 hours
    thread.last_activity_at = time.time() - (13 * 3600)

    # 2. Run suspend check
    with patch('codogram.core.coordinator.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        mock_tmux.return_value.kill.return_value = None

        with patch('codogram.core.coordinator.Path') as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.stat.return_value.st_mtime = thread.last_activity_at

            with patch('codogram.core.coordinator.settings') as mock_settings:
                mock_settings.suspend_timeout_hours = 12

                from codogram.core.coordinator import _check_suspend_timeout
                _check_suspend_timeout(mock_project_with_session, thread)

    # Verify suspended
    assert thread.suspended is True

    # 3. Check resume detection
    with patch('codogram.services.resume.TmuxSession') as mock_tmux:
        mock_tmux.return_value.exists.return_value = False  # Tmux killed

        from codogram.services.resume import ResumeService
        service = ResumeService()
        reason = service.detect_resume_reason(mock_project_with_session, thread)

    # Should detect suspended (flag set)
    assert reason == "suspended"
```

**Step 2: Run test**

Run: `cd /home/superbereza/dev/codogram/.worktrees/avtosaspend && python -m pytest tests/test_auto_suspend_resume.py -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_auto_suspend_resume.py
git commit -m "$(cat <<'EOF'
test: add integration test for auto-suspend/resume cycle

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Update E2E tests documentation

**Files:**
- Create: `docs/e2e/features/auto-suspend.md`

**Step 1: Write E2E test documentation**

```markdown
# Auto-Suspend & Auto-Resume E2E Tests

## Prerequisites
- Bot running
- Active Claude session in test chat

## Test: Session Suspends After Idle

**Setup:** Session with last_activity_at > 12 hours ago

**Steps:**
1. Wait for coordinator check (every 15s)
2. Observe logs for "session_suspended"

**Expected:**
- Tmux session killed
- Thread.suspended = True
- No Telegram notification (silent suspend)

## Test: Message to Suspended Session Resumes

**Steps:**
1. Have suspended session (from previous test)
2. Send message: "hello"

**Expected:**
1. Bot responds: "⏸️ Session was suspended. Resuming..."
2. Launch animation plays
3. Bot responds: "Processing your message..."
4. Message delivered to Claude

## Test: Message During Resume Shows Wait

**Steps:**
1. Trigger resume (send message to suspended)
2. Immediately send another message

**Expected:**
- Bot responds: "Session is resuming, please wait..."
- Original message still processed after resume

## Test: Command to Suspended Session

**Steps:**
1. Have suspended session
2. Send: /help

**Expected:**
1. Bot responds: "⏸️ Session was suspended. Resuming..."
2. Launch animation
3. Bot responds: "Resumed. Please send your command again."
```

**Step 2: Commit**

```bash
git add docs/e2e/features/auto-suspend.md
git commit -m "$(cat <<'EOF'
docs: add E2E test documentation for auto-suspend/resume

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Remove "Session closed" notification and `notified_closed` field

**Files:**
- Modify: `src/codogram/core/coordinator.py` — remove notification block
- Modify: `src/codogram/core/session_manager.py` — remove `notified_closed` field and loading
- Modify: `src/codogram/telegram/launch_animation.py` — remove `notified_closed = False`
- Modify: `src/codogram/services/branch.py` — remove `notified_closed = True`

**Step 1: Simplify tmux died handling in coordinator.py**

In `_check_for_changes()`, replace the "Session closed" notification block (lines 92-118) with simpler logic:

```python
# Check if tmux died - just cancel tasks, no notification
# Auto-resume will handle relaunch on next user message
if thread.session_id and not tmux.exists():
    # Stop thread tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
        thread.watcher_task = None
    if thread.poller_task:
        thread.poller_task.cancel()
        thread.poller_task = None
    # NOTE: Keep session_id/jsonl_path for auto-resume
```

**Step 2: Remove `notified_closed` from ThreadInfo**

In `session_manager.py`, remove from ThreadInfo dataclass:

```python
# DELETE this line from ThreadInfo:
notified_closed: bool = False
```

Remove from `_load_projects()` (2 places):

```python
# DELETE these lines:
notified_closed=bool(thread_data.get("session_id")),
notified_closed=bool(data.get("session_id")),
```

**Step 3: Remove from launch_animation.py**

```python
# DELETE this line (around line 102):
thread.notified_closed = False
```

**Step 4: Remove from branch.py**

```python
# DELETE this line (around line 51):
thread.notified_closed = True
```

**Step 5: Verify syntax**

Run: `python -c "from codogram.core import coordinator, session_manager; from codogram.telegram import launch_animation; from codogram.services import branch; print('OK')"`

Expected: OK

**Step 6: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove Session closed notification and notified_closed field

With auto-resume, we don't need to notify users when tmux dies.
The next message will trigger auto-resume transparently.

Removed:
- "Session closed" notification in coordinator
- notified_closed field from ThreadInfo
- All 4 usages of notified_closed

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Remove should_cleanup_project (30-day)

**Files:**
- Modify: `src/codogram/core/session_manager.py` — delete `should_cleanup_project()`
- Modify: `src/codogram/core/coordinator.py` — remove cleanup call
- Delete: tests that use `should_cleanup_project`

**Step 1: Remove from coordinator.py**

Remove lines 64-79 in `_check_for_changes()`:

```python
# DELETE THIS BLOCK:
# 1. Check if should cleanup (inactive > 30 days)
if should_cleanup_project(project):
    logger.info("project_cleanup", ...)
    # Cancel all thread tasks
    ...
    del self.project_manager.projects[project.project_name]
    continue
```

Also remove the import:
```python
from .session_manager import should_cleanup_project  # DELETE
```

**Step 2: Remove from session_manager.py**

Delete the entire `should_cleanup_project()` function (lines 61-130).

**Step 3: Remove/update tests**

Search for tests using `should_cleanup_project` and remove them.

**Step 4: Verify syntax**

Run: `python -c "from codogram.core import coordinator, session_manager; print('OK')"`

Expected: OK

**Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove 30-day project cleanup (replaced by auto-suspend)

Auto-suspend + auto-resume replaces the need for automatic project deletion.
Projects now persist and can be resumed at any time.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Move design doc to done

**Files:**
- Move: `docs/plans/2026-01-24-auto-suspend-design.md` → `docs/designs/done/`

**Step 1: Move design to done**

```bash
mv docs/plans/2026-01-24-auto-suspend-design.md docs/designs/done/
```

**Step 2: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: move auto-suspend design to done

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

Total tasks: 13
Estimated commits: 13

Key changes:
1. New `PendingAction` dataclass for holding messages during resume
2. New ThreadInfo fields: `last_activity_at`, `suspended`, `resuming`, `pending_action`
3. New `SUSPEND_TIMEOUT_HOURS` config (default 12)
4. New resume messages in strings.py
5. New `ResumeService` for detect/handle resume logic
6. Suspend check in coordinator loop
7. Activity tracking in message router only (jsonl mtime covers commands)
8. Auto-resume logic in message handler
9. Integration tests
10. E2E documentation
11. Remove "Session closed" notification + `notified_closed` field (4 files)
12. Remove `should_cleanup_project()` — replaced by auto-suspend
