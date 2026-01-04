"""StartFlowService - business logic for /start flow."""
from dataclasses import dataclass
from enum import Enum


class FlowAction(Enum):
    """All possible outcomes of a flow step."""

    # Questions - need user input
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"

    # Actions - perform operation
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"
    SELECT_TMUX = "select_tmux"

    # Errors
    ERROR = "error"


@dataclass
class FlowResult:
    """Result of a flow step."""

    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_session: str | None = None
    tmux_list: list[str] | None = None
    message: str | None = None
    error: str | None = None
