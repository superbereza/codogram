"""Message routing handler - routes messages to tmux sessions."""
import asyncio

from aiogram import Router
from aiogram.types import Message

from ..services.message_router import MessageRouterService, RouteAction
from ..session_manager import project_manager, ThreadInfo
from ..logging_config import logger

router = Router(name="messages")

# Service instance
_message_router = MessageRouterService()


@router.message()
async def on_message(message: Message):
    """Route regular messages to tmux sessions.

    This is the catch-all handler - registered last so commands
    and FSM states are handled first by other routers.
    """
    text = message.text
    if not text:
        return

    # Log
    text_preview = text[:100] if len(text) > 100 else text
    logger.info(
        f"Incoming message from user={message.from_user.id} "
        f"chat={message.chat.id} thread={message.message_thread_id}: {text_preview}"
    )

    # Skip commands
    if text.startswith("/"):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    # Route the message
    result = _message_router.route(chat_id, thread_id, text)

    match result.action:
        case RouteAction.NO_PROJECT:
            # Silent - no project registered
            return

        case RouteAction.CREATE_PENDING:
            # Unknown topic - create pending thread
            thread = ThreadInfo(thread_id=thread_id, name="pending")
            result.project.threads[thread_id] = thread
            project_manager._save()
            await message.answer("Use /start or /thread_create to connect Claude to this topic")
            return

        case RouteAction.SKIP_PENDING:
            # Pending thread - skip silently
            return

        case RouteAction.START_BINDING:
            # Need to bind session - start binding task
            await _start_binding(message, result)
            # Still try to send to tmux
            _try_send_to_tmux(result, text)
            return

        case RouteAction.SEND_TO_TMUX:
            success = _message_router.send_to_tmux(result, text)
            if not success and message.chat.id < 0:
                await message.answer("No active Claude session. Use /start to launch.")

        case RouteAction.NO_TMUX:
            if message.chat.id < 0:
                await message.answer("No active Claude session. Use /start to launch.")


def _try_send_to_tmux(result, text: str) -> bool:
    """Try to send message to tmux if session exists."""
    if result.tmux_name and result.cwd:
        from ..tmux import TmuxSession
        tmux = TmuxSession(result.tmux_name, result.cwd)
        if tmux.exists():
            tmux.send(text)
            return True
    return False


async def _start_binding(message: Message, result):
    """Start session binding for unbound thread."""
    from ..history_watcher import poll_for_session_thread
    from .. import main

    thread = result.thread
    project = result.project

    thread.last_sent_message = message.text

    if not thread.binding_task or thread.binding_task.done():
        logger.debug(f"Starting binding task for thread {thread.name}")

        async def start_poller(p):
            from ..permission_poller import create_poller_task
            return await create_poller_task(message.bot, p, main.telegram_queue)

        async def start_watcher(p, send_missed=False):
            from ..watcher import create_watcher_task
            return await create_watcher_task(message.bot, p, main.telegram_queue, send_missed)

        thread.binding_task = asyncio.create_task(
            poll_for_session_thread(
                project, thread, message.bot,
                start_poller, start_watcher, main.telegram_queue
            )
        )
