# Image and File Input Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to send images and files via Telegram to Claude Code for analysis.

**Architecture:** Service with callback pattern — handler provides download function, service orchestrates validation/path/download/result. Service doesn't know about aiogram.

**Tech Stack:** aiogram (Telegram), pathlib (file ops), datetime (filenames)

---

## Task 1: Domain Types

**Files:**
- Create: `src/codogram/services/file_input.py`
- Create: `tests/unit/services/test_file_input.py`

### Step 1: Write failing test for FileInfo and FileInputResult

```python
# tests/unit/services/test_file_input.py
"""Tests for file input service."""
from pathlib import Path


class TestDomainTypes:
    def test_file_info_creation(self):
        from codogram.services.file_input import FileInfo

        info = FileInfo(file_id="abc123", extension="png", size=1000)

        assert info.file_id == "abc123"
        assert info.extension == "png"
        assert info.size == 1000

    def test_file_input_result_success(self):
        from codogram.services.file_input import FileInputResult

        result = FileInputResult(success=True, path=Path("/tmp/test.png"))

        assert result.success is True
        assert result.path == Path("/tmp/test.png")
        assert result.error is None

    def test_file_input_result_error(self):
        from codogram.services.file_input import FileInputResult

        result = FileInputResult(success=False, error="too_large")

        assert result.success is False
        assert result.path is None
        assert result.error == "too_large"
```

### Step 2: Run test to verify it fails

```bash
cd /home/superbereza/dev/codogram/.worktrees/pic-support
pytest tests/unit/services/test_file_input.py::TestDomainTypes -v
```

Expected: FAIL with `ModuleNotFoundError`

### Step 3: Write domain types

```python
# src/codogram/services/file_input.py
"""File input service for handling images and documents from Telegram."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable


@dataclass
class FileInfo:
    """Information about a file from Telegram message."""
    file_id: str
    extension: str
    size: int


@dataclass
class FileInputResult:
    """Result of file save operation."""
    success: bool = False
    path: Path | None = None
    error: str | None = None  # "unsupported_type", "too_large", "download_failed"


# Type alias for download callback
DownloadFn = Callable[[str, str], Awaitable[None]]  # (file_id, destination) -> None
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/services/test_file_input.py::TestDomainTypes -v
```

Expected: 3 passed

### Step 5: Commit

```bash
git add src/codogram/services/file_input.py tests/unit/services/test_file_input.py
git commit -m "$(cat <<'EOF'
feat(file-input): add domain types

- FileInfo dataclass for file metadata
- FileInputResult for operation results with error field
- DownloadFn type alias for callback pattern

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: FileInputService - extract_info

**Files:**
- Modify: `src/codogram/services/file_input.py`
- Modify: `tests/unit/services/test_file_input.py`

### Step 1: Write failing tests for extract_info

```python
# Add to tests/unit/services/test_file_input.py
from unittest.mock import MagicMock


