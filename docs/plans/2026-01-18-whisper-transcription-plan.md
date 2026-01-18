# Whisper Transcription Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add voice/audio/video_note transcription via OpenAI Whisper API, show result to user, send to Claude in tmux.

**Architecture:** New `WhisperService` handles API calls, new `handlers/audio.py` routes media messages, extends `FileInputService` for audio file saving.

**Tech Stack:** OpenAI Python SDK (async), aiogram content type filters.

---

## Task 1: Add OpenAI config fields

**Files:**
- Modify: `src/codogram/config.py:6-28`

**Step 1: Add config fields**

Add to `Settings` class after line 12:

```python
    # OpenAI / Whisper
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
```

**Step 2: Verify config loads**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
python -c "from src.codogram.config import settings; print('openai_base_url:', settings.openai_base_url)"
```

Expected: `openai_base_url: https://api.openai.com/v1`

**Step 3: Commit**

```bash
git add src/codogram/config.py
git commit -m "feat(config): add OpenAI API key and base URL settings"
```

---

## Task 2: Add audio strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add audio strings section**

Add after line 139 (after `FILE_DOWNLOAD_FAILED`):

```python

# --- Audio/Whisper ---

AUDIO_TRANSCRIBING = f"{STATUS_PENDING} Transcribing..."
AUDIO_SENT = f"{STATUS_OK} «{{text}}» → Claude"

AUDIO_ERR_TOO_LARGE = f"{STATUS_ERR} Transcription failed: file too large"
AUDIO_ERR_FORMAT = f"{STATUS_ERR} Transcription failed: unsupported format"
AUDIO_ERR_TIMEOUT = f"{STATUS_ERR} Transcription failed: timeout, try again"
AUDIO_ERR_GENERIC = f"{STATUS_ERR} Transcription failed: {{error}}"
AUDIO_ERR_NO_SPEECH = f"{STATUS_ERR} No speech detected"
AUDIO_ERR_NOT_CONFIGURED = f"{STATUS_ERR} Whisper not configured (missing OPENAI_API_KEY)"
```

**Step 2: Remove old audio blocker string**

Delete line 136:
```python
FILE_AUDIO_VIDEO_NOT_SUPPORTED = f"{STATUS_WARN} Video and audio not supported yet. Coming soon with Whisper!"
```

**Step 3: Verify imports**

```bash
python -c "from src.codogram.strings import AUDIO_TRANSCRIBING, AUDIO_SENT; print(AUDIO_TRANSCRIBING)"
```

Expected: `` `[~]` Transcribing... ``

**Step 4: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat(strings): add audio transcription messages"
```

---

## Task 3: Add openai dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add openai to dependencies**

Add to dependencies list (line 5-11):

```toml
dependencies = [
    "aiogram>=3.4",
    "aiofiles>=23.0",
    "pydantic-settings>=2.0",
    "telegramify-markdown>=0.5",
    "unidecode>=1.3",
    "openai>=1.0",
]
```

**Step 2: Install in main venv**

```bash
cd /home/superbereza/dev/codogram
source venv/bin/activate
pip install openai>=1.0
```

**Step 3: Verify**

```bash
python -c "import openai; print('openai version:', openai.__version__)"
```

Expected: `openai version: 1.x.x`

**Step 4: Commit**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
git add pyproject.toml
git commit -m "feat(deps): add openai SDK for Whisper transcription"
```

---

## Task 4: Create WhisperService with tests

**Files:**
- Create: `src/codogram/services/whisper.py`
- Create: `tests/test_whisper_service.py`

**Step 1: Write the failing test**

Create `tests/test_whisper_service.py`:

