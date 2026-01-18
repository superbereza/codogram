# src/codogram/handlers/setup/new_project_flow.py
"""New project flow handlers."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from ...config import settings
from ...domain.states import SetupFlow
from ...domain.validators import sanitize_project_name
from ...keyboards.setup import setup_type_keyboard, go_back_keyboard
from ...keyboards.setup.git_choice import git_choice_keyboard
from ...keyboards.setup.confirm import rename_confirm_keyboard
from ...keyboards.setup.common import folder_exists_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_new_project")


async def show_project_name_prompt(message: Message, state: FSMContext):
    """Show project name prompt with suggested name."""
    chat_title = message.chat.title or ""
    suggested = sanitize_project_name(chat_title)

    if suggested:
        text = strings.SETUP_PROJECT_NAME_PROMPT.format(suggested=suggested)
        # Add button for suggested name
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=suggested, callback_data=f"name:use:{suggested}")],
            [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="name:back")],
        ])
    else:
        text = strings.SETUP_PROJECT_NAME_PROMPT.format(suggested="(enter manually)")
        kb = go_back_keyboard("name:back")

    await message.edit_text(text, reply_markup=kb)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data.startswith("name:use:")
)
async def on_suggested_name(callback: CallbackQuery, state: FSMContext):
    """Use suggested project name."""
    await callback.answer()

    name = callback.data.split(":", 2)[-1]
    await _process_project_name(callback.message, state, name, is_suggested=True)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "name:back"
)
async def on_name_back(callback: CallbackQuery, state: FSMContext):
    """Go back to setup type."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.message(SetupFlow.awaiting_project_name, F.text, ~F.text.startswith("/"))
async def on_project_name_input(message: Message, state: FSMContext):
    """Handle custom project name input."""
    name = message.text.strip()

    # Validate name
    sanitized = sanitize_project_name(name)
    if not sanitized or sanitized != name:
        await message.answer(
            strings.SETUP_PROJECT_NAME_INVALID,
            reply_markup=go_back_keyboard("name:back"),
            parse_mode="MarkdownV2",
        )
        return

    await _process_project_name(message, state, name, is_suggested=False)


async def _process_project_name(
    message: Message,
    state: FSMContext,
    name: str,
    is_suggested: bool,
):
    """Process validated project name."""
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / name

    await state.update_data(
        project_name=name,
        target_dir=str(target_dir),
    )

    # Check if folder exists
    if target_dir.exists():
        await message.edit_text(
            strings.SETUP_PROJECT_EXISTS.format(name=name),
            reply_markup=folder_exists_keyboard("new"),
        )
        return

    # Custom name → ask for rename
    if not is_suggested:
        chat_title = message.chat.title or ""
        if chat_title != name:
            await state.set_state(SetupFlow.awaiting_rename_confirm)
            await state.update_data(rename_to=name)
            await message.edit_text(
                strings.SETUP_RENAME_PROMPT.format(name=name),
                reply_markup=rename_confirm_keyboard(),
            )
            return

    # Proceed to git choice
    await state.set_state(SetupFlow.awaiting_git_choice)
    await message.edit_text(
        strings.SETUP_GIT_CHOICE.format(folder=name),
        reply_markup=git_choice_keyboard(),
    )


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:use"
)
async def on_use_existing(callback: CallbackQuery, state: FSMContext):
    """Use existing folder."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Check git
    has_git = (target_dir / ".git").exists()

    if has_git:
        from .launch import do_launch
        await do_launch(callback.message, state)
    else:
        await state.set_state(SetupFlow.awaiting_git_choice)
        await callback.message.edit_text(
            strings.SETUP_GIT_CHOICE.format(folder=data["project_name"]),
            reply_markup=git_choice_keyboard(),
        )


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:rename"
)
async def on_different_name(callback: CallbackQuery, state: FSMContext):
    """Ask for different name."""
    await callback.answer()
    await show_project_name_prompt(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:back"
)
async def on_exists_back(callback: CallbackQuery, state: FSMContext):
    """Go back from folder exists."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


# Git choice handlers

@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:init"
)
async def on_git_init(callback: CallbackQuery, state: FSMContext):
    """Initialize git repository."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Create directory if needed
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    from ...services.setup.git_operations import git_init
    result = await git_init(target_dir)

    if not result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} git init failed: {result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    await state.update_data(git_choice="init")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:gh"
)
async def on_git_gh(callback: CallbackQuery, state: FSMContext):
    """Git init + gh repo create."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])
    project_name = data["project_name"]

    # Check gh first
    from ...services.setup.git_operations import check_gh_cli, git_init, gh_repo_create

    check = await check_gh_cli()
    if not check.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} {check.error}",
            reply_markup=git_choice_keyboard(),
        )
        return

    # Create directory
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    # Git init
    init_result = await git_init(target_dir)
    if not init_result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} git init failed: {init_result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    # Create GitHub repo
    gh_result = await gh_repo_create(target_dir, project_name)
    if not gh_result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} gh repo create failed: {gh_result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    await state.update_data(git_choice="gh")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:clone"
)
async def on_git_clone(callback: CallbackQuery, state: FSMContext):
    """Switch to clone flow."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Check if folder is empty
    if target_dir.exists() and any(target_dir.iterdir()):
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} Folder not empty, can't clone",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    # Switch to clone flow
    await state.set_state(SetupFlow.awaiting_clone_url)
    await state.update_data(setup_type="clone", clone_into_existing=True)

    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:none"
)
async def on_git_none(callback: CallbackQuery, state: FSMContext):
    """No git setup."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Create directory if needed
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    await state.update_data(git_choice="none")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:back"
)
async def on_git_back(callback: CallbackQuery, state: FSMContext):
    """Go back from git choice.

    Per design navigation:
    - If rename was shown, go back to ASK_RENAME_CONFIRM
    - Otherwise go back to previous step (folder select or project name)
    """
    await callback.answer()

    data = await state.get_data()
    setup_type = data.get("setup_type")
    project_name = data.get("project_name")
    chat_title = callback.message.chat.title or ""

    # Check if rename step was/should be shown
    # (chat title differs from project name)
    if chat_title != project_name:
        # Go back to rename confirm
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=project_name)
        await callback.message.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=project_name),
            reply_markup=rename_confirm_keyboard(),
        )
    elif setup_type == "connect":
        # Back to folder selection (rename was skipped)
        await state.set_state(SetupFlow.awaiting_folder_select)
        from .connect_flow import show_folder_selection
        await show_folder_selection(callback.message, state)
    else:
        # Back to project name (for "new" flow, rename was skipped)
        await state.set_state(SetupFlow.awaiting_project_name)
        await show_project_name_prompt(callback.message, state)
