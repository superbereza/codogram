"""Tests for chat member update handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_chat_member_update():
    """Create mock ChatMemberUpdated event."""
    update = MagicMock()
    update.chat.id = -100123456
    update.chat.title = "Test Project"
    update.chat.type = "supergroup"
    update.chat.invite_link = None
    update.from_user.id = 789
    update.from_user.username = "creator"
    update.new_chat_member.status = "administrator"
    update.old_chat_member.status = "left"
    return update


@pytest.mark.asyncio
async def test_bot_added_sends_push_to_admins(mock_chat_member_update):
    """Should send push notification to all admins when bot is added."""
    from codogram.handlers.dm import on_bot_added_to_chat

    mock_bot = MagicMock()
    mock_bot.id = 999
    mock_bot.send_message = AsyncMock()

    with patch("codogram.handlers.dm.settings") as mock_settings:
        mock_settings.get_admin_ids.return_value = {111, 222}

        await on_bot_added_to_chat(mock_chat_member_update, mock_bot)

        assert mock_bot.send_message.call_count == 2
