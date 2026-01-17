"""File input service for handling images and documents from Telegram."""
from dataclasses import dataclass
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
