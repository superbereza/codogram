# src/codogram/services/setup/base_dir.py
"""Base directory validation service."""
from pathlib import Path

from ...config import settings


def check_base_dir() -> Path | None:
    """Check if base_dir is configured and exists.

    Returns:
        Path to base_dir if valid, None otherwise
    """
    base_dir = settings.base_dir
    if not base_dir:
        return None

    path = Path(base_dir).expanduser()
    if not path.exists():
        return None

    return path
