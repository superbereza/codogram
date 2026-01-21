"""Bot admin rights middleware - blocks messages until bot has admin rights."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..session_manager import project_manager
from ..services.setup import check_bot_admin_rights
from ..telegram.queue import TelegramQueue
from ..logging_config import logger
from .. import strings


class BotAdminRightsMiddleware(BaseMiddleware):
    """Block all messages/callbacks if project.awaiting_admin_rights is True.

    When bot loses admin rights (e.g., after group→supergroup migration),
    this middleware blocks all functionality until rights are restored.

    On each message, it also checks if rights were restored and clears the flag.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat_id = self._get_chat_id(event)
        if not chat_id:
            return await handler(event, data)

        project = project_manager.get_by_chat(chat_id)
        if not project:
            return await handler(event, data)

        if not project.awaiting_admin_rights:
            return await handler(event, data)

        # Project is waiting for admin rights - check if they were granted
        bot = data.get("bot")
        if bot:
            has_rights = await check_bot_admin_rights(bot, chat_id)
            if has_rights:
                # Rights restored! Clear flag and continue
                project.awaiting_admin_rights = False
                project_manager._save()
                logger.info(f"Admin rights restored for {project.project_name}")
                return await handler(event, data)

        # Still no rights - block with message
        await self._send_blocked_message(event, data)
        return None

    def _get_chat_id(self, event: TelegramObject) -> int | None:
        """Extract chat_id from event."""
        if isinstance(event, Message):
            return event.chat.id
        if isinstance(event, CallbackQuery) and event.message:
            return event.message.chat.id
        return None

    async def _send_blocked_message(
        self, event: TelegramObject, data: dict[str, Any]
    ) -> None:
        """Send blocking message to user."""
        telegram_queue: TelegramQueue | None = data.get("telegram_queue")

        if isinstance(event, Message) and telegram_queue:
            await telegram_queue.reply(event, strings.BOT_ADMIN_RIGHTS_BLOCKED)
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.BOT_ADMIN_RIGHTS_BLOCKED_POPUP,
                show_alert=True,
            )
