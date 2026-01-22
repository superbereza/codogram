"""StartFlowService - business logic for /start flow."""
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    MAX_PROJECT_NAME_LENGTH,
    validate_git_url,
)
from ...magic_names import get_random_magic_name
from ...tmux.launcher import (
    resolve_project_path,
    is_tmux_session_exists,
    git_init,
    git_init_with_github,
    git_clone,
)
from ...core.session_manager import ThreadInfo
from ...tmux.session import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession

from .models import FlowAction, FlowResult

if TYPE_CHECKING:
    from ...core.session_manager import ProjectManager


class StartFlowService:
    """Business logic for /start flow (non-topic mode)."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def handle_start(
        self,
        chat_id: int,
        args: list[str],
        chat_title: str | None = None,
        thread_id: int | None = None,
    ) -> FlowResult:
        """Entry point for /start command.

        Args:
            chat_id: Telegram chat ID
            args: Command arguments (e.g., ["project-name"])
            chat_title: Chat title for auto-naming
            thread_id: Topic thread ID (None for main chat)

        Returns:
            FlowResult with next action to take
        """
        # Topic mode
        if thread_id is not None:
            return self._handle_topic_start(chat_id, thread_id, args, chat_title)

        # Case 1: project name provided in args
        if args:
            project_name = args[0]
            return self._validate_and_start(chat_id, project_name)

        # Case 2: existing project for this chat
        project = self.pm.get_by_chat(chat_id)
        if project:
            # Check if there's a configured thread for this thread_id (including None)
            # This ensures general topic uses naming convention, not CWD discovery
            thread = project.threads.get(thread_id)
            if thread and thread.name != "pending":
                return self._check_thread_tmux(project, thread)

            # Fallback to project-level flow (for backwards compat / new projects)
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

    def _handle_topic_start(
        self, chat_id: int, thread_id: int, args: list[str], chat_title: str | None = None
    ) -> FlowResult:
        """Handle /start in a topic."""
        # Case 1: No project for this chat - try auto-detect from title
        project = self.pm.get_by_chat(chat_id)
        if not project:
            if chat_title:
                sanitized = sanitize_project_name(chat_title)
                if sanitized:
                    return self._start_project_flow(chat_id, sanitized, thread_id)
            return FlowResult(
                action=FlowAction.ASK_PROJECT_NAME,
                thread_id=thread_id,
            )

        # Case 2: Thread exists
        thread = project.threads.get(thread_id)
        if thread:
            if thread.name == "pending":
                return self._upgrade_pending_thread(project, thread)
            else:
                return self._check_thread_tmux(project, thread)

        # Case 3: Unknown topic - register it
        return self._register_unknown_topic(project, thread_id)

    def _check_thread_tmux(self, project, thread) -> FlowResult:
        """Check tmux for thread and return appropriate action."""
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)

        if tmux.exists():
            return FlowResult(
                action=FlowAction.THREAD_SHOW_STATUS,
                project=project.project_name,
                path=project.cwd,
                tmux_session=tmux_name,
                thread_id=thread.thread_id,
                thread_name=thread.name,
            )
        else:
            return FlowResult(
                action=FlowAction.THREAD_LAUNCH,
                project=project.project_name,
                path=project.cwd,
                thread_id=thread.thread_id,
                thread_name=thread.name,
            )

    def _upgrade_pending_thread(self, project, thread) -> FlowResult:
        """Upgrade a pending thread with a magic name."""
        # Get existing names to exclude
        existing_names = {
            t.name for t in project.threads.values()
            if t.name and t.name != "pending"
        }

        # Generate unique name
        new_name = get_random_magic_name(existing_names)
        thread.name = new_name
        self.pm._save()

        return FlowResult(
            action=FlowAction.UPGRADE_PENDING_THREAD,
            project=project.project_name,
            path=project.cwd,
            thread_id=thread.thread_id,
            thread_name=new_name,
        )

    def _register_unknown_topic(self, project, thread_id: int) -> FlowResult:
        """Register an unknown topic with a new ThreadInfo."""
        # Get existing names to exclude
        existing_names = {
            t.name for t in project.threads.values()
            if t.name and t.name != "pending"
        }

        # Generate unique name
        new_name = get_random_magic_name(existing_names)

        # Create and register thread
        thread = ThreadInfo(thread_id=thread_id, name=new_name)
        project.threads[thread_id] = thread
        self.pm._save()

        return FlowResult(
            action=FlowAction.REGISTER_UNKNOWN_TOPIC,
            project=project.project_name,
            path=project.cwd,
            thread_id=thread_id,
            thread_name=new_name,
        )

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

    def _start_project_flow(self, chat_id: int, project_name: str, thread_id: int | None = None) -> FlowResult:
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
            return self._connect_or_launch(project, thread_id)
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
                thread_id=thread_id,
            )

    def _connect_or_launch(self, project, thread_id: int | None = None) -> FlowResult:
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
                action=FlowAction.ASK_TMUX_SELECT,
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
        is_valid, error_msg = validate_git_url(url)
        if not is_valid:
            return FlowResult(
                action=FlowAction.ASK_CLONE_URL_RETRY,
                error=error_msg,
                project=project,
                path=path,
            )

        result = git_clone(path, url)

        if not result.success:
            return FlowResult(
                action=FlowAction.ASK_CLONE_URL_RETRY,
                error=f"Clone failed: {result.error}",
                project=project,
                path=path,
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
