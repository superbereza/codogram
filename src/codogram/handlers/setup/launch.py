# src/codogram/handlers/setup/launch.py
"""Launch phase handler."""
import asyncio
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...domain.states import SetupFlow
from ...keyboards.setup import go_back_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_launch")


@router.callback_query(F.data == "error:retry")
async def on_error_retry(callback: CallbackQuery, state: FSMContext):
    """Retry setup after error."""
    await callback.answer()

    # Clear state and restart setup
    await state.clear()

    # Restart setup flow
    from .triggers import _start_setup_flow
    await _start_setup_flow(callback.bot, callback.message.chat, state)


async def do_launch(message: Message, state: FSMContext):
    """Execute the launch phase.

    This is called from various flows after all setup is complete.
    """
    # Lazy imports to avoid circular dependencies
    from ...services.setup.project_setup import setup_project
    from ...services.menu import register_menu_for_chat
    from ...launch_animation import launch_with_animation
    from ...session_manager import project_manager
    from ...main import telegram_queue

    # Enter launching state (blocks user input)
    await state.set_state(SetupFlow.launching)

    data = await state.get_data()
    project_name = data["project_name"]
    target_dir = Path(data["target_dir"])

    chat = message.chat
    chat_id = chat.id
    chat_title = chat.title or project_name
    chat_type = chat.type
    thread_id = message.message_thread_id

    # Run setup (creates dir, tmux session, registers project)
    result = await setup_project(
        project_name=project_name,
        target_dir=target_dir,
        chat_id=chat_id,
        chat_title=chat_title,
        chat_type=chat_type,
    )

    if not result.success:
        # Reset to setup type selection so user can retry
        await state.set_state(SetupFlow.awaiting_setup_type)
        await message.answer(
            f"{strings.STATUS_ERR} Setup failed: {result.error}",
            reply_markup=go_back_keyboard("error:retry"),
            parse_mode="MarkdownV2",
        )
        return

    # Register appropriate menu
    is_forum = chat_type == "supergroup" and getattr(chat, "is_forum", False)
    await register_menu_for_chat(message.bot, chat_id, is_forum)

    # Clear FSM state
    await state.clear()

    # Get project and thread for animation
    project = project_manager.get_by_chat(chat_id)
    thread = project.get_or_create_thread(thread_id, project_name)

    # Launch Claude with animation (this handles everything including success message)
    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=chat_id,
            thread_id=thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )
