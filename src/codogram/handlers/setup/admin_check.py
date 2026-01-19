# src/codogram/handlers/setup/admin_check.py
"""Admin rights check handlers."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated

from ...domain.states import SetupFlow
from ...services.setup import check_bot_admin_rights
from ...keyboards.setup import admin_check_keyboard, setup_type_keyboard
from ...utils import is_stale_callback
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_admin_check")


@router.callback_query(
    SetupFlow.awaiting_admin_rights,
    F.data == "admin:check"
)
async def on_check_rights(callback: CallbackQuery, state: FSMContext):
    """Handle Check rights button press."""
    # Ignore stale buttons (>5 min old per design)
    if is_stale_callback(callback.message.date):
        await callback.answer("Button expired, use /start")
        return

    chat_id = callback.message.chat.id
    bot = callback.bot

    has_rights = await check_bot_admin_rights(bot, chat_id)

    if has_rights:
        # Proceed to setup type selection
        await state.set_state(SetupFlow.awaiting_setup_type)
        await callback.message.edit_text(
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
        await callback.answer()
    else:
        # Still no rights - show toast notification
        await callback.answer(strings.SETUP_ADMIN_CHECK_FAILED, show_alert=True)


@router.my_chat_member(
    SetupFlow.awaiting_admin_rights,
    F.new_chat_member.status == "administrator"
)
async def on_admin_granted(event: ChatMemberUpdated, state: FSMContext):
    """Handle bot being granted admin rights while waiting."""
    chat = event.chat
    bot = event.bot

    # Verify the rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    if has_rights:
        await state.set_state(SetupFlow.awaiting_setup_type)
        await bot.send_message(
            chat.id,
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
