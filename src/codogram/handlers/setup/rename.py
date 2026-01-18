# src/codogram/handlers/setup/rename.py
"""Rename confirmation handlers."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ...services.setup.chat_rename import rename_chat_safe
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_rename")


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "rename:yes"
)
async def on_rename_yes(callback: CallbackQuery, state: FSMContext):
    """Confirm chat rename."""
    await callback.answer()

    data = await state.get_data()
    rename_to = data.get("rename_to")

    if rename_to:
        # Re-check admin rights before rename (per design line 537)
        from ...services.setup import check_bot_admin_rights
        has_rights = await check_bot_admin_rights(callback.bot, callback.message.chat.id)

        if not has_rights:
            # Warn and continue without rename
            await callback.message.answer(
                strings.SETUP_RENAME_FAILED,
                parse_mode="MarkdownV2",
            )
        else:
            # Try to rename
            success = await rename_chat_safe(
                callback.bot,
                callback.message.chat.id,
                rename_to,
            )

            if not success:
                # Warn but continue
                await callback.message.answer(
                    strings.SETUP_RENAME_FAILED,
                    parse_mode="MarkdownV2",
                )

    # Proceed to launch
    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "rename:no"
)
async def on_rename_no(callback: CallbackQuery, state: FSMContext):
    """Skip rename."""
    await callback.answer()

    # Proceed to launch
    from .launch import do_launch
    await do_launch(callback.message, state)
