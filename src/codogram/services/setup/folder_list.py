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
    from ...session_manager import ProjectManager

    pm = ProjectManager()
    result = {}

    for project_name, project_data in pm.projects.items():
        result[project_name] = project_data.get("chat_id")

    return result
