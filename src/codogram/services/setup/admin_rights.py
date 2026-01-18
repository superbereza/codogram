"""Admin rights checking service."""
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)


async def check_bot_admin_rights(bot: Bot, chat_id: int) -> bool:
    """Check if bot has required admin rights (can_change_info)."""
    try:
        member = await bot.get_chat_member(chat_id, bot.id)

        if member.status not in ("administrator", "creator"):
            return False

        if hasattr(member, 'can_change_info') and not member.can_change_info:
            return False

        return True
    except Exception as e:
        logger.warning(f"Failed to check admin rights for chat {chat_id}: {e}")
        return False
