# tests/services/test_chat_rename.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from codogram.services.setup.chat_rename import rename_chat_safe


@pytest.mark.asyncio
async def test_rename_chat_success():
    """rename_chat_safe returns True on success."""
    bot = AsyncMock()
    bot.set_chat_title = AsyncMock()

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is True
    bot.set_chat_title.assert_called_once()


@pytest.mark.asyncio
async def test_rename_chat_retry_after():
    """rename_chat_safe retries on TelegramRetryAfter."""
    bot = AsyncMock()

    # First call raises retry, second succeeds
    error = TelegramRetryAfter(method=MagicMock(), message="Retry after 1 seconds", retry_after=0.1)

    bot.set_chat_title = AsyncMock(side_effect=[error, None])

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is True
    assert bot.set_chat_title.call_count == 2


@pytest.mark.asyncio
async def test_rename_chat_bad_request_no_retry():
    """rename_chat_safe doesn't retry TelegramBadRequest."""
    bot = AsyncMock()

    error = TelegramBadRequest(method=MagicMock(), message="Not enough rights")
    bot.set_chat_title = AsyncMock(side_effect=error)

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is False
    assert bot.set_chat_title.call_count == 1  # No retry
