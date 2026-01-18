# src/codogram/services/setup/init_project.py
"""Project initialization - creates directory and registers in config."""
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class InitResult:
    """Result of project initialization."""
    success: bool
    error: str | None = None


async def init_project(
    project_name: str,
    target_dir: Path,
    chat_id: int,
) -> InitResult:
    """Initialize project: create directory and register in config.

    Note: tmux and Claude launch are handled separately by launch_with_animation.

    Args:
        project_name: Project/folder name
        target_dir: Full path to project directory
        chat_id: Telegram chat ID

    Returns:
        InitResult with success/error
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

        return InitResult(success=True)

    except Exception as e:
        logger.exception(f"Project init failed: {e}")

        # Rollback - delete dir if we created it
        if created_dir and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
                logger.info(f"Rolled back: deleted {target_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Rollback failed: {cleanup_error}")

        return InitResult(success=False, error=str(e))
