"""Admin middleware - global protection for all handlers."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from ..config import settings

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
    """Block non-admins globally. Shows their ID automatically.

    Register on Dispatcher level (protects ALL routers):
        dp.message.middleware(AdminMiddleware())
        dp.callback_query.middleware(AdminMiddleware())

    Non-admins receive their ID automatically - no /my_chat_id needed.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None:
            return None

        if is_admin(user.id):
            return await handler(event, data)

        # Non-admin: show helpful message with their ID
        await self._reject_non_admin(event, user.id)
        return None

    async def _reject_non_admin(self, event: TelegramObject, user_id: int):
        """Send rejection message with user's ID."""
        if hasattr(event, 'reply'):
            # Message - markdown with status indicator
            await event.reply(
                f"`\\[x\\]` Not admin\\. Your ID: `{user_id}`\n"
                f"Add to ADMIN\\_IDS in \\.env",
                parse_mode="MarkdownV2"
            )
        elif hasattr(event, 'answer'):
            # CallbackQuery - popup (no markdown, shorter)
            await event.answer(
                f"[x] Not admin. Your ID: {user_id}",
                show_alert=True
            )
