# tests/test_history_watcher.py
import os
# Set env vars BEFORE importing telegram_bridge modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_check_session_for_project_detects_change():
    """Test that check_session_for_project detects session changes."""
    from telegram_bridge.history_watcher import check_session_for_project

    bot = MagicMock()
    start_poller = AsyncMock(return_value=MagicMock())
    start_watcher = AsyncMock(return_value=MagicMock())

    # Mock project
    mock_project = MagicMock()
    mock_project.chat_id = 123
    mock_project.cwd = "/test/path"
    mock_project.session_id = "old-session"
    mock_project.watcher_task = None

    # Create a mock project_manager
    mock_pm = MagicMock()
    mock_pm.refresh_project_session.return_value = True  # Session changed
    mock_pm._maybe_start_tasks = AsyncMock()

    # Patch session_manager module where it's imported from
    with patch('telegram_bridge.session_manager.project_manager', mock_pm):
        await check_session_for_project(mock_project, bot, start_poller, start_watcher)

        # Should have called refresh and _maybe_start_tasks
        mock_pm.refresh_project_session.assert_called_once_with(mock_project)
        mock_pm._maybe_start_tasks.assert_called_once()

@pytest.mark.asyncio
async def test_history_watcher_checks_tmux_health():
    """Test that HistoryWatcher only checks tmux health."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    bot.send_message = AsyncMock()
    start_poller = AsyncMock()
    start_watcher = AsyncMock()
    watcher = HistoryWatcher(bot, start_poller, start_watcher)

    # Mock project
    mock_project = MagicMock()
    mock_project.chat_id = 123
    mock_project.cwd = "/test/path"
    mock_project.tmux_session = "test-tmux"
    mock_project.watcher_task = None
    mock_project.poller_task = None

    mock_pm = MagicMock()
    mock_pm.projects = {"test": mock_project}
    watcher.project_manager = mock_pm

    with patch('telegram_bridge.session_manager.should_cleanup_project', return_value=False):
        with patch('telegram_bridge.history_watcher.TmuxSession') as mock_tmux:
            mock_tmux.return_value.exists.return_value = True

            await watcher._check_for_changes()

            # Should have checked tmux but not called refresh_project_session
            mock_tmux.assert_called_once_with("test-tmux", "/test/path")
            mock_pm.refresh_project_session.assert_not_called()
