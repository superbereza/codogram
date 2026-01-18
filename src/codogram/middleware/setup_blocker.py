# src/codogram/middleware/setup_blocker.py
"""Middleware to block non-setup commands during setup flow."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from .. import strings

logger = logging.getLogger(__name__)

# Commands allowed during setup
ALLOWED_DURING_SETUP = {"/start", "/reset_all", "/help", "/get_debug_ids"}


class SetupBlockerMiddleware(BaseMiddleware):
    """Block commands during setup flow.

    Only allows /start, /reset_all, /help, /get_debug_ids while
    any SetupFlow state is active.
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Only process commands
        if not event.text or not event.text.startswith("/"):
            return await handler(event, data)

        # Get FSM state
        state = data.get("state")
        if not state:
            return await handler(event, data)

        current_state = await state.get_state()

        # Check if in setup flow
        if current_state and current_state.startswith("SetupFlow:"):
            # Extract command (without @botname suffix)
            command = event.text.split()[0].split("@")[0]

            if command not in ALLOWED_DURING_SETUP:
                logger.debug(f"Blocked {command} during setup")
                await event.answer(
                    strings.SETUP_COMMAND_BLOCKED,
                    parse_mode="MarkdownV2",
                )
                return

        return await handler(event, data)
