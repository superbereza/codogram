# src/codogram/services/setup/chat_rename.py
"""Chat rename service with retry logic."""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest, TelegramAPIError

logger = logging.getLogger(__name__)


async def rename_chat_safe(
    bot: Bot,
    chat_id: int,
    title: str,
    max_retries: int = 3,
) -> bool:
    """Try to rename chat with exponential backoff.

    Args:
        bot: Bot instance
        chat_id: Chat to rename
        title: New chat title
        max_retries: Maximum retry attempts

    Returns:
        True if renamed successfully, False otherwise
    """
    for attempt in range(max_retries):
        try:
            await bot.set_chat_title(chat_id, title)
            return True

        except TelegramRetryAfter as e:
            # Rate limited — wait and retry
            if attempt < max_retries - 1:
                logger.info(f"Rename rate limited, waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
                continue
            logger.warning(f"Rename failed after {max_retries} retries: rate limited")
            return False

        except TelegramBadRequest as e:
            # Not enough rights, chat title too long — no retry
            logger.warning(f"Rename failed: {e}")
            return False

        except TelegramAPIError as e:
            # Network error — retry with backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Rename failed ({e}), retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
                continue
            logger.warning(f"Rename failed after {max_retries} retries: {e}")
            return False

    return False
