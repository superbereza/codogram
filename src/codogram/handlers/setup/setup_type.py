# src/codogram/handlers/setup/setup_type.py
"""Setup type selection handlers (Clone/Connect/New)."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_type")


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:clone"
)
async def on_clone_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Clone repository selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_clone_url)
    await state.update_data(setup_type="clone")

    # Import here to avoid circular imports
    from ...keyboards.setup.common import go_back_keyboard

    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:connect"
)
async def on_connect_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Connect to existing folder selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_folder_select)
    await state.update_data(setup_type="connect")

    # Import here to avoid circular imports
    from .connect_flow import show_folder_selection

    await show_folder_selection(callback.message, state, page=0)


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:new"
)
async def on_new_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Start new project selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_project_name)
    await state.update_data(setup_type="new")

    # Import here to avoid circular imports
    from .new_project_flow import show_project_name_prompt

    await show_project_name_prompt(callback.message, state)
