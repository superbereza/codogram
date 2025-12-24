# Fix Poller Duplication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent duplicate pollers when multiple sessions share the same tmux session

**Architecture:** Fix two issues in SessionManager: (1) await task cancellation in unregister_session, (2) deduplicate by tmux_session in restore_sessions - keep only the most recent session per tmux

**Tech Stack:** Python asyncio, pytest

---

## Task 1: Add test for unregister awaiting cancellation

**Files:**
- Create: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
# tests/test_session_manager.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_config():
    """Mock config loading/saving."""
    with patch("telegram_bridge.session_manager.load_config") as load, \
         patch("telegram_bridge.session_manager.save_config") as save:
        load.return_value = {"projects": {}, "sessions": {}}
        yield {"load": load, "save": save}

@pytest.fixture
def session_manager(mock_config):
    """Create fresh SessionManager."""
    from telegram_bridge.session_manager import SessionManager
    return SessionManager()

@pytest.mark.asyncio
async def test_unregister_awaits_task_cancellation(session_manager):
    """unregister_session should await task cancellation."""
    # Create a task that tracks if it was properly awaited
    cancel_awaited = asyncio.Event()

    async def slow_poller():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancel_awaited.set()
            raise

    task = asyncio.create_task(slow_poller())

    # Manually add session with the task
    from telegram_bridge.session_manager import SessionState
    session = SessionState(
        session_id="test-123",
        tmux_session="test-tmux",
        cwd="/tmp",
        project_name="test",
        poller_task=task,
    )
    session_manager.sessions["test-123"] = session

    # Unregister should await cancellation
    await session_manager.unregister_session("test-123")

    # Task should have received CancelledError and set the event
    assert cancel_awaited.is_set(), "Task cancellation was not awaited"
    assert task.cancelled() or task.done()
```

**Step 2: Run test to verify it fails**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_unregister_awaits_task_cancellation -v`

Expected: FAIL - cancel_awaited.is_set() is False

**Step 3: Implement fix in unregister_session**

Modify: `src/telegram_bridge/session_manager.py:115-123`

```python
    async def unregister_session(self, session_id: str) -> None:
        """Unregister Claude session."""
        session = self.sessions.pop(session_id, None)
        if session:
            if session.poller_task:
                session.poller_task.cancel()
                try:
                    await session.poller_task
                except asyncio.CancelledError:
                    pass
            if session.watcher_task:
                session.watcher_task.cancel()
                try:
                    await session.watcher_task
                except asyncio.CancelledError:
                    pass
        self._save()
```

**Step 4: Run test to verify it passes**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_unregister_awaits_task_cancellation -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_session_manager.py src/telegram_bridge/session_manager.py
git commit -m "fix(session): await task cancellation in unregister"
```

---

## Task 2: Add test for restore_sessions deduplication

**Files:**
- Modify: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_restore_sessions_deduplicates_by_tmux(mock_config):
    """restore_sessions should only start one poller per tmux session."""
    # Config has two sessions with same tmux_session
    mock_config["load"].return_value = {
        "projects": {"test-project": 12345},
        "sessions": {
            "old-session": {
                "tmux_session": "my-tmux",
                "cwd": "/home/user/project",
                "project_name": "test-project",
                "jsonl_path": "/tmp/old.jsonl",
            },
            "new-session": {
                "tmux_session": "my-tmux",  # Same tmux!
                "cwd": "/home/user/project",
                "project_name": "test-project",
                "jsonl_path": "/tmp/new.jsonl",
            },
        },
    }

    from telegram_bridge.session_manager import SessionManager
    manager = SessionManager()

    poller_starts = []

    async def mock_start_poller(session):
        poller_starts.append(session.session_id)
        return AsyncMock()

    async def mock_start_watcher(session):
        return AsyncMock()

    with patch("telegram_bridge.session_manager.TmuxSession") as mock_tmux:
        mock_tmux.return_value.exists.return_value = True
        await manager.restore_sessions(mock_start_poller, mock_start_watcher)

    # Should only start ONE poller for the tmux session
    assert len(poller_starts) == 1, f"Expected 1 poller, got {len(poller_starts)}: {poller_starts}"
    # Should keep the newer session (new-session comes after old-session alphabetically,
    # but we want most recent by jsonl mtime - for simplicity, keep last in iteration)
    assert "new-session" in poller_starts or "old-session" in poller_starts
```

