"""Utility functions for start flow."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.session_manager import ProjectState


def build_announcement(project_name: str, tmux_name: str, is_forum: bool) -> str:
    """Build project ready announcement."""
    commands = [
        "• /esc — cancel operation",
        "• /clear_context — clear context",
        "• /auto_accept — toggle auto-accept",
    ]
    if is_forum:
        commands.extend([
            "• /new_chat — new topic or branch",
            "• /finish_chat — merge and archive",
        ])

    return f"""`[v]` Project `{project_name}` ready

Commands available in this chat:
{chr(10).join(commands)}

To see Claude UI: `tmux attach -t {tmux_name}`"""


def build_thread_announcement(thread_name: str, tmux_name: str) -> str:
    """Build short announcement for topics."""
    return f"""`[v]` Thread `{thread_name}` running

To see Claude UI: `tmux attach -t {tmux_name}`"""


def is_setup_phase(project: "ProjectState") -> bool:
    """Check if project is in setup phase (Claude never ran)."""
    main_thread = project.threads.get(None)
    if main_thread and main_thread.session_id:
        return False
    if project.session_id:  # Legacy
        return False
    return True
