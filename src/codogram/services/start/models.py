"""Models for start flow."""
from dataclasses import dataclass
from enum import Enum


class FlowAction(Enum):
    """Outcomes of start flow steps.

    Note: Restart/Reset have their own simple services without enums.
    """
    # Questions
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CLONE_URL_RETRY = "ask_clone_url_retry"
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"
    ASK_TMUX_SELECT = "ask_tmux_select"  # Renamed from SELECT_TMUX

    # Actions
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"

    # Errors
    ERROR = "error"

    # Thread-specific
    THREAD_SHOW_STATUS = "thread_show_status"
    THREAD_LAUNCH = "thread_launch"
    UPGRADE_PENDING_THREAD = "upgrade_pending_thread"
    REGISTER_UNKNOWN_TOPIC = "register_unknown_topic"


@dataclass
class FlowResult:
    """Result of a start flow step."""
    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_session: str | None = None
    tmux_list: list[str] | None = None
    error: str | None = None
    thread_id: int | None = None
    thread_name: str | None = None
