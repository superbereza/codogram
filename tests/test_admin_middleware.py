"""Tests for admin middleware."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.middleware.admin import AdminMiddleware, is_admin


class TestIsAdmin:
    """Tests for is_admin helper."""

    def test_admin_returns_true(self):
        with patch("codogram.middleware.admin.get_admin_ids", return_value={123, 456}):
            assert is_admin(123) is True
            assert is_admin(456) is True

    def test_non_admin_returns_false(self):
        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            assert is_admin(999) is False


class TestAdminMiddleware:
    """Tests for AdminMiddleware."""

    @pytest.mark.asyncio
    async def test_admin_allowed(self):
        """Admin users can access handlers."""
        middleware = AdminMiddleware()
        handler = AsyncMock(return_value="result")
        event = Mock()
        data = {"event_from_user": Mock(id=123)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_called_once_with(event, data)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_non_admin_message_blocked_with_id(self):
        """Non-admin Message users are blocked and receive their ID."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        event.reply = AsyncMock()
        data = {"event_from_user": Mock(id=999)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None
        event.reply.assert_called_once()
        # Check message follows tone-of-voice: [x] prefix + ID (escaped for MarkdownV2)
        call_args = event.reply.call_args[0][0]
        assert "Not admin" in call_args
        assert "999" in call_args

    @pytest.mark.asyncio
    async def test_non_admin_callback_gets_alert(self):
        """Non-admin CallbackQuery gets show_alert popup with ID."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock(spec=['answer'])  # CallbackQuery-like
        event.answer = AsyncMock()
        data = {"event_from_user": Mock(id=999)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        event.answer.assert_called_once()
        assert event.answer.call_args[1].get('show_alert') is True
        # Check message follows tone-of-voice: [x] prefix + ID
        call_args = event.answer.call_args[0][0]
        assert "[x]" in call_args
        assert "999" in call_args

    @pytest.mark.asyncio
    async def test_no_user_blocked_silently(self):
        """Events without user are blocked silently."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        data = {}  # No event_from_user

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    def test_empty_admin_ids_blocks_everyone(self):
        """Empty ADMIN_IDS blocks all users."""
        with patch("codogram.middleware.admin.get_admin_ids", return_value=set()):
            assert is_admin(123) is False
            assert is_admin(0) is False
