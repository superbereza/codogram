"""Tests for Telegram adapter."""
import pytest
from unittest.mock import AsyncMock

from codogram.adapters.telegram import send_with_retry


class TestSendWithRetry:
    """Tests for send_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Message sent successfully on first attempt."""
        mock_queue = AsyncMock()
        mock_queue.send.return_value = [123]  # Message ID returned

        result = await send_with_retry(mock_queue, 123, "test message")

        assert result is True
        mock_queue.send.assert_called_once_with(
            chat_id=123,
            text="test message",
            thread_id=None,
            parse_mode="MarkdownV2",
        )

    @pytest.mark.asyncio
    async def test_success_with_thread_id(self):
        """Message sent to specific thread."""
        mock_queue = AsyncMock()
        mock_queue.send.return_value = [456]

        result = await send_with_retry(
            mock_queue, 123, "test", message_thread_id=456
        )

        assert result is True
        mock_queue.send.assert_called_once_with(
            chat_id=123,
            text="test",
            thread_id=456,
            parse_mode="MarkdownV2",
        )

    @pytest.mark.asyncio
    async def test_returns_true_when_message_sent(self):
        """Returns True when telegram_queue.send returns message IDs."""
        mock_queue = AsyncMock()
        mock_queue.send.return_value = [789]

        result = await send_with_retry(mock_queue, 123, "test")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_messages_sent(self):
        """Returns False when telegram_queue.send returns empty list."""
        mock_queue = AsyncMock()
        mock_queue.send.return_value = []  # No messages sent (queue handles retries internally)

        result = await send_with_retry(mock_queue, 123, "test")

        assert result is False
