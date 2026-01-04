"""Telegram adapter - messaging utilities."""

from ..telegram_queue import TelegramQueue


async def send_with_retry(
    telegram_queue: TelegramQueue,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    message_thread_id: int | None = None,
    retries: int = 3,  # noqa: ARG001 - kept for backwards compat
) -> bool:
    """Send message with retry on rate limit.

    Args:
        telegram_queue: TelegramQueue instance for sending messages
        chat_id: Target chat ID
        text: Message text
        parse_mode: Telegram parse mode
        message_thread_id: Thread/topic ID if any
        retries: Deprecated - TelegramQueue handles retries internally

    Returns:
        True if sent successfully, False otherwise
    """
    result = await telegram_queue.send(
        chat_id=chat_id,
        text=text,
        thread_id=message_thread_id,
        parse_mode=parse_mode,
    )
    return len(result) > 0
