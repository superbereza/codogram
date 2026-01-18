# src/codogram/handlers/setup/connect_flow.py
"""Connect to existing folder flow handlers."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...config import settings
from ...domain.states import SetupFlow
from ...keyboards.setup import (
    setup_type_keyboard,
    folder_select_keyboard,
    connected_projects_keyboard,
    go_back_keyboard,
    FOLDERS_PER_PAGE,
)
from ...services.setup import list_available_folders, get_connected_folders, get_chat_link
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_connect")


async def show_folder_selection(message: Message, state: FSMContext, page: int = 0):
    """Show folder selection with pagination."""
    base_dir = Path(settings.base_dir).expanduser()
    connected = set(get_connected_folders().keys())

    folders = list_available_folders(base_dir, connected)

    if not folders:
        # No folders available
        if connected:
            text = strings.SETUP_FOLDER_ALL_CONNECTED
        else:
            text = strings.SETUP_FOLDER_EMPTY.format(base_dir=settings.base_dir)

        await message.edit_text(
            text,
            reply_markup=go_back_keyboard("folder:back"),
            parse_mode="MarkdownV2",
        )
        return

    # Calculate pagination
    total_pages = (len(folders) + FOLDERS_PER_PAGE - 1) // FOLDERS_PER_PAGE
    page = max(0, min(page, total_pages - 1))  # clamp

    start = page * FOLDERS_PER_PAGE
    end = start + FOLDERS_PER_PAGE
    page_folders = folders[start:end]

    await message.edit_text(
        strings.SETUP_FOLDER_SELECT,
        reply_markup=folder_select_keyboard(page_folders, page, total_pages),
    )


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data.startswith("folder:page:")
)
async def on_folder_page(callback: CallbackQuery, state: FSMContext):
    """Handle pagination buttons."""
    await callback.answer()

    page = int(callback.data.split(":")[-1])
    await show_folder_selection(callback.message, state, page)


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data.startswith("folder:select:")
)
async def on_folder_selected(callback: CallbackQuery, state: FSMContext):
    """Handle folder selection."""
    await callback.answer()

    folder_name = callback.data.split(":", 2)[-1]

    # Verify folder still exists
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / folder_name

    if not target_dir.exists():
        await callback.message.edit_text(
            strings.SETUP_FOLDER_NOT_FOUND.format(name=folder_name),
            reply_markup=go_back_keyboard("folder:back"),
            parse_mode="MarkdownV2",
        )
        return

    await state.update_data(
        project_name=folder_name,
        target_dir=str(target_dir),
    )

    # Check if rename needed
    chat_title = callback.message.chat.title or ""

    if chat_title != folder_name:
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=folder_name)

        from ...keyboards.setup.confirm import rename_confirm_keyboard
        await callback.message.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=folder_name),
            reply_markup=rename_confirm_keyboard(),
        )
    else:
        # Check git status
        await _check_git_and_proceed(callback.message, state, target_dir)


async def _check_git_and_proceed(message: Message, state: FSMContext, target_dir: Path):
    """Check if folder has git and proceed accordingly."""
    has_git = (target_dir / ".git").exists()

    if has_git:
        # Proceed directly to launch
        from .launch import do_launch
        await do_launch(message, state)
    else:
        # Ask about git
        await state.set_state(SetupFlow.awaiting_git_choice)

        from ...keyboards.setup.git_choice import git_choice_keyboard
        data = await state.get_data()
        folder_name = data["project_name"]

        await message.edit_text(
            strings.SETUP_GIT_CHOICE.format(folder=folder_name),
            reply_markup=git_choice_keyboard(),
        )


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data == "folder:view_connected"
)
async def on_view_connected(callback: CallbackQuery, state: FSMContext):
    """Show connected projects."""
    await callback.answer()
    await state.set_state(SetupFlow.viewing_connected_projects)

    connected = get_connected_folders()

    if not connected:
        text = f"{strings.SETUP_CONNECTED_HEADER}\n\n{strings.SETUP_CONNECTED_EMPTY}"
    else:
        lines = [strings.SETUP_CONNECTED_HEADER, ""]

        from ...session_manager import ProjectManager
        pm = ProjectManager()

        for folder_name, chat_id in connected.items():
            project = pm.projects.get(folder_name)
            # Use project name as title (we don't store chat_title in ProjectState)
            chat_title = folder_name
            # Detect chat type from chat_id format: -100xxx = supergroup
            chat_type = "supergroup" if str(chat_id).startswith("-100") else "group"

            link = get_chat_link(chat_id, chat_type)
            if link:
                lines.append(f"• {folder_name} → [{chat_title}]({link})")
            else:
                lines.append(f"• {folder_name} → {chat_title} {strings.SETUP_CONNECTED_NO_LINK}")

        lines.append("")
        lines.append(strings.SETUP_CONNECTED_TAP_HINT)
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=connected_projects_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


@router.callback_query(
    SetupFlow.viewing_connected_projects,
    F.data == "folder:back_connected"
)
async def on_back_from_connected(callback: CallbackQuery, state: FSMContext):
    """Go back to folder selection."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_folder_select)
    await show_folder_selection(callback.message, state, page=0)


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data == "folder:back"
)
async def on_folder_back(callback: CallbackQuery, state: FSMContext):
    """Go back to setup type selection."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.message(SetupFlow.awaiting_folder_select, F.text, ~F.text.startswith("/"))
async def on_folder_text_input(message: Message, state: FSMContext):
    """Handle text input during folder selection (not expected)."""
    await message.answer(
        strings.SETUP_FOLDER_USE_BUTTONS,
        parse_mode="MarkdownV2",
    )
