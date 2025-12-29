# src/codogram/telegram_queue.py
"""Rate-limited Telegram message queue with FIFO ordering per chat_id."""
import asyncio
from collections import defaultdict
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from .logging_config import logger


@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]  # [{text, parse_mode, reply_markup?}, ...]
