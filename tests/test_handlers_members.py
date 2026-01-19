"""Tests for members handler."""
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestIsLeaveOrDemotion:
    """Tests for _is_leave_or_demotion helper."""

    def test_left_status(self):
        """Returns True for 'left' status."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "left"
        assert _is_leave_or_demotion(event) is True

    def test_kicked_status(self):
        """Returns True for 'kicked' status."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "kicked"
        assert _is_leave_or_demotion(event) is True

    def test_demoted_from_admin(self):
        """Returns True when demoted from admin to member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is True

    def test_demoted_from_creator(self):
        """Returns True when demoted from creator to member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "creator"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is True

    def test_member_still_member(self):
        """Returns False when member stays member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is False

    def test_promoted_to_admin(self):
        """Returns False when promoted to admin."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "administrator"
        assert _is_leave_or_demotion(event) is False


class TestOnBotStatusChanged:
    """Tests for on_bot_status_changed handler."""

    @pytest.mark.asyncio
    async def test_ignores_private_chat(self):
        """Ignores events from private chats."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "private"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_added_registers_group(self):
        """Calls check_and_register when bot added as member."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 123
        event.new_chat_member.status = "member"
        event.bot = Mock()
        group_auth = AsyncMock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_called_once_with(event.bot, 123)

    @pytest.mark.asyncio
    async def test_bot_added_as_admin_registers_group(self):
        """Calls check_and_register when bot added as administrator."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "group"
        event.chat.id = 456
        event.new_chat_member.status = "administrator"
        event.bot = Mock()
        group_auth = AsyncMock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_called_once_with(event.bot, 456)

    @pytest.mark.asyncio
    async def test_bot_removed_calls_on_bot_removed(self):
        """Calls on_bot_removed when bot leaves."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 789
        event.new_chat_member.status = "left"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.on_bot_removed.assert_called_once_with(789)

    @pytest.mark.asyncio
    async def test_bot_kicked_calls_on_bot_removed(self):
        """Calls on_bot_removed when bot is kicked."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 789
        event.new_chat_member.status = "kicked"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.on_bot_removed.assert_called_once_with(789)


class TestOnMemberUpdate:
    """Tests for on_member_update handler."""

    @pytest.mark.asyncio
    async def test_ignores_non_leave_events(self):
        """Ignores member joins and promotions."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "administrator"
        event.new_chat_member.user.is_bot = False
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()

        await on_member_update(event, telegram_queue, group_auth)

        group_auth.on_admin_left.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_on_admin_left_for_leave(self):
        """Calls on_admin_left when member leaves."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456, is_bot=False))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=False)

        with patch("codogram.handlers.members.project_manager") as pm:
            pm.get_by_chat.return_value = None
            await on_member_update(event, telegram_queue, group_auth)

        group_auth.on_admin_left.assert_called_once_with(event.bot, 123, 456)

    @pytest.mark.asyncio
    async def test_sends_message_when_deactivated(self):
        """Sends GROUP_DEACTIVATED message when group deactivated."""
        from codogram.handlers.members import on_member_update
        from codogram import strings

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456, is_bot=False))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=True)

        with patch("codogram.handlers.members.project_manager") as pm:
            pm.get_by_chat.return_value = None
            await on_member_update(event, telegram_queue, group_auth)

        telegram_queue.send.assert_called_once_with(123, strings.GROUP_DEACTIVATED)

    @pytest.mark.asyncio
    async def test_no_message_when_still_valid(self):
        """No message when group still valid after admin leaves."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456, is_bot=False))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=False)

        with patch("codogram.handlers.members.project_manager") as pm:
            pm.get_by_chat.return_value = None
            await on_member_update(event, telegram_queue, group_auth)

        telegram_queue.send.assert_not_called()
