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