```python
"""Tests for WhisperService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.codogram.services.whisper import WhisperService, TranscriptionResult


class TestWhisperService:
    """Tests for WhisperService."""

    def test_init_with_credentials(self):
        """Service initializes with API key and base URL."""
        service = WhisperService(
            api_key="test-key",
            base_url="https://custom.api.com/v1"
        )
        assert service.api_key == "test-key"
        assert service.base_url == "https://custom.api.com/v1"

    def test_init_default_base_url(self):
        """Service uses OpenAI default base URL."""
        service = WhisperService(api_key="test-key")
        assert service.base_url == "https://api.openai.com/v1"

    @pytest.mark.asyncio
    async def test_transcribe_success(self, tmp_path):
        """Successful transcription returns text."""
        service = WhisperService(api_key="test-key")

        # Create dummy audio file
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.text = "Hello world"

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = await service.transcribe(audio_file)

        assert result.success is True
        assert result.text == "Hello world"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, tmp_path):
        """Missing file returns error."""
        service = WhisperService(api_key="test-key")

        result = await service.transcribe(tmp_path / "nonexistent.ogg")

        assert result.success is False
        assert result.error == "file_not_found"

    @pytest.mark.asyncio
    async def test_transcribe_api_error_file_too_large(self, tmp_path):
        """API error about file size is mapped correctly."""
        service = WhisperService(api_key="test-key")

        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            from openai import BadRequestError
            mock_api.side_effect = BadRequestError(
                message="Maximum content size limit exceeded",
                response=MagicMock(status_code=400),
                body={"error": {"message": "Maximum content size limit exceeded"}}
            )

            result = await service.transcribe(audio_file)

        assert result.success is False
        assert result.error == "file_too_large"

    @pytest.mark.asyncio
    async def test_transcribe_api_timeout(self, tmp_path):
        """Timeout is mapped correctly."""
        service = WhisperService(api_key="test-key")

        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            import asyncio
            mock_api.side_effect = asyncio.TimeoutError()

            result = await service.transcribe(audio_file)

        assert result.success is False
        assert result.error == "timeout"
```

**Step 2: Run test to verify it fails**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
python -m pytest tests/test_whisper_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.codogram.services.whisper'`

**Step 3: Write WhisperService implementation**

Create `src/codogram/services/whisper.py`:

```python
"""Whisper transcription service."""
from dataclasses import dataclass
from pathlib import Path
import asyncio

from openai import AsyncOpenAI, BadRequestError, APITimeoutError, APIError

from ..logging_config import logger


@dataclass
class TranscriptionResult:
    """Result of transcription attempt."""
    success: bool
    text: str | None = None
    error: str | None = None  # file_not_found, file_too_large, format, timeout, no_speech, api_error


class WhisperService:
    """Service for audio transcription via OpenAI Whisper API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1"
    ):
        self.api_key = api_key
        self.base_url = base_url
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._client

    async def _call_api(self, file_path: Path):
        """Call Whisper API. Separated for testing."""
        client = self._get_client()
        with open(file_path, "rb") as audio_file:
            return await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

    async def transcribe(self, file_path: Path) -> TranscriptionResult:
        """Transcribe audio file.

        Args:
            file_path: Path to audio file (ogg, mp3, m4a, wav, mp4)

        Returns:
            TranscriptionResult with success/text or error code
        """
        # Check file exists
        if not file_path.exists():
            return TranscriptionResult(success=False, error="file_not_found")

        try:
            logger.info(f"Transcribing {file_path.name} ({file_path.stat().st_size} bytes)")

            response = await self._call_api(file_path)
            text = response.text.strip() if response.text else ""

            if not text:
                return TranscriptionResult(success=False, error="no_speech")

            logger.info(f"Transcription complete: {len(text)} chars")
            return TranscriptionResult(success=True, text=text)

        except BadRequestError as e:
            error_msg = str(e).lower()
            if "size" in error_msg or "large" in error_msg or "limit" in error_msg:
                return TranscriptionResult(success=False, error="file_too_large")
            if "format" in error_msg or "codec" in error_msg:
                return TranscriptionResult(success=False, error="format")
            logger.error(f"Whisper BadRequest: {e}")
            return TranscriptionResult(success=False, error="api_error")

        except (APITimeoutError, asyncio.TimeoutError):
            return TranscriptionResult(success=False, error="timeout")

        except APIError as e:
            logger.error(f"Whisper API error: {e}")
            return TranscriptionResult(success=False, error="api_error")

        except Exception as e:
            logger.exception(f"Whisper unexpected error: {e}")
            return TranscriptionResult(success=False, error="api_error")
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_whisper_service.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/whisper.py tests/test_whisper_service.py
git commit -m "feat(whisper): add WhisperService for audio transcription"
```

