"""Audio message handler - transcribes voice/audio/video_note via Whisper."""
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

# Service instances
_file_input = FileInputService()
_message_router = MessageRouterService()

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

        # Download from Telegram
        logger.info(f"Audio download: file_id={audio_info.file_id[:20]}... size={audio_info.size}")
        tg_file = await message.bot.get_file(audio_info.file_id)
        await message.bot.download(tg_file.file_path, destination=str(file_path))

        logger.info(f"Audio saved: {file_path} ({audio_info.size} bytes)")

        # Transcribe
        whisper = WhisperService(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.whisper_timeout
        )
        transcription = await whisper.transcribe(file_path)

        if not transcription.success:
            error_msg = _ERROR_MESSAGES.get(
                transcription.error,
                strings.AUDIO_ERR_GENERIC.format(error=transcription.error)
            )
            await edit_status(error_msg)
            return

        # Show transcription and send to Claude
        text = transcription.text
        await edit_status(strings.AUDIO_SENT.format(text=text))

        # Send to tmux
        _message_router.send_to_tmux(result, text)

    except Exception as e:
        logger.exception(f"Audio handling failed: {e}")
        await edit_status(strings.AUDIO_ERR_GENERIC.format(error=str(e)[:50]))


@router.message(F.content_type.in_({ContentType.VOICE, ContentType.AUDIO, ContentType.VIDEO_NOTE}))
async def on_audio(message: Message, telegram_queue: TelegramQueue):
    """Route audio messages to handler."""
    await _handle_audio_message(message, telegram_queue)
