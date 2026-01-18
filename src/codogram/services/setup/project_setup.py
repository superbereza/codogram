# src/codogram/services/setup/project_setup.py
"""Project setup service - creates directory and registers project."""
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SetupResult:
    """Result of project setup."""
    success: bool
    error: str | None = None


async def setup_project(
    project_name: str,
    target_dir: Path,
    chat_id: int,
    chat_title: str,
    chat_type: str,
) -> SetupResult:
    """Set up project directory and register in config.

    Note: tmux creation and Claude launch are handled by launch_with_animation.

    Args:
        project_name: Project/folder name
        target_dir: Full path to project directory
        chat_id: Telegram chat ID
        chat_title: Chat title for config
        chat_type: Chat type (group/supergroup)

    Returns:
        SetupResult with success/error
    """
    created_dir = False

    try:
        # Create directory if needed
        if not target_dir.exists():
            target_dir.mkdir(parents=True)
            created_dir = True
            logger.info(f"Created directory: {target_dir}")

        # Register project in config
        from ...session_manager import project_manager
        project = project_manager.get_or_create(project_name)
        project.chat_id = chat_id
        project.cwd = str(target_dir)
        project_manager._save()

        return SetupResult(success=True)

    except Exception as e:
        logger.exception(f"Project setup failed: {e}")

        # Rollback - delete dir if we created it
        if created_dir and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
                logger.info(f"Rolled back: deleted {target_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Rollback failed: {cleanup_error}")

        return SetupResult(success=False, error=str(e))
