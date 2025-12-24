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
