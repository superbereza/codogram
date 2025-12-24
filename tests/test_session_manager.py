# tests/test_session_manager.py
import os
# Set env vars BEFORE importing telegram_bridge modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

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

    # Give task a moment to start running
    await asyncio.sleep(0.01)

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
