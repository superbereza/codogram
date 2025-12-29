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


@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None


QueueItem = OutgoingBatch | EditBatch


@dataclass
class _InternalQueueItem:
    """Internal queue item with result future."""
    item: QueueItem
    result: asyncio.Future[list[int]] | None  # None for fire-and-forget


class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id.

    Thread-safe: uses locks to prevent race conditions when starting workers.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue[_QueueItem]] = defaultdict(asyncio.Queue)
        self._workers: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def enqueue(self, item: QueueItem) -> list[int]:
        """Add item to queue, wait for completion, return message IDs.

        Use this when you need to track sent message IDs (e.g., for cleanup).
        """
        chat_id = item.chat_id
        result_future: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
        queue_item = _InternalQueueItem(item=item, result=result_future)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(queue_item)
        return await result_future

    async def enqueue_nowait(self, item: QueueItem) -> None:
        """Add item to queue without waiting. Fire-and-forget.

        Use this when you don't need message IDs (e.g., watcher notifications).
        """
        chat_id = item.chat_id
        queue_item = _InternalQueueItem(item=item, result=None)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(queue_item)

    async def _worker(self, chat_id: int) -> None:
        """Process queue FIFO. Exits after 5 min idle."""
        queue = self._queues[chat_id]

        while True:
            try:
                queue_item = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                logger.debug(f"Queue worker {chat_id} exiting (idle timeout)")
                return

            try:
                if isinstance(queue_item.item, OutgoingBatch):
                    result_ids = await self._send_batch(queue_item.item)
                elif isinstance(queue_item.item, EditBatch):
                    result_ids = await self._edit_message(queue_item.item)
                else:
                    result_ids = []

                if queue_item.result is not None and not queue_item.result.done():
                    queue_item.result.set_result(result_ids)
            except Exception as e:
                logger.error(f"Queue operation failed chat_id={chat_id}: {e}")
                if queue_item.result is not None and not queue_item.result.done():
                    queue_item.result.set_exception(e)
            finally:
                queue.task_done()

    async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0) -> list[int]:
        """Send all messages in batch. Returns message IDs. Cleanup on failure."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(
                f"MESSAGE_LOST: Failed after {MAX_ATTEMPTS} attempts, "
                f"chat_id={batch.chat_id}, thread_id={batch.thread_id}, "
                f"messages={[m.get('text', '')[:50] for m in batch.messages]}"
            )
            return []

        sent_ids: list[int] = []

        try:
            for msg in batch.messages:
                result = await self.bot.send_message(
                    chat_id=batch.chat_id,
                    message_thread_id=batch.thread_id,
                    **msg,
                )
                sent_ids.append(result.message_id)
            return sent_ids

        except TelegramRetryAfter as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(
                f"Rate limited chat_id={batch.chat_id}, thread_id={batch.thread_id}, "
                f"waiting {e.retry_after}s, attempt {attempt + 1}/{MAX_ATTEMPTS}"
            )
            await asyncio.sleep(e.retry_after)
            return await self._send_batch(batch, attempt + 1)

        except TelegramBadRequest as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)

            # If parse error and we have parse_mode, retry without it
            if "parse entities" in str(e).lower():
                has_parse_mode = any(m.get("parse_mode") for m in batch.messages)
                if has_parse_mode:
                    logger.warning(
                        f"Parse error, retrying without parse_mode: chat_id={batch.chat_id}, "
                        f"thread_id={batch.thread_id}"
                    )
                    # Strip parse_mode from all messages
                    for msg in batch.messages:
                        msg.pop("parse_mode", None)
                    return await self._send_batch(batch, attempt + 1)

            logger.error(
                f"MESSAGE_LOST: BadRequest, chat_id={batch.chat_id}, thread_id={batch.thread_id}, "
                f"error={e}, messages={[m.get('text', '')[:50] for m in batch.messages]}"
            )
            return []

    async def _edit_message(self, edit: EditBatch, attempt: int = 0) -> list[int]:
        """Edit a single message. Returns [message_id] on success, [] on failure."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(
                f"EDIT_FAILED: Failed after {MAX_ATTEMPTS} attempts, "
                f"chat_id={edit.chat_id}, message_id={edit.message_id}"
            )
            return []

        try:
            await self.bot.edit_message_text(
                chat_id=edit.chat_id,
                message_id=edit.message_id,
                text=edit.text,
                parse_mode=edit.parse_mode,
            )
            return [edit.message_id]

        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited edit chat_id={edit.chat_id}, "
                f"waiting {e.retry_after}s, attempt {attempt + 1}/{MAX_ATTEMPTS}"
            )
            await asyncio.sleep(e.retry_after)
            return await self._edit_message(edit, attempt + 1)

        except TelegramBadRequest as e:
            # If parse error, retry without parse_mode
            if "parse entities" in str(e).lower() and edit.parse_mode:
                logger.warning(f"Parse error in edit, retrying without parse_mode")
                edit.parse_mode = None
                return await self._edit_message(edit, attempt + 1)

            # Message deleted or not found - not an error
            if "message to edit not found" in str(e).lower():
                logger.debug(f"Message {edit.message_id} not found, skipping edit")
                return []

            logger.warning(f"Edit failed chat_id={edit.chat_id}: {e}")
            return []

    async def _cleanup_orphans(self, chat_id: int, msg_ids: list[int]) -> None:
        """Delete partially sent messages."""
        for msg_id in msg_ids:
            try:
                await self.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    async def shutdown(self) -> None:
        """Stop all workers gracefully."""
        for task in self._workers.values():
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()
