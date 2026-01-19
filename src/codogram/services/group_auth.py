"""Group authorization service."""
import asyncio

from aiogram import Bot

from ..config import (
    get_allowed_groups,
    add_allowed_group,
    remove_allowed_group,
)
from ..middleware.admin import get_admin_ids
from ..logging_config import logger

# Retry settings for race condition
CHECK_RETRY_DELAY = 0.3  # seconds
CHECK_RETRY_MAX = 3  # attempts


class GroupAuthService:
    """Manages group authorization based on admin membership."""

    def __init__(self):
        self._checking: set[int] = set()  # Groups being checked (race condition protection)
        self._validated_this_run: set[int] = set()  # Groups re-validated after restart

    def is_allowed(self, chat_id: int) -> bool:
        """Check if group is in allowed_groups."""
        return chat_id in get_allowed_groups()

    def needs_revalidation(self, chat_id: int) -> bool:
        """Check if group needs re-validation (first message after restart)."""
        return chat_id in get_allowed_groups() and chat_id not in self._validated_this_run

    async def check_and_register(self, bot: Bot, chat_id: int) -> bool:
        """Check group admins, register if valid.

        Returns True if group was registered (or already was).
        Returns False if no admin from ADMIN_IDS found.

        Race condition handling: if already checking this group, wait and retry.
        """
        # If already checking, wait for it to complete
        for attempt in range(CHECK_RETRY_MAX):
            if chat_id not in self._checking:
                break
            logger.debug(f"group_check_waiting: chat_id={chat_id} attempt={attempt + 1}")
            await asyncio.sleep(CHECK_RETRY_DELAY)
            # After waiting, check if group was registered
            if self.is_allowed(chat_id):
                return True
        else:
            # Still checking after max retries - reject
            logger.warning(f"group_check_timeout: chat_id={chat_id}")
            return False

        self._checking.add(chat_id)
        try:
            if await self._has_our_admin(bot, chat_id):
                add_allowed_group(chat_id)
                self._validated_this_run.add(chat_id)
                logger.info(f"group_registered: chat_id={chat_id}")
                return True
            return False
        finally:
            self._checking.discard(chat_id)

    async def revalidate(self, bot: Bot, chat_id: int) -> bool:
        """Re-validate group after restart.

        Returns True if still valid, False if deactivated.
        """
        self._validated_this_run.add(chat_id)

        if await self._has_our_admin(bot, chat_id):
            return True

        remove_allowed_group(chat_id)
        logger.info(f"group_invalidated_on_revalidation: chat_id={chat_id}")
        return False

    async def on_admin_left(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """Handle admin leaving or being demoted.

        If user_id in ADMIN_IDS, re-check group.
        Returns True if group was deactivated.
        """
        if user_id not in get_admin_ids():
            return False

        if await self._has_our_admin(bot, chat_id):
            return False

        remove_allowed_group(chat_id)
        logger.info(f"group_deactivated: chat_id={chat_id}")
        return True

    def on_bot_removed(self, chat_id: int) -> None:
        """Handle bot being removed from group."""
        remove_allowed_group(chat_id)
        self._validated_this_run.discard(chat_id)
        logger.info(f"bot_removed_from_group: chat_id={chat_id}")

    async def _has_our_admin(self, bot: Bot, chat_id: int) -> bool:
        """Check if group has at least one admin from ADMIN_IDS."""
        try:
            admins = await bot.get_chat_administrators(chat_id)
            admin_ids = get_admin_ids()
            for admin in admins:
                if admin.user.id in admin_ids:
                    return True
            return False
        except Exception as e:
            logger.warning(f"failed_to_get_admins: chat_id={chat_id} error={e}")
            return False
