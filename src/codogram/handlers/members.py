"""Handler for member join/leave events."""
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..adapters.sticker import StickerAdapter
from ..session_manager import project_manager
from ..services.emoji_pack import EmojiPackService
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


@router.chat_member()
async def on_member_update(event: ChatMemberUpdated) -> None:
    """Handle member join/leave for emoji pack updates."""
    project = project_manager.get_by_chat(event.chat.id)
    if not project or not project.feat_avatar_pack:
        return

    user = event.new_chat_member.user
    if user.is_bot:
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
