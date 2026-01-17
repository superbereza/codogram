# src/codogram/telegram_queue.py
"""Rate-limited Telegram message queue with FIFO ordering per chat_id."""
import asyncio
import collections
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import telegramify_markdown
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

if TYPE_CHECKING:
    from aiogram.types import Message

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
    messages: list[dict]  # [{text, parse_mode}, ...]
    reply_markup: InlineKeyboardMarkup | None = None  # Applied to LAST message
    replace_key: str | None = None  # If set, replaces previous batch with same key


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
class DeleteBatch:
    """Delete message operation."""
    chat_id: int
    message_id: int


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


@dataclass
class _DeleteQueueItem:
    """Internal queue item for delete operations."""
    batch: DeleteBatch
    result: asyncio.Future[None] | None


class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id.

    Thread-safe: uses locks to prevent race conditions when starting workers.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, collections.deque] = defaultdict(collections.deque)
        self._queue_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._queue_events: dict[int, asyncio.Event] = defaultdict(asyncio.Event)
        self._workers: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.sent_statuses: dict[str, int] = {}  # replace_key -> msg_id

    async def enqueue(self, batch: OutgoingBatch | EditBatch | KeyboardBatch | DeleteBatch, timeout: float = 120.0) -> list[int] | None:
        """Add batch to queue, wait for send.

        For OutgoingBatch: returns list of sent message IDs.
        For EditBatch: returns None (edit doesn't create new messages).
        For KeyboardBatch: returns list with single message ID.
        For DeleteBatch: returns None (delete doesn't create new messages).

        Args:
            batch: The batch to send.
            timeout: Maximum seconds to wait for send to complete. Defaults to 120.0.

        Raises:
            TelegramQueueTimeout: If the operation times out.
        """
        chat_id = batch.chat_id

        if isinstance(batch, DeleteBatch):
            result_future_del: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            item: _QueueItem | _EditQueueItem | _KeyboardQueueItem | _DeleteQueueItem = _DeleteQueueItem(batch=batch, result=result_future_del)
        elif isinstance(batch, EditBatch):
            result_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            item = _EditQueueItem(batch=batch, result=result_future)
        elif isinstance(batch, KeyboardBatch):
            result_future_kb: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
            item = _KeyboardQueueItem(batch=batch, result=result_future_kb)
        else:
            result_future_send: asyncio.Future[list[int]] = asyncio.get_running_loop().create_future()
            item = _QueueItem(batch=batch, result=result_future_send)

        async with self._queue_locks[chat_id]:
            self._queues[chat_id].append(item)
            self._queue_events[chat_id].set()

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        try:
            if isinstance(batch, DeleteBatch):
                await asyncio.wait_for(result_future_del, timeout=timeout)
                return None
            elif isinstance(batch, EditBatch):
                await asyncio.wait_for(result_future, timeout=timeout)
                return None
            elif isinstance(batch, KeyboardBatch):
                return await asyncio.wait_for(result_future_kb, timeout=timeout)
            else:
                return await asyncio.wait_for(result_future_send, timeout=timeout)
        except asyncio.TimeoutError as e:
            raise TelegramQueueTimeout(f"Enqueue operation timed out after {timeout}s") from e

    async def enqueue_nowait(self, batch: OutgoingBatch | EditBatch | KeyboardBatch | DeleteBatch) -> None:
        """Add batch to queue without waiting. Fire-and-forget.

        Use this when you don't need message IDs (e.g., watcher notifications).
        """
        chat_id = batch.chat_id

        # Create queue item
        if isinstance(batch, DeleteBatch):
            item: _QueueItem | _EditQueueItem | _KeyboardQueueItem | _DeleteQueueItem = _DeleteQueueItem(batch=batch, result=None)
        elif isinstance(batch, EditBatch):
            item = _EditQueueItem(batch=batch, result=None)
        elif isinstance(batch, KeyboardBatch):
            item = _KeyboardQueueItem(batch=batch, result=None)
        else:
            item = _QueueItem(batch=batch, result=None)

        async with self._queue_locks[chat_id]:
            # Replace existing item with same replace_key
            if isinstance(batch, OutgoingBatch) and batch.replace_key:
                queue = self._queues[chat_id]
                for i, existing in enumerate(queue):
                    if (isinstance(existing, _QueueItem) and
                        isinstance(existing.batch, OutgoingBatch) and
                        existing.batch.replace_key == batch.replace_key):
                        queue[i] = item
                        self._queue_events[chat_id].set()
                        # Start worker if needed (outside lock)
                        break
                else:
                    # No existing item found, append new
                    self._queues[chat_id].append(item)
                    self._queue_events[chat_id].set()
            else:
                self._queues[chat_id].append(item)
                self._queue_events[chat_id].set()

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

    async def _worker(self, chat_id: int) -> None:
        """Process queue FIFO. Exits after 5 min idle."""
        queue = self._queues[chat_id]
        event = self._queue_events[chat_id]

        while True:
            # Wait for items or timeout
            try:
                await asyncio.wait_for(event.wait(), timeout=300)
            except asyncio.TimeoutError:
                logger.debug(f"Queue worker {chat_id} exiting (idle timeout)")
                return

            # Process all available items
            while True:
                async with self._queue_locks[chat_id]:
                    if not queue:
                        event.clear()
                        break
                    item = queue.popleft()

                try:
                    if isinstance(item, _DeleteQueueItem):
                        await self._delete_message(item.batch)
                        if item.result is not None and not item.result.done():
                            item.result.set_result(None)
                    elif isinstance(item, _EditQueueItem):
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

        # Convert GFM to MarkdownV2 BEFORE chunking (escaping can increase length)
        converted_messages = []
        for msg in batch.messages:
            if msg.get("parse_mode") == "MarkdownV2":
                try:
                    msg = {**msg, "text": telegramify_markdown.markdownify(
                        msg.get("text", ""),
                        max_line_length=None,
                        normalize_whitespace=False
                    )}
                except Exception as e:
                    logger.warning(f"markdownify failed: {e}")
            converted_messages.append(msg)

        # Expand messages with chunking (after conversion)
        expanded_messages = []
        for msg in converted_messages:
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
            for i, msg in enumerate(expanded_messages):
                is_last = (i == len(expanded_messages) - 1)

                # Apply batch-level reply_markup to the last message
                send_kwargs = {**msg}
                if is_last and batch.reply_markup:
                    send_kwargs["reply_markup"] = batch.reply_markup

                result = await self.bot.send_message(
                    chat_id=batch.chat_id,
                    message_thread_id=batch.thread_id,
                    **send_kwargs,
                )
                sent_ids.append(result.message_id)

            # Track sent message ID by replace_key for later edit/delete
            if sent_ids and batch.replace_key:
                self.sent_statuses[batch.replace_key] = sent_ids[-1]

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

    async def _delete_message(self, batch: DeleteBatch) -> None:
        """Delete a message. Silently ignores errors (message already deleted)."""
        try:
            await self.bot.delete_message(batch.chat_id, batch.message_id)
        except Exception as e:
            logger.debug(f"Delete failed (message likely already deleted): {e}")

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

    async def reply(
        self,
        message: "Message",
        text: str,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: "InlineKeyboardMarkup | None" = None,
    ) -> list[int]:
        """Reply to a message through queue."""
        msg_dict: dict = {"text": text}
        if parse_mode:
            msg_dict["parse_mode"] = parse_mode
        if reply_markup:
            msg_dict["reply_markup"] = reply_markup

        batch = OutgoingBatch(
            chat_id=message.chat.id,
            thread_id=message.message_thread_id,
            messages=[msg_dict],
        )
        return await self.enqueue(batch)

    async def send(
        self,
        chat_id: int,
        text: str,
        thread_id: int | None = None,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: "InlineKeyboardMarkup | None" = None,
    ) -> list[int]:
        """Send message to chat through queue."""
        msg_dict: dict = {"text": text}
        if parse_mode:
            msg_dict["parse_mode"] = parse_mode
        if reply_markup:
            msg_dict["reply_markup"] = reply_markup

        batch = OutgoingBatch(
            chat_id=chat_id,
            thread_id=thread_id,
            messages=[msg_dict],
        )
        return await self.enqueue(batch)

    async def edit(
        self,
        message: "Message",
        text: str,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: "InlineKeyboardMarkup | None" = None,
    ) -> None:
        """Edit a message through queue."""
        batch = EditBatch(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        await self.enqueue(batch)
