"""Normalize command case middleware."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class NormalizeCommandMiddleware(BaseMiddleware):
    """Normalize command text to lowercase.

    Converts /Branch, /HELP, /New to /branch, /help, /new
    so that Command() filters match regardless of case.

    Register FIRST on message middleware (before other middlewares):
        dp.message.outer_middleware(NormalizeCommandMiddleware())
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            # Split command from arguments: "/Branch arg1 arg2" -> ["/Branch", "arg1 arg2"]
            parts = event.text.split(None, 1)
            if parts:
                command = parts[0].lower()  # "/Branch" -> "/branch"
                args = parts[1] if len(parts) > 1 else ""
                # Reconstruct: "/branch arg1 arg2"
                event.text = f"{command} {args}".rstrip()

        return await handler(event, data)