---

## Task 5: Extend FileInputService for audio

**Files:**
- Modify: `src/codogram/services/file_input.py`
- Create: `tests/test_file_input_audio.py`

**Step 1: Write the failing test**

Create `tests/test_file_input_audio.py`:

```python
"""Tests for FileInputService audio handling."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from src.codogram.services.file_input import FileInputService, AudioFileInfo


class TestExtractAudioInfo:
    """Tests for extract_audio_info method."""

    def setup_method(self):
        self.service = FileInputService()

    def test_voice_message(self):
        """Extracts info from voice message."""
        message = MagicMock()
        message.voice = MagicMock(
            file_id="voice123",
            file_size=5000,
            duration=10
        )
        message.audio = None
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "voice123"
        assert result.extension == "ogg"
        assert result.size == 5000
        assert result.duration == 10

    def test_audio_file_with_name(self):
        """Extracts info from audio file with filename."""
        message = MagicMock()
        message.voice = None
        message.audio = MagicMock(
            file_id="audio456",
            file_name="song.mp3",
            file_size=1000000,
            duration=180
        )
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "audio456"
        assert result.extension == "mp3"
        assert result.size == 1000000

    def test_audio_file_no_name(self):
        """Audio without filename defaults to mp3."""
        message = MagicMock()
        message.voice = None
        message.audio = MagicMock(
            file_id="audio789",
            file_name=None,
            file_size=50000,
            duration=30
        )
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.extension == "mp3"

    def test_video_note(self):
        """Extracts info from video note (круглое видео)."""
        message = MagicMock()
        message.voice = None
        message.audio = None
        message.video_note = MagicMock(
            file_id="videonote123",
            file_size=200000,
            duration=15
        )

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "videonote123"
        assert result.extension == "mp4"
        assert result.duration == 15

    def test_no_audio_content(self):
        """Returns None for non-audio message."""
        message = MagicMock()
        message.voice = None
        message.audio = None
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is None
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_file_input_audio.py -v
```

Expected: FAIL with `ImportError: cannot import name 'AudioFileInfo'`

**Step 3: Add AudioFileInfo and extract_audio_info**

Add to `src/codogram/services/file_input.py` after `FileInfo` class (around line 15):

```python
@dataclass
class AudioFileInfo:
    """Information about audio from Telegram message."""

    file_id: str
    extension: str
    size: int
    duration: int | None = None
```

Add method to `FileInputService` class (after `extract_info` method, around line 72):

```python
    def extract_audio_info(self, message) -> AudioFileInfo | None:
        """Extract audio info from voice/audio/video_note message.

        Returns AudioFileInfo or None if no audio content.
        """
        if message.voice:
            return AudioFileInfo(
                file_id=message.voice.file_id,
                extension="ogg",
                size=message.voice.file_size or 0,
                duration=message.voice.duration,
            )

        if message.audio:
            filename = message.audio.file_name or ""
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"
            return AudioFileInfo(
                file_id=message.audio.file_id,
                extension=ext,
                size=message.audio.file_size or 0,
                duration=message.audio.duration,
            )

        if message.video_note:
            return AudioFileInfo(
                file_id=message.video_note.file_id,
                extension="mp4",
                size=message.video_note.file_size or 0,
                duration=message.video_note.duration,
            )

        return None
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_file_input_audio.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/file_input.py tests/test_file_input_audio.py
git commit -m "feat(file-input): add audio file info extraction"
```

---

## Task 6: Create audio handler

**Files:**
- Create: `src/codogram/handlers/audio.py`
- Create: `tests/test_audio_handler.py`

**Step 1: Write the failing test**

Create `tests/test_audio_handler.py`:

