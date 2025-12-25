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
