# src/codogram/services/setup/folder_list.py
"""Folder listing service for connect flow."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def list_available_folders(
    base_dir: Path,
    connected: set[str],
) -> list[str]:
    """List folders available for connection.

    Args:
        base_dir: Base directory to scan
        connected: Set of folder names already connected to Codogram

    Returns:
        Sorted list of available folder names
    """
    folders = []

    try:
        for item in base_dir.iterdir():
            # Skip non-directories
            if not item.is_dir():
                continue

            # Skip hidden folders
            if item.name.startswith("."):
                continue

            # Skip symlinks
            if item.is_symlink():
                continue

            # Skip already connected
            if item.name in connected:
                continue

            folders.append(item.name)
    except PermissionError as e:
        logger.warning(f"Cannot list {base_dir}: {e}")
        return []

    return sorted(folders)


def get_connected_folders() -> dict[str, int]:
    """Get dict of folder_name -> chat_id for connected projects.

    Returns:
        Dict mapping folder names to their chat IDs
    """
    from ...core.session_manager import ProjectManager

    pm = ProjectManager()
    result = {}

    for project_name, project in pm.projects.items():
        if project.chat_id:
            result[project_name] = project.chat_id

    return result


def get_chat_link(chat_id: int, chat_type: str) -> str | None:
    """Generate t.me link for a chat.

    Args:
        chat_id: Telegram chat ID
        chat_type: Chat type (supergroup, group, etc.)

    Returns:
        URL string or None if not possible
    """
    if chat_type == "supergroup":
        # Supergroups have t.me/c/{id} links
        # chat_id = -1001234567890 → link_id = 1234567890
        link_id = str(abs(chat_id))[3:]  # remove -100 prefix
        return f"https://t.me/c/{link_id}"

    # Regular groups don't have stable links
    return None
