"""Handler registry for FlowAction results.

Replaces god-switch in _handle_result with modular handlers.
"""
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ... import strings
from ...domain.states import StartFlow
from ...services.start import FlowAction, FlowResult
from ...telegram.queue import TelegramQueue
from ...start_flow import dir_not_found_keyboard, git_setup_keyboard, launch_confirm_keyboard
from ...telegram.keyboards.tmux_selector import create_tmux_selection_keyboard
from .helpers import register_chat_menu


# === Individual handlers ===

async def handle_ask_project_name(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_project_name)
    if result.thread_id:
        await state.update_data(thread_id=result.thread_id)
    await queue.reply(msg, strings.START_PROJECT_NAME_PROMPT, parse_mode=None)


async def handle_ask_dir_choice(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_dir_choice)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_DIR_CHOICE_PROMPT.format(path=result.path),
                      reply_markup=dir_not_found_keyboard())


async def handle_ask_git_choice(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_git_choice)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_GIT_SETUP_PROMPT,
                      reply_markup=git_setup_keyboard(), parse_mode=None)


async def handle_ask_launch_confirm(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_launch_confirm)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_LAUNCH_CONFIRM.format(path=result.path),
                      reply_markup=launch_confirm_keyboard())


async def handle_ask_tmux_select(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    # BUG FIX: Set state for tmux selection (was missing)
    await state.set_state(StartFlow.awaiting_tmux_select)
    await state.update_data(project=result.project)
    await queue.reply(msg, strings.START_TMUX_SELECT,
                      reply_markup=create_tmux_selection_keyboard(result.tmux_list, result.project),
                      parse_mode=None)


async def handle_show_status(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_CLAUDE_RUNNING.format(
        project=result.project, tmux_session=result.tmux_session))


async def handle_error(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await queue.reply(msg, strings.START_ERROR.format(error=result.error), parse_mode=None)


async def handle_ask_clone_retry(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    # BUG FIX: Ensure we're in the right state
    await state.set_state(StartFlow.awaiting_clone_url)
    await queue.reply(msg, f"{result.error}\n\n{strings.GIT_URL_RETRY_PROMPT}")


async def handle_thread_show_status(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_THREAD_RUNNING.format(
        thread_name=result.thread_name, tmux_session=result.tmux_session))


# === Registry ===

MESSAGE_HANDLERS: dict[FlowAction, callable] = {
    FlowAction.ASK_PROJECT_NAME: handle_ask_project_name,
    FlowAction.ASK_DIR_CHOICE: handle_ask_dir_choice,
    FlowAction.ASK_GIT_CHOICE: handle_ask_git_choice,
    FlowAction.ASK_LAUNCH_CONFIRM: handle_ask_launch_confirm,
    FlowAction.ASK_TMUX_SELECT: handle_ask_tmux_select,
    FlowAction.SHOW_STATUS: handle_show_status,
    FlowAction.ERROR: handle_error,
    FlowAction.ASK_CLONE_URL_RETRY: handle_ask_clone_retry,
    FlowAction.THREAD_SHOW_STATUS: handle_thread_show_status,
    # CONNECT, LAUNCH, THREAD_LAUNCH handled separately (need launch callback)
}


async def dispatch_result(
    msg: Message,
    state: FSMContext,
    result: FlowResult,
    queue: TelegramQueue,
    launch_callback=None,
):
    """Dispatch FlowResult to appropriate handler."""
    handler = MESSAGE_HANDLERS.get(result.action)
    if handler:
        await handler(msg, state, result, queue)
        return

    # Special cases needing launch callback
    if result.action == FlowAction.CONNECT:
        await state.clear()
        await _connect_to_session(msg, result, queue)
    elif result.action == FlowAction.LAUNCH:
        await state.clear()
        if launch_callback:
            await launch_callback(msg, result, queue)
    elif result.action in (FlowAction.THREAD_LAUNCH, FlowAction.UPGRADE_PENDING_THREAD, FlowAction.REGISTER_UNKNOWN_TOPIC):
        await state.clear()
        if result.action == FlowAction.UPGRADE_PENDING_THREAD:
            await queue.reply(msg, strings.START_THREAD_UPGRADED.format(thread_name=result.thread_name))
        elif result.action == FlowAction.REGISTER_UNKNOWN_TOPIC:
            await queue.reply(msg, strings.START_TOPIC_REGISTERED.format(thread_name=result.thread_name))
        if launch_callback:
            await launch_callback(msg, result, queue, thread=True)


async def _connect_to_session(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Connect to existing tmux session."""
    from ...core.session_manager import project_manager

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # BUG FIX: Was silent failure
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    project.tmux_session = result.tmux_session
    project_manager._save()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_CONNECTED.format(tmux_session=result.tmux_session))
