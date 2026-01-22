"""Simple restart service - no FlowAction enum needed."""
from typing import TYPE_CHECKING

from ...tmux.launcher import is_tmux_session_exists
from ...tmux.session import kill_tmux_session

if TYPE_CHECKING:
    from ...core.session_manager import ProjectManager


class RestartService:
    """Service for /restart command."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def get_session_to_restart(
        self, chat_id: int, thread_id: int | None = None
    ) -> str | None:
        """Get tmux session name to restart, or None if nothing to restart."""
        project = self.pm.get_by_chat(chat_id)
        if not project:
            return None

        if thread_id:
            thread = project.threads.get(thread_id)
            if not thread:
                return None
            tmux_name = thread.get_tmux_session(project.project_name)
        else:
            main_thread = project.threads.get(None)
            if main_thread:
                tmux_name = main_thread.get_tmux_session(project.project_name)
            elif project.tmux_session:
                tmux_name = project.tmux_session
            else:
                return None

        if not is_tmux_session_exists(tmux_name):
            return None

        return tmux_name

    def kill_session(self, tmux_name: str) -> bool:
        """Kill tmux session. Returns True if killed."""
        return kill_tmux_session(tmux_name)
