# tests/test_history_watcher.py
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_history_watcher_checks_tmux_and_sessions():
    """Test that HistoryWatcher checks tmux health for threads."""
    from codogram.history_watcher import HistoryWatcher
    from codogram.session_manager import ThreadInfo

    bot = MagicMock()
    bot.send_message = AsyncMock()
    start_poller = AsyncMock()
    start_watcher = AsyncMock()
    telegram_queue = MagicMock()
    telegram_queue.enqueue_nowait = AsyncMock()
    watcher = HistoryWatcher(bot, start_poller, start_watcher, telegram_queue)

    # Mock thread
    mock_thread = MagicMock(spec=ThreadInfo)
    mock_thread.thread_id = None
    mock_thread.name = "main"
    mock_thread.session_id = "old-session"
    mock_thread.watcher_task = None
    mock_thread.poller_task = None
    mock_thread.awaiting_new_session = False
    mock_thread.binding_task = None
    mock_thread.get_tmux_session.return_value = "claude-test"

    # Mock project
    mock_project = MagicMock()
    mock_project.chat_id = 123
    mock_project.cwd = "/test/path"
    mock_project.project_name = "test"
    mock_project.threads = {None: mock_thread}
    # Legacy fields for cleanup check
    mock_project.watcher_task = None
    mock_project.poller_task = None

    mock_pm = MagicMock()
    mock_pm.projects = {"test": mock_project}
    watcher.project_manager = mock_pm

    with patch('codogram.session_manager.should_cleanup_project', return_value=False):
        with patch('codogram.history_watcher.TmuxSession') as mock_tmux:
            mock_tmux.return_value.exists.return_value = True

            await watcher._check_for_changes()

            # Should have checked tmux health for thread
            mock_thread.get_tmux_session.assert_called_once_with("test")
            mock_tmux.assert_called_once_with("claude-test", "/test/path")
