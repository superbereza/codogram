"""Tests for DM handlers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_message():
    """Create mock DM message."""
    msg = MagicMock()
    msg.chat.type = "private"
    msg.chat.id = 123456
    msg.from_user.id = 123456
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_telegram_queue():
    """Create mock telegram queue."""
    tq = MagicMock()
    tq.send = AsyncMock()
    tq.edit = AsyncMock()
    return tq


@pytest.mark.asyncio
async def test_dm_start_shows_onboarding_for_new_user(mock_message, mock_telegram_queue):
    """New user should see onboarding flow."""
    from codogram.handlers.dm import handle_dm_start

    with patch("codogram.handlers.dm.get_user_onboarded", return_value=False), \
         patch("codogram.handlers.dm.run_onboarding") as mock_onboarding:
        mock_onboarding.return_value = None

        await handle_dm_start(mock_message, mock_telegram_queue)

        mock_onboarding.assert_called_once()


@pytest.mark.asyncio
async def test_dm_start_shows_mini_status_for_onboarded_user(mock_message, mock_telegram_queue):
    """Onboarded user should see mini status."""
    from codogram.handlers.dm import handle_dm_start

    with patch("codogram.handlers.dm.get_user_onboarded", return_value=True), \
         patch("codogram.handlers.dm.show_mini_status") as mock_status:
        mock_status.return_value = None

        await handle_dm_start(mock_message, mock_telegram_queue)

        mock_status.assert_called_once()
