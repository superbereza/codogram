# src/codogram/services/setup/project_setup.py
"""Project setup service with atomic operations and rollback."""
import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...tmux import TmuxSession

logger = logging.getLogger(__name__)


def create_session_name(project_name: str) -> str:
    """Generate tmux session name from project name."""
    return f"claude-{project_name}"


async def create_tmux_session(name: str, cwd: str) -> bool:
    """Create a tmux session. Returns True on success."""
    try:
        session = TmuxSession(name, cwd)
        session.create()
        return session.exists()
    except Exception as e:
        logger.warning(f"Failed to create tmux session: {e}")
        return False


@dataclass
class SetupResult:
    """Result of project setup."""
    success: bool
    error: str | None = None
    tmux_name: str | None = None


async def setup_project(
    project_name: str,
    target_dir: Path,
    chat_id: int,
    chat_title: str,
    chat_type: str,
) -> SetupResult:
    """Set up project with atomic operations.

    Phases:
    1. Filesystem - create dir if needed (rollback: delete)
    2. Runtime - create tmux, launch Claude, save config

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
    tmux_name = None

    try:
        # Lazy imports to avoid circular dependencies and config loading at import time
        from ...session_manager import ProjectManager
        from ...services.launch import launch_claude

        # Phase 1: Filesystem
        if not target_dir.exists():
            target_dir.mkdir(parents=True)
            created_dir = True
            logger.info(f"Created directory: {target_dir}")

        # Phase 2: Runtime
        tmux_name = create_session_name(project_name)

        # Create tmux session
        success = await create_tmux_session(tmux_name, str(target_dir))
        if not success:
            raise RuntimeError("Failed to create tmux session")

        # Launch Claude
        launch_result = await launch_claude(tmux_name)
        if not launch_result.success:
            raise RuntimeError(f"Failed to launch Claude: {launch_result.error}")

        # Save to config
        pm = ProjectManager()
        pm.register_project(
            project_name=project_name,
            chat_id=chat_id,
            chat_title=chat_title,
            chat_type=chat_type,
            tmux_name=tmux_name,
            cwd=str(target_dir),
        )

        return SetupResult(success=True, tmux_name=tmux_name)

    except Exception as e:
        logger.exception(f"Project setup failed: {e}")

        # Rollback Phase 2 - kill tmux if created
        if tmux_name:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tmux", "kill-session", "-t", tmux_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception:
                pass

        # Rollback Phase 1 - delete dir if we created it
        if created_dir and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
                logger.info(f"Rolled back: deleted {target_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Rollback failed: {cleanup_error}")

        return SetupResult(success=False, error=str(e))
