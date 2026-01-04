"""StartFlowService - business logic for /start flow."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from ..domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    MAX_PROJECT_NAME_LENGTH,
)
from ..project_launcher import resolve_project_path, is_tmux_session_exists, git_init, git_init_with_github, git_clone
from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention

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

        # Case 2: existing project for this chat
        project = self.pm.get_by_chat(chat_id)
        if project:
            if self._is_claude_running(project):
                return FlowResult(
                    action=FlowAction.SHOW_STATUS,
                    project=project.project_name,
                    path=project.cwd,
                    tmux_session=project.tmux_session,
                )
            return self._start_project_flow(chat_id, project.project_name)

        # Case 3: use chat title if valid
        if chat_title:
            sanitized = sanitize_project_name(chat_title)
            if sanitized:
                return self._start_project_flow(chat_id, sanitized)

        # Case 4: ask for project name
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
            self.pm._save()
            return self._connect_or_launch(project)
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
            )

    def _connect_or_launch(self, project) -> FlowResult:
        """Find tmux or offer to create."""
        tmux_list = find_all_tmux_by_cwd(project.cwd)

        if len(tmux_list) == 0:
            # Try convention naming
            tmux = find_tmux_by_convention(project.project_name)
            if tmux:
                project.tmux_session = tmux
                self.pm._save()
                return FlowResult(
                    action=FlowAction.CONNECT,
                    project=project.project_name,
                    tmux_session=tmux,
                )
            else:
                return FlowResult(
                    action=FlowAction.ASK_LAUNCH_CONFIRM,
                    project=project.project_name,
                    path=project.cwd,
                )
        elif len(tmux_list) == 1:
            project.tmux_session = tmux_list[0]
            self.pm._save()
            return FlowResult(
                action=FlowAction.CONNECT,
                project=project.project_name,
                tmux_session=tmux_list[0],
            )
        else:
            return FlowResult(
                action=FlowAction.SELECT_TMUX,
                project=project.project_name,
                path=project.cwd,
                tmux_list=tmux_list,
            )

    def _is_claude_running(self, project) -> bool:
        """Check if Claude is running for project."""
        if not project.tmux_session:
            return False
        if not is_tmux_session_exists(project.tmux_session):
            return False
        if not project.poller_task or project.poller_task.done():
            return False
        if not project.watcher_task or project.watcher_task.done():
            return False
        return True

    def handle_project_name(self, chat_id: int, name: str) -> FlowResult:
        """Handle user input for project name (FSM state handler)."""
        return self._validate_and_start(chat_id, name.strip())

    def handle_create_dir(self, project: str, path: str) -> FlowResult:
        """Handle 'Create directory' button."""
        expanded = Path(path).expanduser()
        expanded.mkdir(parents=True, exist_ok=True)

        return FlowResult(
            action=FlowAction.ASK_GIT_CHOICE,
            project=project,
            path=str(expanded),
        )

    def handle_custom_path(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle user input for custom path."""
        expanded = Path(path).expanduser().resolve()

        if not expanded.is_dir():
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Directory {path} does not exist",
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    def handle_git_init(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle 'git init' button."""
        result = git_init(path)

        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"git init failed: {result.error}",
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = path
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=path,
        )

    def handle_no_git(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle 'No git' button."""
        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = path
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=path,
        )

    def handle_gh_create(
        self, chat_id: int, project: str, path: str, private: bool
    ) -> FlowResult:
        """Handle GitHub repo creation."""
        result = git_init_with_github(path, private=private)

        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"GitHub creation failed: {result.error}",
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = path
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=path,
        )

    def handle_clone_url(
        self, chat_id: int, project: str, path: str, url: str
    ) -> FlowResult:
        """Handle user input for git clone URL."""
        # Validate URL format
        if not url.startswith(("https://", "git@", "ssh://")):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Invalid URL. Use https:// or git@ format",
            )

        result = git_clone(path, url)

        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Clone failed: {result.error}",
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = path
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=path,
        )

    def handle_tmux_selected(
        self, chat_id: int, project_name: str, tmux_session: str
    ) -> FlowResult:
        """Handle tmux session selection from list."""
        proj = self.pm.get_or_create(project_name)
        proj.chat_id = chat_id
        proj.tmux_session = tmux_session
        self.pm._save()

        return FlowResult(
            action=FlowAction.CONNECT,
            project=project_name,
            tmux_session=tmux_session,
        )
