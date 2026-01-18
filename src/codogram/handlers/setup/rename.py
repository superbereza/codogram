# src/codogram/handlers/setup/rename.py
"""Rename confirmation handlers."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ...services.setup.chat_rename import rename_chat_safe
from ...keyboards.setup import go_back_keyboard, setup_type_keyboard
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


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "rename:back"
)
async def on_rename_back(callback: CallbackQuery, state: FSMContext):
    """Go back from rename confirmation.

    Routes back based on setup_type:
    - clone: back to URL prompt
    - connect: back to folder selection
    - new: back to project name prompt
    """
    await callback.answer()

    data = await state.get_data()
    setup_type = data.get("setup_type")

    if setup_type == "clone":
        await state.set_state(SetupFlow.awaiting_clone_url)
        await callback.message.edit_text(
            strings.SETUP_CLONE_URL_PROMPT,
            reply_markup=go_back_keyboard("clone:back"),
        )
    elif setup_type == "connect":
        await state.set_state(SetupFlow.awaiting_folder_select)
        from .connect_flow import show_folder_selection
        await show_folder_selection(callback.message, state, page=0)
    elif setup_type == "new":
        await state.set_state(SetupFlow.awaiting_project_name)
        from .new_project_flow import show_project_name_prompt
        await show_project_name_prompt(callback.message, state)
    else:
        # Fallback to setup type selection
        await state.set_state(SetupFlow.awaiting_setup_type)
        await callback.message.edit_text(
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
