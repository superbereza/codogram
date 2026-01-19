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
        """Admin users can access handlers in private chat."""
        middleware = AdminMiddleware()
        handler = AsyncMock(return_value="result")
        event = Mock()
        chat = Mock(type="private", id=123)
        data = {
            "event_from_user": Mock(id=123, is_bot=False),
            "event_chat": chat,
        }

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_called_once_with(event, data)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_non_admin_message_blocked_with_id(self):
        """Non-admin Message users are blocked and receive their ID."""
        from aiogram.types import Message

        middleware = AdminMiddleware()
        handler = AsyncMock()
        # Create proper Message mock
        event = Mock(spec=Message)
        telegram_queue = AsyncMock()
        telegram_queue.reply = AsyncMock()
        chat = Mock(type="private", id=999)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "telegram_queue": telegram_queue,
        }

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None
        telegram_queue.reply.assert_called_once()
        # Check message follows tone-of-voice: [x] prefix + ID
        call_args = telegram_queue.reply.call_args[0][1]  # Second positional arg is text
        assert "Not admin" in call_args
        assert "999" in call_args

    @pytest.mark.asyncio
    async def test_non_admin_callback_gets_alert(self):
        """Non-admin CallbackQuery gets show_alert popup with ID."""
        from aiogram.types import CallbackQuery

        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock(spec=CallbackQuery)
        event.answer = AsyncMock()
        chat = Mock(type="private", id=999)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
        }

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

    @pytest.mark.asyncio
    async def test_bot_user_ignored_silently(self):
        """Bot users (including service messages) are ignored silently."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        # Simulate a bot user (e.g., service message from topic creation)
        bot_user = Mock(id=8261696530, is_bot=True)
        data = {"event_from_user": bot_user}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None


class TestAdminMiddlewareGroups:
    """Tests for group authorization in AdminMiddleware."""

    @pytest.mark.asyncio
    async def test_group_allowed_passes(self):
        """Allowed group members can access handlers."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=True)
        group_auth.needs_revalidation = Mock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_called_once()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_group_not_allowed_registers(self):
        """Unknown group triggers check_and_register."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=True)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        bot = Mock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": bot,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        group_auth.check_and_register.assert_called_once_with(bot, 123)
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_rejected_sends_message(self):
        """Unauthorized group gets rejection message."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        telegram_queue = AsyncMock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
            "telegram_queue": telegram_queue,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        telegram_queue.reply.assert_called_once()
        assert "not active" in telegram_queue.reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_group_media_ignored(self):
        """Non-text messages in groups are ignored."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = None  # Media message
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
        }

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_group_revalidation_triggered(self):
        """Re-validation is triggered after restart."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        group_auth.needs_revalidation = Mock(return_value=True)
        group_auth.revalidate = AsyncMock(return_value=True)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        group_auth.revalidate.assert_called_once()
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_none_ignored(self):
        """Events with chat=None are ignored."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock()
        data = {
            "event_from_user": Mock(id=123, is_bot=False),
            "event_chat": None,
        }

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_group_revalidation_fails_sends_rejection(self):
        """Re-validation failure sends rejection message."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import Message

        group_auth = Mock(spec=GroupAuthService)
        group_auth.needs_revalidation = Mock(return_value=True)
        group_auth.revalidate = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        telegram_queue = AsyncMock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
            "telegram_queue": telegram_queue,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        telegram_queue.reply.assert_called_once()
        assert "not active" in telegram_queue.reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_callback_query_rejected_in_group(self):
        """CallbackQuery in unauthorized group gets popup."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService
        from aiogram.types import CallbackQuery

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=CallbackQuery)
        event.answer = AsyncMock()
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        event.answer.assert_called_once()
        assert event.answer.call_args[1].get('show_alert') is True
