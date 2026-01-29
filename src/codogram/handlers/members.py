"""Handler for member join/leave events."""
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..telegram.sticker import StickerAdapter
from ..core.session_manager import project_manager, get_project_setting
from ..config import get_global_defaults
from ..services.emoji_pack import EmojiPackService
from ..services.group_auth import GroupAuthService
from ..telegram.queue import TelegramQueue
from .. import strings
from ..logging_config import logger

router = Router(name="members")


def _is_join(event: ChatMemberUpdated) -> bool:
    """Check if event is a member join."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    return old in ("left", "kicked", "restricted") and new in ("member", "administrator", "creator")


def _is_leave(event: ChatMemberUpdated) -> bool:
    """Check if event is a member leave."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    return old in ("member", "administrator", "creator") and new in ("left", "kicked")


def _is_leave_or_demotion(event: ChatMemberUpdated) -> bool:
    """Check if user left, was kicked, or was demoted from admin."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Left or kicked
    if new_status in ("left", "kicked"):
        return True

    # Demoted from admin/creator to regular member
    old_is_admin = old_status in ("administrator", "creator")
    new_is_admin = new_status in ("administrator", "creator")
    if old_is_admin and not new_is_admin:
        return True

    return False


@router.my_chat_member()
async def on_bot_status_changed(
    event: ChatMemberUpdated,
    group_auth: GroupAuthService,
) -> None:
    """Handle bot being added/removed from group."""
    chat_type = event.chat.type
    if chat_type not in ("group", "supergroup"):
        return

    new_status = event.new_chat_member.status

    if new_status in ("member", "administrator"):
        # Bot added to group - try to register
        logger.info(f"bot_added_to_group: chat_id={event.chat.id}")
        await group_auth.check_and_register(event.bot, event.chat.id)

    elif new_status in ("left", "kicked"):
        # Bot removed from group
        logger.info(f"bot_removed_from_group: chat_id={event.chat.id}")
        group_auth.on_bot_removed(event.chat.id)


@router.chat_member()
async def on_member_update(
    event: ChatMemberUpdated,
    telegram_queue: TelegramQueue,
    group_auth: GroupAuthService,
) -> None:
    """Handle member join/leave for emoji pack and group authorization."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    # --- Group authorization: check if admin left/demoted ---
    if _is_leave_or_demotion(event):
        deactivated = await group_auth.on_admin_left(
            event.bot, event.chat.id, user.id
        )
        if deactivated:
            logger.info(f"group_deactivated: chat_id={event.chat.id}")
            await telegram_queue.send(event.chat.id, strings.GROUP_DEACTIVATED)

    # --- Emoji pack: update stickers ---
    project = project_manager.get_by_chat(event.chat.id)
    if not project or not get_project_setting(project, "feat_avatar_pack", get_global_defaults()):
        return

    # Create service with adapter (layered architecture)
    adapter = StickerAdapter(event.bot)
    service = EmojiPackService(adapter)

    if _is_join(event):
        logger.info(f"Member joined, adding to emoji pack: {user.id}")
        await service.add_member(event.chat.id, user)

    elif _is_leave(event):
        logger.info(f"Member left, removing from emoji pack: {user.id}")
        await service.remove_member(event.chat.id, user.id)
