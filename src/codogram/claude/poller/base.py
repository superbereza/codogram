# src/codogram/claude/poller/base.py
"""Base processor class with common helpers."""
from typing import TYPE_CHECKING

from ...telegram.queue import OutgoingBatch, EditBatch, DeleteBatch
from ...logging_config import logger

if TYPE_CHECKING:
    from .context import PollerContext


class BaseProcessor:
    """Base class for all poller processors."""

    def __init__(self, ctx: "PollerContext"):
        self.ctx = ctx

    async def process(self, screen: str) -> None:
        """Process screen content. Override in subclasses."""
        raise NotImplementedError

    async def send(self, text: str, parse_mode: str | None = None, **kwargs) -> list[int]:
        """Send message via queue."""
        messages = [{"text": text}]
        if parse_mode:
            messages[0]["parse_mode"] = parse_mode
        batch = OutgoingBatch(
            chat_id=self.ctx.chat_id,
            thread_id=self.ctx.thread_id,
            messages=messages,
            **kwargs,
        )
        return await self.ctx.queue.enqueue(batch)

    async def send_nowait(self, text: str, parse_mode: str | None = None, **kwargs) -> None:
        """Send message without waiting for result."""
        messages = [{"text": text}]
        if parse_mode:
            messages[0]["parse_mode"] = parse_mode
        batch = OutgoingBatch(
            chat_id=self.ctx.chat_id,
            thread_id=self.ctx.thread_id,
            messages=messages,
            **kwargs,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    async def edit_by_key(self, text: str, key: str) -> None:
        """Edit message by replace_key."""
        batch = EditBatch(
            chat_id=self.ctx.chat_id,
            message_id=0,
            text=text,
            replace_key=key,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    async def delete_by_key(self, key: str) -> None:
        """Delete message by replace_key."""
        batch = DeleteBatch(
            chat_id=self.ctx.chat_id,
            message_id=0,
            replace_key=key,
        )
        await self.ctx.queue.enqueue_nowait(batch)

    def log_debug(self, msg: str) -> None:
        """Log debug message with prefix."""
        logger.debug(f"{self.ctx.log_prefix}: {msg}")

    def log_info(self, msg: str) -> None:
        """Log info message with prefix."""
        logger.info(f"{self.ctx.log_prefix}: {msg}")

    def log_warning(self, msg: str) -> None:
        """Log warning message with prefix."""
        logger.warning(f"{self.ctx.log_prefix}: {msg}")
