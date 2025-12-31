"""Telegram adapter - messaging utilities."""
import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from ..logging_config import logger


async def send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    message_thread_id: int | None = None,
    retries: int = 3,
) -> bool:
    """Send message with retry on rate limit.

    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        text: Message text
        parse_mode: Telegram parse mode
        message_thread_id: Thread/topic ID if any
        retries: Max retry attempts

    Returns:
        True if sent successfully, False otherwise
    """
    for attempt in range(retries):
        try:
            await bot.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                message_thread_id=message_thread_id,
            )
            return True
        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited, retrying in {e.retry_after}s "
                f"(attempt {attempt + 1}/{retries})"
            )
            await asyncio.sleep(e.retry_after + 1)

    logger.error("Failed to send message after retries")
    return False
