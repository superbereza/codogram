# src/codogram/project_launcher.py
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
    """Check if tmux session exists.

    Uses '=' prefix for exact session name matching.
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", f"={session_name}"],
        capture_output=True,
    )
    return result.returncode == 0


def create_project_directory(path: str) -> LaunchResult:
    """Create project directory."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_init(path: str) -> LaunchResult:
    """Initialize git repository."""
    try:
        result = subprocess.run(
            ["git", "init"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=result.stderr)
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_init_with_github(path: str, private: bool = True) -> LaunchResult:
    """Initialize git and create GitHub repo."""
    try:
        # git init
        init_result = git_init(path)
        if not init_result.success:
            return init_result

        # gh repo create
        visibility = "--private" if private else "--public"
        result = subprocess.run(
            ["gh", "repo", "create", visibility, "--source", ".", "--push"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"gh error: {result.stderr}")
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_clone(path: str, repo_url: str) -> LaunchResult:
    """Clone repository into path."""
    try:
        # Clone into current directory (path should be empty or not exist)
        parent = str(Path(path).parent)
        name = Path(path).name
        result = subprocess.run(
            ["git", "clone", repo_url, name],
            cwd=parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"git clone error: {result.stderr}")
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


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
