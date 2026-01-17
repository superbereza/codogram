"""Handlers for create flow (branch/thread name selection)."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings
from ..domain.create_flow import CreateType
from .common import get_flow_state, clear_flow_state
from ..keyboards.create_flow import CALLBACK_MAGIC_PREFIX, CALLBACK_CANCEL
from ..services.create_flow import create_flow_service
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..git_utils import get_default_branch

router = Router(name="create_flow")


@router.callback_query(F.data == CALLBACK_CANCEL)
async def on_create_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle cancel - delete prompt and clear state."""
    clear_flow_state(callback.message.chat.id, callback.message.message_thread_id)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith(CALLBACK_MAGIC_PREFIX))
async def on_create_magic(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle magic name button - generate name and create."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    type_str = callback.data.split(":")[1]
    create_type = CreateType(type_str)

    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    name = create_flow_service.get_magic_name(project)

    # Show "Creating..." status (edit removes buttons)
    if create_type == CreateType.BRANCH:
        await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=name))
    else:
        await telegram_queue.edit(callback.message, strings.THREAD_CREATING.format(name=name))
    await callback.answer()

    if create_type == CreateType.BRANCH:
        result = await _do_create_branch(callback.bot, chat_id, thread_id, project, name, telegram_queue)
        if result:
            await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=name), thread_id=thread_id)
    else:
        result = await _do_create_thread(callback.bot, chat_id, thread_id, project, name, telegram_queue)
        if result:
            await telegram_queue.send(chat_id, strings.THREAD_CREATED.format(name=name), thread_id=thread_id)


async def handle_name_input(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Handle text message as name input.

    Returns True if message was handled, False if no awaiting state.
    """
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "awaiting_create_name":
        return False

    create_type_str = state.get("create_type")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.CREATE_PROJECT_NOT_FOUND)
        return True

    name, error = create_flow_service.validate_name(message.text.strip(), project)
    if error:
        await telegram_queue.reply(message, error)
        return True

    create_type = CreateType(create_type_str)
    if create_type == CreateType.BRANCH:
        await _do_create_branch(message.bot, chat_id, thread_id, project, name, telegram_queue)
    else:
        # Show "Creating..." status
        await telegram_queue.reply(message, strings.THREAD_CREATING.format(name=name))
        result = await _do_create_thread(message.bot, chat_id, thread_id, project, name, telegram_queue)
        if result:
            await telegram_queue.send(chat_id, strings.THREAD_CREATED.format(name=name), thread_id=thread_id)

    return True


async def _do_create_branch(
    bot, chat_id: int, thread_id: int | None, project, name: str, telegram_queue: TelegramQueue
):
    """Create branch with given name, handling preconditions.

    Returns ThreadInfo if created, None otherwise.
    """
    can_create, error, warning = create_flow_service.check_branch_preconditions(project, name)

    if error:
        await telegram_queue.send(chat_id, error, thread_id=thread_id)
        return None

    if warning:
        # Uncommitted changes - show options
        default_branch = get_default_branch(project.cwd)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Create from last commit",
                callback_data=f"bc_create:{name}:{default_branch}"
            )],
            [InlineKeyboardButton(
                text="Commit first",
                callback_data=f"bc_commit:{name}"
            )],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")],
        ])
        await telegram_queue.send(chat_id, warning, thread_id=thread_id, reply_markup=keyboard)
        return None

    default_branch = get_default_branch(project.cwd)
    return await do_branch_create(bot, chat_id, project, name, default_branch)


async def _do_create_thread(bot, chat_id: int, thread_id: int | None, project, name: str, telegram_queue: TelegramQueue):
    """Create thread with given name. Returns thread if successful, None otherwise."""
    thread = await create_thread_with_session(
        bot=bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )
    if not thread:
        await telegram_queue.send(chat_id, strings.CREATE_TOPIC_ERROR, thread_id=thread_id)
        return None
    return thread
