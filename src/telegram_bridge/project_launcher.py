# src/telegram_bridge/project_launcher.py
"""Project launcher - resolve paths and start Claude in tmux."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import settings


@dataclass
class ProjectPathResult:
    path: str
    exists: bool


@dataclass
class LaunchResult:
    success: bool
    error: str | None = None
    tmux_session: str | None = None


def resolve_project_path(project_name: str, custom_path: str | None) -> ProjectPathResult:
    """Resolve project path using custom path or convention."""
    if custom_path:
        path = Path(custom_path).expanduser()
    else:
        path = Path(settings.base_dir).expanduser() / project_name

    return ProjectPathResult(
        path=str(path),
        exists=path.is_dir(),
    )


def is_tmux_session_exists(session_name: str) -> bool:
    """Check if tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


def create_tmux_with_claude(session_name: str, project_path: str) -> LaunchResult:
    """Create new tmux session and start Claude."""
    try:
        # Create detached tmux session in project directory
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", project_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"tmux error: {result.stderr}")

        # Send claude command
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "claude", "Enter"],
            capture_output=True,
        )

        return LaunchResult(success=True, tmux_session=session_name)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))
