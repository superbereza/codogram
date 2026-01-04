"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router(name="common")

# State dict for thread_create flow (threads.py uses this)
# TODO: Migrate to aiogram FSM in future
_flow_state: dict[int, dict] = {}


async def require_forum_group(message: Message) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await message.answer("`[!]` This command requires a group with topics.", parse_mode="MarkdownV2")
        return False
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required. Enable in group settings -> Topics", parse_mode="MarkdownV2")
        return False
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer()
