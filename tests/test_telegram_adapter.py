"""Tests for Telegram adapter."""
import pytest
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramRetryAfter

from codogram.adapters.telegram import send_with_retry


class TestSendWithRetry:
    """Tests for send_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Message sent successfully on first attempt."""
        mock_bot = AsyncMock()

        result = await send_with_retry(mock_bot, 123, "test message")

        assert result is True
        mock_bot.send_message.assert_called_once_with(
            123,
            "test message",
            parse_mode="Markdown",
            message_thread_id=None,
        )

    @pytest.mark.asyncio
    async def test_success_with_thread_id(self):
        """Message sent to specific thread."""
        mock_bot = AsyncMock()

        result = await send_with_retry(
            mock_bot, 123, "test", message_thread_id=456
        )

        assert result is True
        mock_bot.send_message.assert_called_once_with(
            123,
            "test",
            parse_mode="Markdown",
            message_thread_id=456,
        )

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Retries on rate limit and succeeds."""
        mock_bot = AsyncMock()
        # TelegramRetryAfter requires: method, message, retry_after
        error = TelegramRetryAfter(
            method=None,
            message="Rate limited",
            retry_after=0,  # Don't actually wait in tests
        )
        mock_bot.send_message.side_effect = [error, None]

        result = await send_with_retry(mock_bot, 123, "test", retries=2)

        assert result is True
        assert mock_bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_fail_after_max_retries(self):
        """Returns False after exhausting retries."""
        mock_bot = AsyncMock()
        error = TelegramRetryAfter(
            method=None,
            message="Rate limited",
            retry_after=0,
        )
        mock_bot.send_message.side_effect = error

        result = await send_with_retry(mock_bot, 123, "test", retries=2)

        assert result is False
        assert mock_bot.send_message.call_count == 2
