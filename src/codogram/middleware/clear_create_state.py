"""Middleware to clear create flow state when command is received."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from ..handlers.common import clear_flow_state_by_type


class ClearCreateStateMiddleware(BaseMiddleware):
    """Clear awaiting_create_name state when any command is received.

    This prevents stale prompts: if user sends /branch, then /help,
    then types a name - it won't accidentally create a branch.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Only process text messages that are commands
        if event.text and event.text.startswith("/"):
            clear_flow_state_by_type(
                event.chat.id,
                event.message_thread_id,
                "awaiting_create_name",
            )

        return await handler(event, data)
