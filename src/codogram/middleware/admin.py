"""Admin middleware - global protection for all handlers."""
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from .. import strings
from ..config import settings
from ..logging_config import logger

if TYPE_CHECKING:
    from ..telegram.queue import TelegramQueue
    from ..services.group_auth import GroupAuthService

# Cache admin IDs
_admin_ids: set[int] | None = None


def get_admin_ids() -> set[int]:
    """Get admin IDs (cached)."""
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in get_admin_ids()


class AdminMiddleware(BaseMiddleware):
    """Block non-admins globally. Supports group authorization.

    Register on Dispatcher level (protects ALL routers):
        dp.message.middleware(AdminMiddleware(group_auth))
        dp.callback_query.middleware(AdminMiddleware(group_auth))
    """

    def __init__(self, group_auth: "GroupAuthService | None" = None):
        self.group_auth = group_auth

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Always allow migration messages (system messages about chat conversion)
        # These are critical for maintaining project state during group->supergroup migration
        if isinstance(event, Message):
            if event.migrate_to_chat_id or event.migrate_from_chat_id:
                logger.debug(f"middleware_bypass: migration message chat_id={event.chat.id}")
                return await handler(event, data)

        user: User | None = data.get("event_from_user")

        if user is None:
            return None

        # Ignore messages from bots (including service messages from self)
        if user.is_bot:
            return None

        chat = data.get("event_chat")

        # Unknown chat - ignore
        if chat is None:
            logger.debug("middleware_skip: chat is None")
            return None

        # Private chat - only ADMIN_IDS
        if chat.type == "private":
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        # Group/supergroup - check allowed_groups (if group_auth configured)
        if chat.type in ("group", "supergroup") and self.group_auth:

            # Re-validate after restart if needed
            if self.group_auth.needs_revalidation(chat.id):
                logger.debug(f"revalidating_group: chat_id={chat.id}")
                valid = await self.group_auth.revalidate(data["bot"], chat.id)
                if not valid:
                    logger.info(f"group_invalidated_on_revalidation: chat_id={chat.id}")
                    await self._reject_group(event, data)
                    return None
                return await handler(event, data)

            # Check if group is allowed
            if self.group_auth.is_allowed(chat.id):
                return await handler(event, data)

            # First contact - try to register
            registered = await self.group_auth.check_and_register(
                data["bot"], chat.id
            )
            if registered:
                logger.info(f"group_registered: chat_id={chat.id}")
                return await handler(event, data)

            # No admin from ADMIN_IDS in group - silently ignore.
            # The rejection message is sent once by on_bot_added when bot is first added.
            # We don't want to spam on every subsequent message.
            logger.debug(f"group_rejected_silent: chat_id={chat.id}")
            return None

        # Fallback for groups without group_auth - use old behavior (admin only)
        if chat.type in ("group", "supergroup"):
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        return None

    async def _reject_non_admin(
        self, event: TelegramObject, user_id: int, data: dict[str, Any]
    ):
        """Send rejection message with user's ID."""
        if isinstance(event, Message):
            telegram_queue: "TelegramQueue" = data["telegram_queue"]
            await telegram_queue.reply(
                event,
                strings.ERR_NOT_ADMIN.format(user_id=user_id),
            )
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.ERR_NOT_ADMIN_POPUP.format(user_id=user_id),
                show_alert=True
            )

    async def _reject_group(self, event: TelegramObject, data: dict[str, Any]):
        """Send rejection for unauthorized group."""
        if isinstance(event, Message):
            telegram_queue: "TelegramQueue" = data["telegram_queue"]
            await telegram_queue.reply(event, strings.ERR_GROUP_NOT_ALLOWED)
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.ERR_GROUP_NOT_ALLOWED_POPUP,
                show_alert=True
            )
