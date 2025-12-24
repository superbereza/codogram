# src/telegram_bridge/streamer.py
import asyncio
import time
from aiogram import Bot
from aiogram.types import Message


class EditMessageStreamer:
    """Stream text by editing message in place."""

    def __init__(self, bot: Bot, chat_id: int, min_edit_interval: float = 1.0):
        self.bot = bot
        self.chat_id = chat_id
        self.min_edit_interval = min_edit_interval
        self.message: Message | None = None
        self.buffer = ""
        self.last_edit = 0.0

    async def append(self, text: str, force: bool = False):
        """Append text to buffer and update message if interval passed."""
        self.buffer = text  # Replace buffer (each entry is full text)
        now = time.time()

        if self.message is None:
            self.message = await self.bot.send_message(
                self.chat_id,
                f"◐ {self.buffer[:4000]}"
            )
            self.last_edit = now
        elif force or (now - self.last_edit >= self.min_edit_interval):
            try:
                await self.message.edit_text(f"◐ {self.buffer[:4000]}")
                self.last_edit = now
            except Exception:
                pass  # Message unchanged or other error

    async def complete(self):
        """Mark message as complete with ✓ symbol."""
        if self.message and self.buffer:
            try:
                await self.message.edit_text(f"✓ {self.buffer[:4000]}")
            except Exception:
                pass
        self.message = None
        self.buffer = ""

    def reset(self):
        """Reset state for new response."""
        self.message = None
        self.buffer = ""
