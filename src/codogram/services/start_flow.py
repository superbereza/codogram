"""StartFlowService - business logic for /start flow."""
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ..domain.validators import (
    is_valid_project_name,
    MAX_PROJECT_NAME_LENGTH,
)
from ..project_launcher import resolve_project_path

if TYPE_CHECKING:
    from ..session_manager import ProjectManager


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


class StartFlowService:
    """Business logic for /start flow (non-topic mode)."""

    def __init__(self, project_manager: "ProjectManager", launch_service):
        self.pm = project_manager
        self.launch_service = launch_service

    def handle_start(
        self,
        chat_id: int,
        args: list[str],
        chat_title: str | None = None,
    ) -> FlowResult:
        """Entry point for /start command (non-topic mode).

        Args:
            chat_id: Telegram chat ID
            args: Command arguments (e.g., ["project-name"])
            chat_title: Chat title for auto-naming

        Returns:
            FlowResult with next action to take
        """
        # Case 1: project name provided in args
        if args:
            project_name = args[0]
            return self._validate_and_start(chat_id, project_name)

        # TODO: Other cases in next tasks
        return FlowResult(action=FlowAction.ASK_PROJECT_NAME)

    def _validate_and_start(self, chat_id: int, project_name: str) -> FlowResult:
        """Validate project name and start flow."""
        # Check length first
        if len(project_name) > MAX_PROJECT_NAME_LENGTH:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Project name too long (max {MAX_PROJECT_NAME_LENGTH} chars)",
            )

        # Check valid characters
        if not is_valid_project_name(project_name):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Project name can only contain letters, digits, - and _",
            )

        return self._start_project_flow(chat_id, project_name)

    def _start_project_flow(self, chat_id: int, project_name: str) -> FlowResult:
        """Resolve path and decide next step."""
        project = self.pm.get_or_create(project_name)
        project.chat_id = chat_id

        # Get path
        if project.cwd:
            path = project.cwd
            exists = True  # If cwd is set, assume it exists
        else:
            path_result = resolve_project_path(project_name, None)
            path = path_result.path
            exists = path_result.exists

        if exists:
            project.cwd = path
            # TODO: _connect_or_launch in next task
            return FlowResult(
                action=FlowAction.ASK_LAUNCH_CONFIRM,
                project=project_name,
                path=path,
            )
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
            )
