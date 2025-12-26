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
async def test_history_watcher_detects_session_change():
    """Test that HistoryWatcher detects session changes."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    start_poller = AsyncMock(return_value=MagicMock())
    start_watcher = AsyncMock(return_value=MagicMock())

    watcher = HistoryWatcher(bot, start_poller, start_watcher)

    # Mock project_manager with a test project
    with patch('telegram_bridge.history_watcher.project_manager') as mock_pm:
        mock_project = MagicMock()
        mock_project.chat_id = 123
        mock_project.cwd = "/test/path"
        mock_project.session_id = "old-session"
        mock_project.watcher_task = None
        mock_pm.projects = {"test": mock_project}
        mock_pm.refresh_project_session.return_value = True  # Session changed
        mock_pm._maybe_start_tasks = AsyncMock()  # Mock as async

        with patch('telegram_bridge.history_watcher.HISTORY_PATH') as mock_path:
            mock_path.exists.return_value = True
            mock_path.stat.return_value.st_mtime = 12345

            await watcher._check_for_changes()

            # Should have called refresh and _maybe_start_tasks
            mock_pm.refresh_project_session.assert_called_once_with(mock_project)
            mock_pm._maybe_start_tasks.assert_called_once()

@pytest.mark.asyncio
async def test_history_watcher_skips_when_no_change():
    """Test that HistoryWatcher skips when mtime unchanged."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    watcher = HistoryWatcher(bot, AsyncMock(), AsyncMock())
    watcher._last_mtime = 12345  # Same as we'll return

    with patch('telegram_bridge.history_watcher.HISTORY_PATH') as mock_path:
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_mtime = 12345

        with patch('telegram_bridge.history_watcher.project_manager') as mock_pm:
            await watcher._check_for_changes()

            # Should not have called refresh
            mock_pm.refresh_project_session.assert_not_called()
