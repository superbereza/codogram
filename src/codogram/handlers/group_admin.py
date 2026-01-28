"""Admin handlers for group approval/rejection."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..config import add_allowed_group
from ..logging_config import logger
from .. import strings

router = Router(name="group_admin")


@router.callback_query(F.data.startswith("grp:"))
async def on_group_action(callback: CallbackQuery):
    """Handle group approve/reject from admin alert."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    action = parts[1]  # approve or reject
    try:
        chat_id = int(parts[2])
    except ValueError:
        await callback.answer("Invalid chat ID")
        return

    if action == "approve":
        add_allowed_group(chat_id)
        logger.info(f"group_approved_by_admin: chat_id={chat_id}")

        # Update message
        await callback.message.edit_text(
            strings.ADMIN_GROUP_APPROVED.format(chat_title=f"`{chat_id}`"),
            parse_mode="MarkdownV2",
        )
        await callback.answer("Group approved!")

    elif action == "reject":
        logger.info(f"group_rejected_by_admin: chat_id={chat_id}")

        # Just remove the message
        await callback.message.delete()
        await callback.answer("Dismissed")

    else:
        await callback.answer("Unknown action")
