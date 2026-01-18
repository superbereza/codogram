# src/codogram/handlers/setup/clone_flow.py
"""Clone repository flow handlers."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...config import settings
from ...domain.states import SetupFlow
from ...domain.validators import validate_git_url, extract_project_name_from_url
from ...keyboards.setup import go_back_keyboard, setup_type_keyboard, folder_exists_keyboard, clone_error_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_clone")


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "clone:back"
)
async def on_clone_back(callback: CallbackQuery, state: FSMContext):
    """Handle Go back from clone URL input."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "clone:retry"
)
async def on_clone_retry(callback: CallbackQuery, state: FSMContext):
    """Handle Retry button after clone failure."""
    await callback.answer()

    # Retry the clone with stored data
    await _do_clone(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "clone:change_url"
)
async def on_clone_change_url(callback: CallbackQuery, state: FSMContext):
    """Handle Change URL button after clone failure."""
    await callback.answer()

    # Go back to URL prompt
    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "exists:use"
)
async def on_exists_use(callback: CallbackQuery, state: FSMContext):
    """Handle Use existing folder button."""
    await callback.answer()

    # Use existing folder - proceed to rename check or launch
    data = await state.get_data()
    project_name = data["project_name"]
    chat_title = callback.message.chat.title or ""

    if chat_title != project_name:
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=project_name)

        from ...keyboards.setup.confirm import rename_confirm_keyboard
        await callback.message.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=project_name),
            reply_markup=rename_confirm_keyboard(),
        )
    else:
        # Proceed to launch
        await _proceed_to_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "exists:rename"
)
async def on_exists_rename(callback: CallbackQuery, state: FSMContext):
    """Handle Different name button - ask for new URL."""
    await callback.answer()

    # Clear stored data and ask for new URL
    await state.update_data(clone_url=None, project_name=None, target_dir=None)
    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.message(SetupFlow.awaiting_clone_url, F.text, ~F.text.startswith("/"))
async def on_clone_url(message: Message, state: FSMContext):
    """Handle clone URL input."""
    url = message.text.strip()

    # Validate URL
    is_valid, error = validate_git_url(url)
    if not is_valid:
        await message.answer(
            f"{strings.STATUS_ERR} {error}",
            reply_markup=go_back_keyboard("clone:back"),
            parse_mode="MarkdownV2",
        )
        return

    # Extract project name
    project_name = extract_project_name_from_url(url)
    if not project_name:
        await message.answer(
            f"{strings.STATUS_ERR} Could not extract project name from URL",
            reply_markup=go_back_keyboard("clone:back"),
            parse_mode="MarkdownV2",
        )
        return

    # Check if folder already exists
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / project_name

    if target_dir.exists():
        await state.update_data(clone_url=url, project_name=project_name, target_dir=str(target_dir))
        # Folder exists - offer Use existing / Different name (per design line 295)
        await message.answer(
            strings.SETUP_PROJECT_EXISTS.format(name=project_name),
            reply_markup=folder_exists_keyboard("clone"),
            parse_mode="MarkdownV2",
        )
        return

    # Store data and proceed to clone
    await state.update_data(
        clone_url=url,
        project_name=project_name,
        target_dir=str(target_dir),
    )

    # Perform clone
    await _do_clone(message, state)


async def _do_clone(message: Message, state: FSMContext):
    """Perform the git clone operation."""
    data = await state.get_data()
    url = data["clone_url"]
    target_dir = data["target_dir"]
    project_name = data["project_name"]

    # Show progress
    progress_msg = await message.answer(strings.SETUP_CLONE_PROGRESS, parse_mode="MarkdownV2")

    # Import git_clone from existing service
    from ...services.start_flow import git_clone

    result = await git_clone(url, target_dir)

    if not result.success:
        error_msg = result.error or "Unknown error"

        # Add hints for common errors
        hint = ""
        if "Permission denied" in error_msg:
            hint = f"\n\n{strings.SETUP_CLONE_SSH_HINT}"
        elif "Authentication failed" in error_msg or "401" in error_msg:
            hint = f"\n\n{strings.SETUP_CLONE_AUTH_HINT}"

        # Show Retry/Change URL/Back buttons (per design line 229)
        await progress_msg.edit_text(
            strings.SETUP_CLONE_FAILED.format(error=error_msg) + hint,
            reply_markup=clone_error_keyboard(),
            parse_mode="MarkdownV2",
        )
        return

    # Clone successful - check if rename needed
    chat_title = message.chat.title or ""

    if chat_title != project_name:
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=project_name)

        from ...keyboards.setup.confirm import rename_confirm_keyboard
        await progress_msg.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=project_name),
            reply_markup=rename_confirm_keyboard(),
        )
    else:
        # No rename needed - proceed to launch
        await _proceed_to_launch(progress_msg, state)


async def _proceed_to_launch(message: Message, state: FSMContext):
    """Proceed to launch phase."""
    from .launch import do_launch
    await do_launch(message, state)
