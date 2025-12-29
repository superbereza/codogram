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
class _QueueItem:
    """Internal queue item with result future."""
    batch: OutgoingBatch
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

    async def enqueue(self, batch: OutgoingBatch) -> list[int]:
        """Add batch to queue, wait for send, return message IDs.

        Use this when you need to track sent message IDs (e.g., for cleanup).
        """
        chat_id = batch.chat_id
        result_future: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
        item = _QueueItem(batch=batch, result=result_future)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(item)
        return await result_future

    async def enqueue_nowait(self, batch: OutgoingBatch) -> None:
        """Add batch to queue without waiting. Fire-and-forget.

        Use this when you don't need message IDs (e.g., watcher notifications).
        """
        chat_id = batch.chat_id
        item = _QueueItem(batch=batch, result=None)  # None for fire-and-forget

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(item)

    async def _worker(self, chat_id: int) -> None:
        """Process queue FIFO. Exits after 5 min idle."""
        queue = self._queues[chat_id]

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                logger.debug(f"Queue worker {chat_id} exiting (idle timeout)")
                return

            try:
                sent_ids = await self._send_batch(item.batch)
                if item.result is not None and not item.result.done():
                    item.result.set_result(sent_ids)
            except Exception as e:
                logger.error(f"Queue send failed chat_id={item.batch.chat_id}: {e}")
                if item.result is not None and not item.result.done():
                    item.result.set_exception(e)
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
            logger.error(
                f"MESSAGE_LOST: BadRequest, chat_id={batch.chat_id}, thread_id={batch.thread_id}, "
                f"error={e}, messages={[m.get('text', '')[:50] for m in batch.messages]}"
            )
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
