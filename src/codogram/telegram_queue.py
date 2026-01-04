# src/codogram/telegram_queue.py
"""Rate-limited Telegram message queue with FIFO ordering per chat_id."""
import asyncio
from collections import defaultdict
from dataclasses import dataclass

import telegramify_markdown
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from .logging_config import logger
from .chunker import chunk_message


class TelegramQueueTimeout(Exception):
    """Raised when queue operation times out."""
    pass


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
    reply_markup: InlineKeyboardMarkup | None = None


@dataclass
class KeyboardBatch:
    """Keyboard message with reply markup."""
    chat_id: int
    text: str
    reply_markup: InlineKeyboardMarkup
    thread_id: int | None = None


@dataclass
class _QueueItem:
    """Internal queue item with result future."""
    batch: OutgoingBatch
    result: asyncio.Future[list[int]] | None  # None for fire-and-forget


@dataclass
class _EditQueueItem:
    """Internal queue item for edit operations."""
    batch: EditBatch
    result: asyncio.Future[None] | None  # None for fire-and-forget


@dataclass
class _KeyboardQueueItem:
    """Internal queue item for keyboard messages."""
    batch: KeyboardBatch
    result: asyncio.Future[list[int]] | None


class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id.

    Thread-safe: uses locks to prevent race conditions when starting workers.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue[_QueueItem | _EditQueueItem | _KeyboardQueueItem]] = defaultdict(asyncio.Queue)
        self._workers: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def enqueue(self, batch: OutgoingBatch | EditBatch | KeyboardBatch, timeout: float = 30.0) -> list[int] | None:
        """Add batch to queue, wait for send.

        For OutgoingBatch: returns list of sent message IDs.
        For EditBatch: returns None (edit doesn't create new messages).
        For KeyboardBatch: returns list with single message ID.

        Args:
            batch: The batch to send.
            timeout: Maximum seconds to wait for send to complete. Defaults to 30.0.

        Raises:
            TelegramQueueTimeout: If the operation times out.
        """
        chat_id = batch.chat_id

        if isinstance(batch, EditBatch):
            result_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            item: _QueueItem | _EditQueueItem | _KeyboardQueueItem = _EditQueueItem(batch=batch, result=result_future)
        elif isinstance(batch, KeyboardBatch):
            result_future_kb: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
            item = _KeyboardQueueItem(batch=batch, result=result_future_kb)
        else:
            result_future_send: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
            item = _QueueItem(batch=batch, result=result_future_send)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(item)

        try:
            if isinstance(batch, EditBatch):
                await asyncio.wait_for(result_future, timeout=timeout)
                return None
            elif isinstance(batch, KeyboardBatch):
                return await asyncio.wait_for(result_future_kb, timeout=timeout)
            else:
                return await asyncio.wait_for(result_future_send, timeout=timeout)
        except asyncio.TimeoutError as e:
            raise TelegramQueueTimeout(f"Enqueue operation timed out after {timeout}s") from e

    async def enqueue_nowait(self, batch: OutgoingBatch | EditBatch | KeyboardBatch) -> None:
        """Add batch to queue without waiting. Fire-and-forget.

        Use this when you don't need message IDs (e.g., watcher notifications).
        """
        chat_id = batch.chat_id

        if isinstance(batch, EditBatch):
            item: _QueueItem | _EditQueueItem | _KeyboardQueueItem = _EditQueueItem(batch=batch, result=None)
        elif isinstance(batch, KeyboardBatch):
            item = _KeyboardQueueItem(batch=batch, result=None)
        else:
            item = _QueueItem(batch=batch, result=None)

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
                if isinstance(item, _EditQueueItem):
                    await self._edit_message(item.batch)
                    if item.result is not None and not item.result.done():
                        item.result.set_result(None)
                elif isinstance(item, _KeyboardQueueItem):
                    sent_ids = await self._send_keyboard(item.batch)
                    if item.result is not None and not item.result.done():
                        item.result.set_result(sent_ids)
                else:
                    sent_ids = await self._send_batch(item.batch)
                    if item.result is not None and not item.result.done():
                        item.result.set_result(sent_ids)
            except Exception as e:
                logger.error(f"Queue operation failed chat_id={item.batch.chat_id}: {e}")
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

        # Expand messages with chunking
        expanded_messages = []
        for msg in batch.messages:
            text = msg.get("text", "")
            if len(text) > 4000:
                chunks = chunk_message(text)
                logger.debug(f"Chunking message: {len(text)} chars -> {len(chunks)} chunks")
                for chunk in chunks:
                    expanded_messages.append({**msg, "text": chunk})
            else:
                expanded_messages.append(msg)

        sent_ids: list[int] = []

        try:
            for msg in expanded_messages:
                # Convert GFM to MarkdownV2 using telegramify-markdown
                if msg.get("parse_mode") == "MarkdownV2":
                    try:
                        msg["text"] = telegramify_markdown.markdownify(
                            msg.get("text", ""),
                            max_line_length=None,
                            normalize_whitespace=False
                        )
                    except Exception as e:
                        logger.warning(f"markdownify failed: {e}")

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

    async def _edit_message(self, batch: EditBatch, attempt: int = 0) -> None:
        """Edit a message. Handles rate limits and parse errors."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(
                f"Edit failed after {MAX_ATTEMPTS} attempts, "
                f"chat_id={batch.chat_id}, message_id={batch.message_id}"
            )
            return

        # Apply telegramify for MarkdownV2
        text = batch.text
        if batch.parse_mode == "MarkdownV2":
            try:
                text = telegramify_markdown.markdownify(
                    text,
                    max_line_length=None,
                    normalize_whitespace=False
                )
            except Exception as e:
                logger.warning(f"markdownify failed on edit: {e}")

        try:
            await self.bot.edit_message_text(
                chat_id=batch.chat_id,
                message_id=batch.message_id,
                text=text,
                parse_mode=batch.parse_mode,
                reply_markup=batch.reply_markup,
            )
        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited on edit chat_id={batch.chat_id}, message_id={batch.message_id}, "
                f"waiting {e.retry_after}s, attempt {attempt + 1}/{MAX_ATTEMPTS}"
            )
            await asyncio.sleep(e.retry_after)
            await self._edit_message(batch, attempt + 1)
        except TelegramBadRequest as e:
            # Handle parse errors - retry without parse_mode
            if "parse entities" in str(e).lower() and batch.parse_mode:
                logger.warning(
                    f"Parse error on edit, retrying without parse_mode: "
                    f"chat_id={batch.chat_id}, message_id={batch.message_id}"
                )
                batch.parse_mode = None
                await self._edit_message(batch, attempt + 1)
            else:
                # Message deleted or other error, ignore silently
                logger.debug(
                    f"Edit failed (message likely deleted): chat_id={batch.chat_id}, "
                    f"message_id={batch.message_id}, error={e}"
                )

    async def _send_keyboard(self, batch: KeyboardBatch) -> list[int]:
        """Send keyboard message."""
        try:
            msg = await self.bot.send_message(
                batch.chat_id,
                batch.text,
                reply_markup=batch.reply_markup,
                message_thread_id=batch.thread_id,
            )
            return [msg.message_id]
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self._send_keyboard(batch)
        except Exception as e:
            logger.error(f"keyboard_send_error: {e}")
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
