"""Message routing handler - routes messages to tmux sessions."""
import asyncio

from aiogram import Router
from aiogram.types import Message

from ..services.message_router import MessageRouterService, RouteAction
from ..services.file_input import FileInputService
from ..session_manager import project_manager, ThreadInfo
from ..telegram_queue import TelegramQueue
from ..logging_config import logger
from .. import strings
from .create_flow import handle_name_input

router = Router(name="messages")

# Service instances
_message_router = MessageRouterService()
_file_input = FileInputService()

# Error messages for file operations
_FILE_ERROR_MESSAGES = {
    "too_large": strings.FILE_TOO_LARGE,
    "download_failed": strings.FILE_DOWNLOAD_FAILED,
    "path_error": strings.FILE_DOWNLOAD_FAILED,
}


@router.message()
async def on_message(message: Message, telegram_queue: TelegramQueue):
    """Route regular messages to tmux sessions.

    This is the catch-all handler - registered last so commands
    and FSM states are handled first by other routers.
    """
    text = message.text
    has_file = bool(message.photo or message.document)

    # Block video/audio
    if message.video or message.video_note or message.audio or message.voice:
        await telegram_queue.reply(message, strings.FILE_AUDIO_VIDEO_NOT_SUPPORTED)
        return

    # Skip empty messages (no text and no file)
    if not text and not has_file:
        return

    # Log
    content_preview = text[:100] if text and len(text) > 100 else (text or "[file]")
    logger.info(
        f"Incoming message from user={message.from_user.id} "
        f"chat={message.chat.id} thread={message.message_thread_id}: {content_preview}"
    )

    # Skip commands
    if text and text.startswith("/"):
        return

    chat_id = message.chat.id

    # Check if awaiting name input for create flow
    if await handle_name_input(message, telegram_queue):
        return

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
            await telegram_queue.reply(message, "Use /start or /thread_create to connect Claude to this topic")
            return

        case RouteAction.SKIP_PENDING:
            # Pending thread - skip silently
            return

        case RouteAction.START_BINDING:
            # Need to bind session - start binding task
            await _start_binding(message, result)
            # Still try to send to tmux (supports files too)
            await _send_content(message, result, telegram_queue)
            return

        case RouteAction.SEND_TO_TMUX:
            success = await _send_content(message, result, telegram_queue)
            if not success and message.chat.id < 0:
                await telegram_queue.reply(message, "No active Claude session. Use /start to launch.")

        case RouteAction.NO_TMUX:
            if message.chat.id < 0:
                await telegram_queue.reply(message, "No active Claude session. Use /start to launch.")


async def _send_content(message: Message, result, telegram_queue: TelegramQueue) -> bool:
    """Send message content (text or file) to tmux.

    Returns:
        True if sent successfully or if error was already shown to user.
        False only if tmux session doesn't exist.
    """
    if not result.tmux_name or not result.cwd:
        return False

    # Handle file messages (photo or document)
    if message.photo or message.document:
        file_info = _file_input.extract_info(message)
        if not file_info:
            await telegram_queue.reply(message, strings.FILE_TYPE_NOT_SUPPORTED)
            return True  # Error shown, don't show "No active session"

        # Create download callback
        async def download(file_id: str, destination: str):
            await message.bot.download(file_id, destination=destination)

        # Save file via service
        save_result = await _file_input.save_file(
            file_info=file_info,
            cwd=result.cwd,
            thread_name=result.thread.name,
            thread_id=message.message_thread_id,
            user_id=message.from_user.id,
            download_fn=download
        )

        if not save_result.success:
            error_msg = _FILE_ERROR_MESSAGES.get(save_result.error, "Failed to process file")
            await telegram_queue.reply(message, error_msg)
            return True  # Error shown, don't show "No active session"

        content = _file_input.format_message(message.caption, [save_result.path], result.cwd)
    else:
        content = message.text

    return _message_router.send_to_tmux(result, content)


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