class TestExtractInfo:
    def test_extract_photo(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 5000

        message = MagicMock()
        message.photo = [MagicMock(file_size=100), photo]  # Largest last
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is not None
        assert result.file_id == "photo123"
        assert result.extension == "jpg"
        assert result.size == 5000

    def test_extract_document_allowed(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        doc = MagicMock()
        doc.file_id = "doc456"
        doc.file_name = "report.pdf"
        doc.file_size = 10000

        message = MagicMock()
        message.photo = None
        message.document = doc
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is not None
        assert result.file_id == "doc456"
        assert result.extension == "pdf"
        assert result.size == 10000

    def test_extract_document_blocked_extension(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        doc = MagicMock()
        doc.file_id = "exe123"
        doc.file_name = "virus.exe"
        doc.file_size = 1000

        message = MagicMock()
        message.photo = None
        message.document = doc
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is None

    def test_extract_video_blocked(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = MagicMock()
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is None

    def test_extract_audio_blocked(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = None
        message.audio = MagicMock()
        message.voice = None

        result = service.extract_info(message)

        assert result is None
```

### Step 2: Run test to verify it fails

```bash
pytest tests/unit/services/test_file_input.py::TestExtractInfo -v
```

Expected: FAIL with `AttributeError: 'FileInputService' object has no attribute 'extract_info'`

### Step 3: Add FileInputService with extract_info

```python
# Add to src/codogram/services/file_input.py

class FileInputService:
    """Handle file downloads and path generation for Telegram media."""

    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp",  # images
        "pdf", "txt", "md", "json", "csv", "xml", "yaml", "yml"  # docs
    }
    MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20MB

    def extract_info(self, message) -> FileInfo | None:
        """Extract file info from Telegram message.

        Returns FileInfo or None if blocked (video/audio/unsupported type).
        """
        # Block video and audio
        if message.video or message.audio or message.voice:
            return None

        # Handle photo (take largest)
        if message.photo:
            photo = message.photo[-1]  # Largest size is last
            return FileInfo(
                file_id=photo.file_id,
                extension="jpg",  # Telegram photos are JPEG
                size=photo.file_size or 0,
            )

        # Handle document
        if message.document:
            doc = message.document
            filename = doc.file_name or "file"
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

            if ext not in self.ALLOWED_EXTENSIONS:
                return None

            return FileInfo(
                file_id=doc.file_id,
                extension=ext,
                size=doc.file_size or 0,
            )

        return None
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/services/test_file_input.py::TestExtractInfo -v
```

Expected: 5 passed

### Step 5: Commit

```bash
git add -u
git commit -m "$(cat <<'EOF'
feat(file-input): add extract_info method

- Extract FileInfo from photo/document messages
- Block video/audio/voice
- Validate extension against whitelist

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Path Building

**Files:**
- Modify: `src/codogram/services/file_input.py`
- Modify: `tests/unit/services/test_file_input.py`

### Step 1: Write failing tests for _build_path

```python
# Add to tests/unit/services/test_file_input.py
from freezegun import freeze_time


class TestBuildPath:
    @freeze_time("2026-01-17 04:35:12")
    def test_build_path_basic(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        path = service._build_path(
            cwd=str(tmp_path),
            thread_name="celestial",
            thread_id=1328,
            user_id=456,
            extension="png"
        )

        assert path.parent.exists()
        assert "celestial" in str(path)
        assert "20260117-043512" in str(path)
        assert "thread_1328" in str(path)
        assert "user_456" in str(path)
        assert path.suffix == ".png"

    @freeze_time("2026-01-17 04:35:12")
    def test_build_path_main_thread(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        path = service._build_path(
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            extension="jpg"
        )

        assert "main" in str(path)
        assert "thread_main" in str(path)

    def test_build_path_traversal_blocked(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        try:
            service._build_path(
                cwd=str(tmp_path),
                thread_name="../../../etc",
                thread_id=1,
                user_id=1,
                extension="txt"
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "outside" in str(e).lower()
```

### Step 2: Run test to verify it fails

```bash
pytest tests/unit/services/test_file_input.py::TestBuildPath -v
```

Expected: FAIL with `AttributeError`

### Step 3: Add _build_path method

```python
# Add to FileInputService class in src/codogram/services/file_input.py

    def _build_path(
        self,
        cwd: str,
        thread_name: str,
        thread_id: int | None,
        user_id: int,
        extension: str
    ) -> Path:
        """Build safe file path with validation.

        Creates parent directories. Validates path is inside input-files.

        Raises:
            ValueError: If path traversal detected
        """
        # Generate filename
        dt = datetime.now().strftime("%Y%m%d-%H%M%S")
        tid = f"thread_{thread_id}" if thread_id else "thread_main"
        filename = f"{dt}-{tid}-user_{user_id}.{extension}"

        # Build path
        base = Path(cwd) / "tmp" / "input-files"
        path = base / thread_name / filename

        # Create directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Validate - prevent path traversal
        resolved = path.resolve()
        base_resolved = base.resolve()

        if not resolved.is_relative_to(base_resolved):
            raise ValueError(f"Path {resolved} is outside allowed directory {base_resolved}")

        return path
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/services/test_file_input.py::TestBuildPath -v
```

Expected: 3 passed

### Step 5: Commit

```bash
git add -u
git commit -m "$(cat <<'EOF'
feat(file-input): add path building with traversal protection

- _build_path() generates safe filenames
- Format: datetime-thread_id-user_id.ext
- Uses is_relative_to() for path traversal check

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: save_file with Callback

**Files:**
- Modify: `src/codogram/services/file_input.py`
- Modify: `tests/unit/services/test_file_input.py`

### Step 1: Write failing tests for save_file

```python
# Add to tests/unit/services/test_file_input.py
import pytest
from unittest.mock import AsyncMock


class TestSaveFile:
    @pytest.mark.asyncio
    @freeze_time("2026-01-17 04:35:12")
    async def test_save_file_success(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(file_id="abc123", extension="png", size=1000)

        async def mock_download(file_id, destination):
            Path(destination).write_bytes(b"fake image data")

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="celestial",
            thread_id=1328,
            user_id=456,
            download_fn=mock_download
        )

        assert result.success is True
        assert result.path is not None
        assert result.path.exists()
        assert result.path.read_bytes() == b"fake image data"
        assert "celestial" in str(result.path)

    @pytest.mark.asyncio
    async def test_save_file_too_large(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(
            file_id="abc123",
            extension="png",
            size=25 * 1024 * 1024  # 25MB > 20MB limit
        )

        async def mock_download(file_id, destination):
            pass

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            download_fn=mock_download
        )

        assert result.success is False
        assert result.error == "too_large"

    @pytest.mark.asyncio
    async def test_save_file_download_fails(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(file_id="abc123", extension="png", size=1000)

        async def failing_download(file_id, destination):
            raise Exception("Network error")

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            download_fn=failing_download
        )

        assert result.success is False
        assert result.error == "download_failed"
```

### Step 2: Run test to verify it fails

```bash
pytest tests/unit/services/test_file_input.py::TestSaveFile -v
```

Expected: FAIL with `AttributeError`

### Step 3: Add save_file method

```python
# Add to FileInputService class in src/codogram/services/file_input.py

    async def save_file(
        self,
        file_info: FileInfo,
        cwd: str,
        thread_name: str,
        thread_id: int | None,
        user_id: int,
        download_fn: DownloadFn
    ) -> FileInputResult:
        """Validate, build path, download via callback, return result.

        Args:
            file_info: File metadata from extract_info()
            cwd: Project working directory
            thread_name: Thread name for folder
            thread_id: Thread ID for filename (None for main)
            user_id: User ID for filename
            download_fn: Callback to download file (handler provides this)

        Returns:
            FileInputResult with success/error/path
        """
        # Validate size
        if file_info.size > self.MAX_SIZE_BYTES:
            return FileInputResult(success=False, error="too_large")

        # Build path
        try:
            path = self._build_path(cwd, thread_name, thread_id, user_id, file_info.extension)
        except ValueError:
            return FileInputResult(success=False, error="path_error")

        # Download via callback
        try:
            await download_fn(file_info.file_id, str(path))
        except Exception:
            # Cleanup partial file
            path.unlink(missing_ok=True)
            return FileInputResult(success=False, error="download_failed")

        return FileInputResult(success=True, path=path)
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/services/test_file_input.py::TestSaveFile -v
```

Expected: 3 passed

### Step 5: Commit

```bash
git add -u
git commit -m "$(cat <<'EOF'
feat(file-input): add save_file with callback pattern

- Validates size before download
- Calls download_fn callback (provided by handler)
- Returns FileInputResult with error details
- Cleans up partial files on failure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: format_message

**Files:**
- Modify: `src/codogram/services/file_input.py`
- Modify: `tests/unit/services/test_file_input.py`

### Step 1: Write failing tests for format_message

```python
# Add to tests/unit/services/test_file_input.py

class TestFormatMessage:
    def test_format_single_file_no_caption(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption=None,
            paths=[Path("/project/tmp/input-files/main/test.png")],
            cwd="/project"
        )

        assert msg == "📎 ./tmp/input-files/main/test.png"

    def test_format_single_file_with_caption(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption="Check this mockup",
            paths=[Path("/project/tmp/input-files/celestial/design.png")],
            cwd="/project"
        )

        assert msg == "Check this mockup\n\n📎 ./tmp/input-files/celestial/design.png"

    def test_format_multiple_files(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption="Review these",
            paths=[
                Path("/project/tmp/input-files/main/a.png"),
                Path("/project/tmp/input-files/main/b.png"),
            ],
            cwd="/project"
        )

        expected = "Review these\n\n📎 ./tmp/input-files/main/a.png\n📎 ./tmp/input-files/main/b.png"
        assert msg == expected
```

### Step 2: Run test to verify it fails

```bash
pytest tests/unit/services/test_file_input.py::TestFormatMessage -v
```

Expected: FAIL with `AttributeError`

### Step 3: Add format_message method

```python
# Add to FileInputService class in src/codogram/services/file_input.py

    def format_message(self, caption: str | None, paths: list[Path], cwd: str) -> str:
        """Format message with caption and file paths for tmux.

        Args:
            caption: Optional user caption
            paths: List of absolute file paths
            cwd: Project working directory (for relative paths)

        Returns:
            Formatted message string for tmux
        """
        cwd_path = Path(cwd)

        path_lines = []
        for p in paths:
            try:
                rel = p.relative_to(cwd_path)
                path_lines.append(f"📎 ./{rel}")
            except ValueError:
                path_lines.append(f"📎 {p}")

        paths_str = "\n".join(path_lines)

        if caption:
            return f"{caption}\n\n{paths_str}"
        return paths_str
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/services/test_file_input.py::TestFormatMessage -v
```

Expected: 3 passed

### Step 5: Commit

```bash
git add -u
git commit -m "$(cat <<'EOF'
feat(file-input): add format_message for tmux

- Formats paths relative to cwd with 📎 prefix
- Handles optional caption
- Supports multiple files

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Handler Integration

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Create: `tests/unit/handlers/test_messages_file.py`

### Step 1: Write failing test for file handling

```python
# tests/unit/handlers/test_messages_file.py
"""Tests for file message handling."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path


class TestFileMessageHandler:
    @pytest.mark.asyncio
    async def test_photo_sent_to_tmux(self, tmp_path):
        """Photo message should be downloaded and sent to tmux."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult
        from codogram.services.file_input import FileInfo, FileInputResult

        # Mock photo
        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 1000

        # Mock message
        message = MagicMock()
        message.text = None
        message.caption = "Check this"
        message.photo = [photo]
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = 1328
        message.from_user = MagicMock(id=456)
        message.bot = MagicMock()
        message.bot.download = AsyncMock()

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        mock_project = MagicMock()
        mock_project.cwd = str(tmp_path)
        mock_thread = MagicMock()
        mock_thread.name = "celestial"
        mock_thread.session_id = "sess123"

        with patch("codogram.handlers.messages._message_router") as mock_router, \
             patch("codogram.handlers.messages._file_input") as mock_file_svc, \
             patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):

            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=mock_project,
                thread=mock_thread,
                tmux_name="claude-test",
                cwd=str(tmp_path)
            )

            mock_file_svc.extract_info.return_value = FileInfo(
                file_id="photo123", extension="jpg", size=1000
            )
            mock_file_svc.save_file = AsyncMock(return_value=FileInputResult(
                success=True, path=tmp_path / "test.jpg"
            ))
            mock_file_svc.format_message.return_value = "Check this\n\n📎 ./test.jpg"

            mock_router.send_to_tmux.return_value = True

            await on_message(message, telegram_queue)

            # Verify service was called with callback
            mock_file_svc.save_file.assert_called_once()
            call_kwargs = mock_file_svc.save_file.call_args[1]
            assert call_kwargs["thread_name"] == "celestial"
            assert "download_fn" in call_kwargs

            # Verify sent to tmux
            mock_router.send_to_tmux.assert_called_once()

    @pytest.mark.asyncio
    async def test_video_rejected(self):
        """Video messages should be rejected with friendly message."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult

        message = MagicMock()
        message.text = None
        message.photo = None
        message.document = None
        message.video = MagicMock()
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=123)

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        with patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):
            await on_message(message, telegram_queue)

            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "video" in reply_text.lower() or "audio" in reply_text.lower()
```

### Step 2: Run test to verify it fails

```bash
pytest tests/unit/handlers/test_messages_file.py -v
```

Expected: FAIL

### Step 3: Update handler

```python
# src/codogram/handlers/messages.py - full replacement
"""Message routing handler - routes messages to tmux sessions."""
import asyncio

from aiogram import Router
from aiogram.types import Message

from ..services.message_router import MessageRouterService, RouteAction
from ..services.file_input import FileInputService
from ..session_manager import project_manager, ThreadInfo
from ..telegram_queue import TelegramQueue
from ..logging_config import logger
from .create_flow import handle_name_input

router = Router(name="messages")

# Service instances
_message_router = MessageRouterService()
_file_input = FileInputService()

# Error messages for file operations
_FILE_ERROR_MESSAGES = {
    "too_large": "File too large (max 20MB)",
    "download_failed": "Download failed, please try again",
    "path_error": "Failed to save file",
}


@router.message()
async def on_message(message: Message, telegram_queue: TelegramQueue):
    """Route regular messages to tmux sessions."""
    text = message.text
    has_file = bool(message.photo or message.document)

    # Handle video/audio with friendly message
    if message.video or message.audio or message.voice:
        await telegram_queue.reply(message, "Video and audio not supported yet. Coming soon with Whisper!")
        return

    # Skip if no text and no file
    if not text and not has_file:
        return

    # Log
    content_preview = text[:100] if text else f"[file: {message.caption or 'no caption'}]"
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
    result = _message_router.route(chat_id, thread_id, text or "")

    match result.action:
        case RouteAction.NO_PROJECT:
            return

        case RouteAction.CREATE_PENDING:
            thread = ThreadInfo(thread_id=thread_id, name="pending")
            result.project.threads[thread_id] = thread
            project_manager._save()
            await telegram_queue.reply(message, "Use /start or /thread_create to connect Claude to this topic")
            return

        case RouteAction.SKIP_PENDING:
            return

        case RouteAction.START_BINDING:
            await _start_binding(message, result)
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
    """Send message content (text or file) to tmux."""
    if not result.tmux_name or not result.cwd:
        return False

    # Handle file messages
    if message.photo or message.document:
        file_info = _file_input.extract_info(message)
        if not file_info:
            await telegram_queue.reply(message, "File type not supported")
            return False

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
            return False

        content = _file_input.format_message(message.caption, [save_result.path], result.cwd)
    else:
        content = message.text

    return _message_router.send_to_tmux(result, content)


async def _start_binding(message: Message, result):
    """Start session binding for unbound thread."""
    from ..history_watcher import poll_for_session_thread
    from .. import main

    thread = result.thread
    project = result.project

    thread.last_sent_message = message.text or message.caption or ""

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
```

### Step 4: Run test to verify it passes

```bash
pytest tests/unit/handlers/test_messages_file.py -v
```

Expected: PASS

### Step 5: Commit

```bash
git add src/codogram/handlers/messages.py tests/unit/handlers/test_messages_file.py
git commit -m "$(cat <<'EOF'
feat(file-input): integrate file handling into message handler

- Handle photo and document messages
- Create download callback for service
- Block video/audio with friendly message
- Send formatted path to tmux

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Full Test Suite

### Step 1: Run all tests

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass

### Step 2: Run linter

```bash
ruff check src/codogram/services/file_input.py src/codogram/handlers/messages.py
```

### Step 3: Fix any issues and commit

---

## Task 8: E2E Test

### Step 1: Start bot in worktree

```bash
cd /home/superbereza/dev/codogram/.worktrees/pic-support
./dev-run.sh
```

### Step 2: Test via Telegram

Send a photo to the test chat and verify Claude describes it.

### Step 3: Restore main bot

```bash
cd /home/superbereza/dev/codogram
./restart.sh
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Domain types | 3 |
| 2 | extract_info | 5 |
| 3 | _build_path | 3 |
| 4 | save_file | 3 |
| 5 | format_message | 3 |
| 6 | Handler | 2 |
| 7 | Full suite | - |
| 8 | E2E | - |

**Total unit tests:** 19
