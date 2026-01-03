"""Tests for permission handler.

Note: Admin check is done by global middleware, not tested here.
"""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.handlers.permissions import on_permission_callback


class TestPermissionCallback:
    """Tests for on_permission_callback."""

    @pytest.fixture
    def mock_callback(self):
        """Create mock callback."""
        callback = Mock()
        callback.data = "perm:y:claude-test"
        callback.answer = AsyncMock()
        callback.bot = Mock()
        callback.bot.delete_message = AsyncMock()
        callback.message = Mock()
        callback.message.chat = Mock(id=123)
        callback.message.message_id = 456
        callback.message.delete = AsyncMock()
        return callback

    @pytest.mark.asyncio
    async def test_permission_yes(self, mock_callback):
        """Yes button sends 'y' to tmux."""
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("y")
        mock_callback.answer.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_permission_no(self, mock_callback):
        """No button sends 'n' to tmux."""
        mock_callback.data = "perm:n:claude-test"
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("n")

    @pytest.mark.asyncio
    async def test_permission_escape(self, mock_callback):
        """Esc button sends Escape key to tmux."""
        mock_callback.data = "perm:esc:claude-test"
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("Escape")

    @pytest.mark.asyncio
    async def test_permission_session_not_found(self, mock_callback):
        """Returns error if session not found."""
        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = None
            await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Session not found")

    @pytest.mark.asyncio
    async def test_permission_invalid_format(self, mock_callback):
        """Returns error for invalid callback format."""
        mock_callback.data = "perm:y"  # Missing tmux_session

        await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Invalid callback format")

    @pytest.mark.asyncio
    async def test_permission_tmux_closed(self, mock_callback):
        """Returns error if tmux session no longer exists."""
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = False  # Tmux closed

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Tmux session closed")