```python
"""Tests for audio message handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.codogram.handlers.audio import _handle_audio_message


class TestAudioHandler:
    """Tests for audio message handling."""

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        """Returns error when OPENAI_API_KEY not set."""
        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('src.codogram.handlers.audio.settings') as mock_settings:
            mock_settings.openai_api_key = None

            await _handle_audio_message(message, telegram_queue)

        # Should send error about missing config
        telegram_queue.reply.assert_called_once()
        call_args = telegram_queue.reply.call_args
        assert "OPENAI_API_KEY" in call_args[0][1] or "not configured" in call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_no_project_registered(self):
        """Silent return when no project for chat."""
        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('src.codogram.handlers.audio.settings') as mock_settings, \
             patch('src.codogram.handlers.audio._message_router') as mock_router:
            mock_settings.openai_api_key = "test-key"
            mock_router.route.return_value = MagicMock(action=MagicMock(name="NO_PROJECT"))
            mock_router.route.return_value.action.value = "no_project"

            from src.codogram.services.message_router import RouteAction
            mock_router.route.return_value.action = RouteAction.NO_PROJECT

            await _handle_audio_message(message, telegram_queue)

        # Should not send any message (silent)
        telegram_queue.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_transcription_flow(self, tmp_path):
        """Full flow: download -> save -> transcribe -> send to Claude."""
        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.from_user.id = 456
        message.message_thread_id = None
        message.bot = AsyncMock()
        message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="voice/file.ogg"))
        message.bot.download = AsyncMock()

        telegram_queue = AsyncMock()

        # Mock all dependencies
        with patch('src.codogram.handlers.audio.settings') as mock_settings, \
             patch('src.codogram.handlers.audio._message_router') as mock_router, \
             patch('src.codogram.handlers.audio._file_input') as mock_file_input, \
             patch('src.codogram.handlers.audio.WhisperService') as MockWhisper:

            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_base_url = "https://api.openai.com/v1"

            # Route result
            from src.codogram.services.message_router import RouteAction, RouteResult
            from src.codogram.session_manager import ThreadInfo
            mock_thread = MagicMock(name="main")
            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=MagicMock(cwd="/tmp/project"),
                thread=mock_thread,
                tmux_name="tmux-session",
                cwd="/tmp/project"
            )
            mock_router.send_to_tmux.return_value = True

            # File input
            from src.codogram.services.file_input import AudioFileInfo
            mock_file_input.extract_audio_info.return_value = AudioFileInfo(
                file_id="v1", extension="ogg", size=1000, duration=5
            )
            mock_file_input._build_path.return_value = tmp_path / "audio.ogg"

            # Whisper
            from src.codogram.services.whisper import TranscriptionResult
            mock_whisper_instance = AsyncMock()
            mock_whisper_instance.transcribe.return_value = TranscriptionResult(
                success=True, text="Hello world"
            )
            MockWhisper.return_value = mock_whisper_instance

            await _handle_audio_message(message, telegram_queue)

        # Should send "Transcribing..." then "«text» → Claude"
        assert telegram_queue.reply.call_count >= 2

        # Should send to tmux
        mock_router.send_to_tmux.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_audio_handler.py::TestAudioHandler::test_no_api_key_configured -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write audio handler implementation**

Create `src/codogram/handlers/audio.py`:

```python
"""Audio message handler - transcribes voice/audio/video_note via Whisper."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ContentType

from ..config import settings
from ..services.file_input import FileInputService
from ..services.message_router import MessageRouterService, RouteAction
from ..services.whisper import WhisperService
from ..telegram_queue import TelegramQueue
from ..logging_config import logger
from .. import strings

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
    thread_id = message.message_thread_id
    user_id = message.from_user.id if message.from_user else 0

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
    status_msg = await telegram_queue.reply(message, strings.AUDIO_TRANSCRIBING)

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
        tg_file = await message.bot.get_file(audio_info.file_id)
        await message.bot.download(tg_file.file_path, destination=str(file_path))

        logger.info(f"Audio saved: {file_path} ({audio_info.size} bytes)")

        # Transcribe
        whisper = WhisperService(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )
        transcription = await whisper.transcribe(file_path)

        if not transcription.success:
            error_msg = _ERROR_MESSAGES.get(
                transcription.error,
                strings.AUDIO_ERR_GENERIC.format(error=transcription.error)
            )
            await telegram_queue.edit(status_msg, error_msg)
            return

        # Show transcription and send to Claude
        text = transcription.text
        await telegram_queue.edit(status_msg, strings.AUDIO_SENT.format(text=text))

        # Send to tmux
        _message_router.send_to_tmux(result, text)

    except Exception as e:
        logger.exception(f"Audio handling failed: {e}")
        await telegram_queue.edit(
            status_msg,
            strings.AUDIO_ERR_GENERIC.format(error=str(e)[:50])
        )


@router.message(F.content_type.in_({ContentType.VOICE, ContentType.AUDIO, ContentType.VIDEO_NOTE}))
async def on_audio(message: Message, telegram_queue: TelegramQueue):
    """Route audio messages to handler."""
    await _handle_audio_message(message, telegram_queue)
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_audio_handler.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/audio.py tests/test_audio_handler.py
git commit -m "feat(audio): add handler for voice/audio/video_note transcription"
```

---

## Task 7: Wire up audio handler

**Files:**
- Modify: `src/codogram/handlers/__init__.py`
- Modify: `src/codogram/handlers/messages.py`

**Step 1: Register audio router**

In `src/codogram/handlers/__init__.py`, add import and registration:

Add import at line 4:
```python
from . import permissions, start, threads, branches, sessions, settings, shift_tab, finish, create_flow, common, messages, migration, audio
```

Add router before messages (around line 28, before `dp.include_router(messages.router)`):
```python
    dp.include_router(audio.router)         # Voice/audio/video transcription
    dp.include_router(messages.router)      # Catch-all for tmux routing (LAST!)
```

**Step 2: Remove audio blocking from messages handler**

In `src/codogram/handlers/messages.py`, remove lines 39-42:

```python
    # Block video/audio
    if message.video or message.video_note or message.audio or message.voice:
        await telegram_queue.reply(message, strings.FILE_AUDIO_VIDEO_NOT_SUPPORTED)
        return
```

Replace with just video block (video files without audio track):
```python
    # Block video files (not video_note - those are handled by audio router)
    if message.video:
        await telegram_queue.reply(message, "Video files are not supported")
        return
```

**Step 3: Verify bot starts**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
python -c "from src.codogram.handlers import register_handlers; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add src/codogram/handlers/__init__.py src/codogram/handlers/messages.py
git commit -m "feat(handlers): wire up audio router, remove audio blocking"
```

---

## Task 8: Update .env.example

**Files:**
- Create or modify: `.env.example`

**Step 1: Check if .env.example exists**

```bash
ls -la /home/superbereza/dev/codogram/.worktrees/whisper-use/.env.example 2>/dev/null || echo "Not found"
```

**Step 2: Add Whisper config section**

If file exists, append. If not, create with full example. Add these lines:

```bash
# Whisper (audio transcription)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add OpenAI config to .env.example"
```

---

## Task 9: Run full test suite

**Step 1: Run all tests**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
python -m pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 2: Fix any failures**

If failures, fix and commit fixes.

---

## Task 10: Manual E2E test

**Prerequisites:**
- Add `OPENAI_API_KEY` to `.env`
- Ask user for test chat ID

**Step 1: Start bot**

```bash
cd /home/superbereza/dev/codogram/.worktrees/whisper-use
./dev-run.sh
```

**Step 2: Send voice message via Telegram MCP**

(Requires manual voice message or test file)

**Step 3: Verify flow**

1. Bot sends `[~] Transcribing...`
2. Bot edits to `[v] «transcribed text» → Claude`
3. Text appears in Claude tmux session

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Config fields | config.py |
| 2 | Audio strings | strings.py |
| 3 | OpenAI dependency | pyproject.toml |
| 4 | WhisperService | services/whisper.py |
| 5 | FileInput audio | services/file_input.py |
| 6 | Audio handler | handlers/audio.py |
| 7 | Wire up handler | handlers/__init__.py, messages.py |
| 8 | .env.example | .env.example |
| 9 | Test suite | - |
| 10 | Manual E2E | - |