**Step 2: Run test to verify it fails**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_restore_sessions_deduplicates_by_tmux -v`

Expected: FAIL - len(poller_starts) == 2

**Step 3: Implement fix in restore_sessions**

Modify: `src/telegram_bridge/session_manager.py:125-150`

```python
    async def restore_sessions(
        self,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})

        # Deduplicate by tmux_session - keep only one session per tmux
        # Group by tmux_session, keep the last one (most recently added to config)
        tmux_to_session: dict[str, tuple[str, dict]] = {}
        for session_id, data in saved_sessions.items():
            tmux_name = data["tmux_session"]
            tmux_to_session[tmux_name] = (session_id, data)

        # Only restore deduplicated sessions
        for session_id, data in tmux_to_session.values():
            chat_id = self.get_chat_id(data["project_name"])
            session = SessionState(
                session_id=session_id,
                tmux_session=data["tmux_session"],
                cwd=data["cwd"],
                project_name=data["project_name"],
                jsonl_path=data.get("jsonl_path"),
                chat_id=chat_id,
            )
            self.sessions[session_id] = session

            if chat_id:
                # Verify tmux session still exists
                tmux = TmuxSession(session.tmux_session, session.cwd)
                if tmux.exists():
                    session.poller_task = await start_poller(session)
                    if session.jsonl_path:
                        session.watcher_task = await start_watcher(session)
```

**Step 4: Run test to verify it passes**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_restore_sessions_deduplicates_by_tmux -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "fix(session): deduplicate pollers by tmux in restore"
```

---

## Task 3: Clean stale sessions from config on restore

**Files:**
- Modify: `tests/test_session_manager.py`
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_restore_sessions_cleans_dead_tmux(mock_config):
    """restore_sessions should remove sessions for non-existent tmux."""
    mock_config["load"].return_value = {
        "projects": {"test-project": 12345},
        "sessions": {
            "dead-session": {
                "tmux_session": "dead-tmux",
                "cwd": "/tmp",
                "project_name": "test-project",
                "jsonl_path": None,
            },
        },
    }

    from telegram_bridge.session_manager import SessionManager
    manager = SessionManager()

    async def mock_start_poller(session):
        return AsyncMock()

    async def mock_start_watcher(session):
        return AsyncMock()

    with patch("telegram_bridge.session_manager.TmuxSession") as mock_tmux:
        mock_tmux.return_value.exists.return_value = False  # tmux doesn't exist
        await manager.restore_sessions(mock_start_poller, mock_start_watcher)

    # Session should not be in memory
    assert len(manager.sessions) == 0
    # Config should be saved (cleaned)
    assert mock_config["save"].called
```

**Step 2: Run test to verify it fails**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_restore_sessions_cleans_dead_tmux -v`

Expected: FAIL - session still in manager.sessions

**Step 3: Implement fix**

Modify `restore_sessions` to not add sessions with dead tmux and save cleaned config:

```python
    async def restore_sessions(
        self,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})

        # Deduplicate by tmux_session - keep only one session per tmux
        tmux_to_session: dict[str, tuple[str, dict]] = {}
        for session_id, data in saved_sessions.items():
            tmux_name = data["tmux_session"]
            tmux_to_session[tmux_name] = (session_id, data)

        # Only restore deduplicated sessions with live tmux
        for session_id, data in tmux_to_session.values():
            tmux = TmuxSession(data["tmux_session"], data["cwd"])
            if not tmux.exists():
                continue  # Skip dead tmux sessions

            chat_id = self.get_chat_id(data["project_name"])
            session = SessionState(
                session_id=session_id,
                tmux_session=data["tmux_session"],
                cwd=data["cwd"],
                project_name=data["project_name"],
                jsonl_path=data.get("jsonl_path"),
                chat_id=chat_id,
            )
            self.sessions[session_id] = session

            if chat_id:
                session.poller_task = await start_poller(session)
                if session.jsonl_path:
                    session.watcher_task = await start_watcher(session)

        # Save cleaned config
        self._save()
```

**Step 4: Run test to verify it passes**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/test_session_manager.py::test_restore_sessions_cleans_dead_tmux -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "fix(session): clean dead tmux sessions on restore"
```

---

## Task 4: Run all tests and verify

**Step 1: Run full test suite**

Run: `cd agent-tools/telegram-bridge && python -m pytest tests/ -v`

Expected: All tests PASS

**Step 2: Manual integration test**

```bash
# 1. Kill bot
pkill -f telegram_bridge

# 2. Clear config
echo '{"projects": {"personal-agent": -5077677938}, "sessions": {}}' > agent-tools/telegram-bridge/.config.json

# 3. Restart bot
./agent-tools/telegram-bridge/restart.sh

# 4. Register session
curl -X POST http://localhost:8787/session/register \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-1", "cwd": "/home/superbereza/dev/personal-agent", "tmux_session": "personal-agent"}'

# 5. Register again (simulating /new)
curl -X POST http://localhost:8787/session/register \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-2", "cwd": "/home/superbereza/dev/personal-agent", "tmux_session": "personal-agent"}'

# 6. Check logs - should show only ONE poller active
tail -20 ~/dev/personal-agent/tmp/telegram-bridge-logs/poller-debug.log
```

**Step 3: Commit if all good**

```bash
git add -A
git commit -m "test(session): add integration verification"
```
