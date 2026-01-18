# tests/services/test_admin_rights.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from codogram.services.setup.admin_rights import check_bot_admin_rights


@pytest.mark.asyncio
async def test_check_admin_rights_returns_true_when_admin():
    """Returns True when bot has can_change_info right."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "administrator"
    member.can_change_info = True

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is True


@pytest.mark.asyncio
async def test_check_admin_rights_returns_false_when_not_admin():
    """Returns False when bot is just a member."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "member"

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is False


@pytest.mark.asyncio
async def test_check_admin_rights_returns_false_without_can_change_info():
    """Returns False when admin but no can_change_info."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "administrator"
    member.can_change_info = False

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is False
