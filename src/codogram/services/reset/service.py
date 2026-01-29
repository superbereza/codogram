"""Simple reset service - no FlowAction enum needed."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ... import strings
from ...tmux.launcher import is_tmux_session_exists
from ...tmux.session import kill_tmux_session

if TYPE_CHECKING:
    from ...core.session_manager import ProjectManager, ProjectState


@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    success: bool
    error: str | None = None


class ResetService:
    """Service for /hard_reset command."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def is_setup_phase(self, project: "ProjectState") -> bool:
        """Check if project is in setup phase."""
        main_thread = project.threads.get(None)
        if main_thread and main_thread.session_id:
            return False
        if project.session_id:
            return False
        return True

    def cleanup(self, project: "ProjectState", delete_directory: bool) -> CleanupResult:
        """Full project cleanup."""
        # 1. Kill all tmux sessions
        for thread in project.threads.values():
            tmux_name = thread.get_tmux_session(project.project_name)
            if is_tmux_session_exists(tmux_name):
                kill_tmux_session(tmux_name)

        # 2. Remove worktrees
        if project.cwd:
            for thread in project.threads.values():
                if thread.worktree_path:
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", thread.worktree_path],
                            cwd=project.cwd, capture_output=True,
                        )
                    except Exception:
                        pass

        # 3. Delete directory
        cleanup_failed = False
        if delete_directory and project.cwd:
            shutil.rmtree(project.cwd, ignore_errors=True)
            if Path(project.cwd).exists():
                cleanup_failed = True

        # 4. Remove from config
        if project.project_name in self.pm.projects:
            del self.pm.projects[project.project_name]
            self.pm._save()

        if cleanup_failed:
            return CleanupResult(
                success=False,
                error=strings.RESET_CLEANUP_FAILED.format(path=project.cwd)
            )
        return CleanupResult(success=True)
