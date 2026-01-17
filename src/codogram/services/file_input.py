"""File input service for handling images and documents from Telegram."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable


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
