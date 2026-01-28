"""Audio message handler - transcribes voice/audio/video_note via Whisper."""
import asyncio
import json
from datetime import datetime
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ContentType

from ..config import settings
from ..services.file_input import FileInputService
from ..services.message_router import MessageRouterService, RouteAction
from ..services.whisper import WhisperService
from ..telegram.queue import TelegramQueue
from ..logging_config import logger
from .. import strings
from .common import normalize_thread_id

router = Router(name="audio")

# Whisper usage log
WHISPER_LOG_PATH = Path.home() / ".codogram" / "whisper-usage.jsonl"

# Service instances
_file_input = FileInputService()
_message_router = MessageRouterService()


def _log_whisper_usage(
    user_id: int,
    username: str | None,
    chat_id: int,
    project: str | None,
    duration_sec: int | None,
    file_size: int,
    success: bool,
    error: str | None = None
):
    """Log Whisper API usage to JSONL file for cost tracking."""
    try:
        WHISPER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Cost from config (default $0.006/min for whisper-1)
        cost_usd = (duration_sec / 60) * settings.whisper_cost_per_minute if duration_sec else 0

        entry = {
            "ts": datetime.now().isoformat(),
            "user_id": user_id,
            "username": username,
            "chat_id": chat_id,
            "project": project,
            "duration_sec": duration_sec,
            "file_size": file_size,
            "cost_usd": round(cost_usd, 6),
            "success": success,
            "error": error,
        }

        with open(WHISPER_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log Whisper usage: {e}")


async def _start_binding(message: Message, result, text: str, telegram_queue: TelegramQueue):
    """Start session binding for unbound thread (audio version).

    Unlike messages.py, we receive transcribed text as parameter since
    audio messages don't have text until after transcription.
    """
    from ..core.coordinator import poll_for_session_thread

    thread = result.thread
    project = result.project

    thread.last_sent_message = text

    if not thread.binding_task or thread.binding_task.done():
        logger.debug(f"Starting binding task for thread {thread.name} (audio)")

        async def start_poller(p):
            from ..claude.poller import create_poller_task
            return await create_poller_task(message.bot, p, telegram_queue)

        async def start_watcher(p, send_missed=False):
            from ..claude.history_watcher import create_watcher_task
            return await create_watcher_task(message.bot, p, telegram_queue, send_missed)

        thread.binding_task = asyncio.create_task(
            poll_for_session_thread(
                project, thread, message.bot,
                start_poller, start_watcher, telegram_queue
            )
        )

# Error code to string mapping
_ERROR_MESSAGES = {
    "file_too_large": strings.AUDIO_ERR_TOO_LARGE,
    "format": strings.AUDIO_ERR_FORMAT,
    "timeout": strings.AUDIO_ERR_TIMEOUT,
    "no_speech": strings.AUDIO_ERR_NO_SPEECH,
    "file_not_found": strings.AUDIO_ERR_GENERIC.format(error="file not found"),
}


async def _handle_audio_message(message: Message, telegram_queue: TelegramQueue):
    """Handle voice/audio/video_note message.

    Flow:
    1. Check if Whisper configured
    2. Route to find project/thread
    3. Send "Transcribing..." message
    4. Download and save audio file
    5. Transcribe via Whisper
    6. Show result and send to Claude
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None

    # Normalize thread_id - ignore in non-forum chats
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    # Check if Whisper is configured
    if not settings.openai_api_key:
        await telegram_queue.reply(message, strings.AUDIO_ERR_NOT_CONFIGURED)
        return

    # Route to find project
    result = _message_router.route(chat_id, thread_id, "")

    if result.action == RouteAction.NO_PROJECT:
        # Silent - no project registered
        return

    if result.action in (RouteAction.CREATE_PENDING, RouteAction.SKIP_PENDING):
        # Pending thread - skip silently
        return

    if not result.cwd or not result.thread:
        return

    # Extract audio info
    audio_info = _file_input.extract_audio_info(message)
    if not audio_info:
        return

    # Send "Transcribing..." message
    status_msg_ids = await telegram_queue.reply(message, strings.AUDIO_TRANSCRIBING)
    status_msg_id = status_msg_ids[0] if status_msg_ids else None

    async def edit_status(text: str):
        """Edit the status message."""
        if status_msg_id:
            try:
                await message.bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    parse_mode="Markdown",
                )
            except Exception:
                pass  # Ignore edit errors

    try:
        # Build file path
        file_path = _file_input._build_path(
            cwd=result.cwd,
            thread_name=result.thread.name,
            thread_id=thread_id,
            user_id=user_id,
            extension=audio_info.extension
        )

        # Download from Telegram (use file_id directly like messages.py)
        logger.info(f"Audio download: file_id={audio_info.file_id[:20]}... size={audio_info.size}")
        await message.bot.download(audio_info.file_id, destination=str(file_path))

        logger.info(f"Audio saved: {file_path} ({audio_info.size} bytes)")

        # Transcribe
        whisper = WhisperService(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.whisper_timeout
        )
        transcription = await whisper.transcribe(file_path)

        if not transcription.success:
            _log_whisper_usage(
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                project=result.project.name if result.project else None,
                duration_sec=audio_info.duration,
                file_size=audio_info.size,
                success=False,
                error=transcription.error,
            )
            error_msg = _ERROR_MESSAGES.get(
                transcription.error,
                strings.AUDIO_ERR_GENERIC.format(error=transcription.error)
            )
            await edit_status(error_msg)
            return

        # Log successful transcription
        _log_whisper_usage(
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            project=result.project.name if result.project else None,
            duration_sec=audio_info.duration,
            file_size=audio_info.size,
            success=True,
        )

        # Show transcription and send to Claude
        text = transcription.text
        await edit_status(strings.AUDIO_SENT.format(text=text))

        # Track for stuck message detection
        if result.thread:
            result.thread.last_sent_message = text

        # Start binding if needed (session_id is None)
        if result.action == RouteAction.START_BINDING:
            await _start_binding(message, result, text, telegram_queue)

        # Track for stuck message detection
        if result.thread:
            result.thread.last_sent_message = text

        # Send to tmux
        _message_router.send_to_tmux(result, text)

    except Exception as e:
        logger.exception(f"Audio handling failed: {e}")
        await edit_status(strings.AUDIO_ERR_GENERIC.format(error=str(e)[:50]))


@router.message(F.content_type.in_({ContentType.VOICE, ContentType.AUDIO, ContentType.VIDEO_NOTE}))
async def on_audio(message: Message, telegram_queue: TelegramQueue):
    """Route audio messages to handler."""
    await _handle_audio_message(message, telegram_queue)
