"""Message routing handler - routes messages to tmux sessions."""
import asyncio

from aiogram import F, Router
from aiogram.types import Message

from ..services.message_router import MessageRouterService, RouteAction
from ..services.file_input import FileInputService
from ..services.response_mode import ResponseModeService
from ..session_manager import project_manager, ThreadInfo
from ..telegram_queue import TelegramQueue
from ..logging_config import logger
from .. import strings
from .new_chat import handle_name_input
from .common import normalize_thread_id

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


def _should_skip_by_response_mode(
    message: Message,
    response_mode_service: ResponseModeService,
) -> bool:
    """Check if message should be skipped based on response mode.

    Returns True if message should be skipped, False if should process.
    """
    # Skip filter for private chats
    if message.chat.type == "private":
        return False

    # Forwarded messages - always respond (user forwarded intentionally)
    if message.forward_date or message.forward_from or message.forward_from_chat:
        return False

    chat_id = message.chat.id
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return False  # No project = no filter

    thread = project.threads.get(thread_id) if thread_id is not None else project.threads.get(None)
    mode = thread.response_mode if thread else project.response_mode

    reply_to_user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        reply_to_user_id = message.reply_to_message.from_user.id

    text = message.text or message.caption
    entities = message.entities or message.caption_entities or []

    result = response_mode_service.should_respond(
        mode=mode,
        text=text,
        entities=entities,
        reply_to_user_id=reply_to_user_id,
    )

    if not result.should_respond:
        logger.info(f"Skipping message in {mode} mode: {result.reason}")
        return True

    return False


@router.message(F.text.startswith("/"))
async def on_unknown_command(
    message: Message,
    telegram_queue: TelegramQueue,
    response_mode_service: ResponseModeService | None = None,
):
    """Forward unregistered commands to Claude as text."""
    if response_mode_service and _should_skip_by_response_mode(message, response_mode_service):
        return

    await _route_message(message, telegram_queue)


@router.message()
async def on_message(
    message: Message,
    telegram_queue: TelegramQueue,
    response_mode_service: ResponseModeService | None = None,
):
    """Route regular messages to tmux sessions.

    This is the catch-all handler - registered last so commands
    and FSM states are handled first by other routers.
    """
    if response_mode_service and _should_skip_by_response_mode(message, response_mode_service):
        return

    await _route_message(message, telegram_queue)


async def _route_message(message: Message, telegram_queue: TelegramQueue):
    """Common routing logic for all messages."""
    text = message.text
    has_file = bool(message.photo or message.document)

    # Block video files (not video_note - those are handled by audio router)
    if message.video:
        await telegram_queue.reply(message, strings.FILE_VIDEO_NOT_SUPPORTED)
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

    chat_id = message.chat.id

    # Check if awaiting name input for create flow
    if await handle_name_input(message, telegram_queue):
        return

    # Normalize thread_id - ignore in non-forum chats
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    # Route the message
    result = _message_router.route(chat_id, thread_id, text)

    match result.action:
        case RouteAction.NO_PROJECT:
            # Silent - no project registered
            return

        case RouteAction.CREATE_PENDING:
            # Unknown topic - create pending thread
            logger.info(f"CREATE_PENDING: chat={chat_id} thread_id={thread_id}")
            thread = ThreadInfo(thread_id=thread_id, name="pending")
            result.project.threads[thread_id] = thread
            project_manager._save()
            await telegram_queue.reply(message, strings.THREAD_CONNECT_HINT)
            return

        case RouteAction.SKIP_PENDING:
            # Pending thread - skip silently
            return

        case RouteAction.START_BINDING:
            # Need to bind session - start binding task
            await _start_binding(message, result, telegram_queue)
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

    # Track for stuck message detection
    if result.thread:
        result.thread.last_sent_message = content

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


async def _start_binding(message: Message, result, telegram_queue: TelegramQueue):
    """Start session binding for unbound thread."""
    from ..history_watcher import poll_for_session_thread

    thread = result.thread
    project = result.project

    thread.last_sent_message = message.text

    if not thread.binding_task or thread.binding_task.done():
        logger.debug(f"Starting binding task for thread {thread.name}")

        async def start_poller(p):
            from ..permission_poller import create_poller_task
            return await create_poller_task(message.bot, p, telegram_queue)

        async def start_watcher(p, send_missed=False):
            from ..watcher import create_watcher_task
            return await create_watcher_task(message.bot, p, telegram_queue, send_missed)

        thread.binding_task = asyncio.create_task(
            poll_for_session_thread(
                project, thread, message.bot,
                start_poller, start_watcher, telegram_queue
            )
        )
