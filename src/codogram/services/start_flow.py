"""StartFlowService - business logic for /start flow."""
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .. import strings
from ..domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    validate_git_url,
    MAX_PROJECT_NAME_LENGTH,
)
from ..magic_names import get_random_magic_name
from ..project_launcher import resolve_project_path, is_tmux_session_exists, git_init, git_init_with_github, git_clone
from ..session_manager import ThreadInfo
from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession, kill_tmux_session

if TYPE_CHECKING:
    from ..session_manager import ProjectManager, ProjectState


def build_announcement(project_name: str, tmux_name: str, is_forum: bool) -> str:
    """Build project ready announcement message.

    Args:
        project_name: Name of the project
        tmux_name: Name of the tmux session
        is_forum: Whether chat is a forum (has topics)

    Returns:
        Formatted announcement message
    """
    commands = [
        "• /esc — cancel operation",
        "• /clear — clear context",
        "• /auto_accept — toggle auto-accept",
    ]
    if is_forum:
        commands.extend([
            "• /thread — new topic",
            "• /branch — new branch + topic",
            "• /finish — merge and archive",
        ])

    return f"""`[v]` Project `{project_name}` ready

Commands available in this chat:
{chr(10).join(commands)}

To see Claude's UI, run in terminal:
`tmux attach -t {tmux_name}`"""


def is_setup_phase(project: "ProjectState") -> bool:
    """Check if project is in setup phase (Claude never ran).

    Returns True if no session ever started in main thread.
    Handles legacy projects that have session_id on project instead of thread.
    """
    # Check new threads structure
    main_thread = project.threads.get(None)
    if main_thread and main_thread.session_id:
        return False

    # Fallback: legacy session_id field
    if project.session_id:
        return False

    return True


@dataclass
class CleanupResult:
    """Result of project cleanup operation."""
    success: bool
    error: str | None = None


def cleanup_project(project: "ProjectState", delete_directory: bool) -> CleanupResult:
    """Full project cleanup.

    Args:
        project: Project to cleanup
        delete_directory: Whether to delete the project directory

    Returns:
        CleanupResult with success=False if directory deletion failed
    """
    # 1. Kill all tmux sessions (main + topics)
    for thread in project.threads.values():
        tmux_name = thread.get_tmux_session(project.project_name)
        if is_tmux_session_exists(tmux_name):
            kill_tmux_session(tmux_name)

    # 2. Remove worktrees (if any)
    if project.cwd:
        for thread in project.threads.values():
            if thread.worktree_path:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", thread.worktree_path],
                        cwd=project.cwd,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Best effort

    # 3. Delete main directory (if requested)
    cleanup_failed = False
    if delete_directory and project.cwd:
        shutil.rmtree(project.cwd, ignore_errors=True)
        # Verify deletion succeeded
        if Path(project.cwd).exists():
            cleanup_failed = True

    # 4. Remove from config
    from ..session_manager import project_manager
    if project.project_name in project_manager.projects:
        del project_manager.projects[project.project_name]
        project_manager._save()

    if cleanup_failed:
        return CleanupResult(
            success=False,
            error=strings.RESET_CLEANUP_FAILED.format(path=project.cwd)
        )
    return CleanupResult(success=True)


class FlowAction(Enum):
    """All possible outcomes of a flow step."""

    # Questions - need user input
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CLONE_URL_RETRY = "ask_clone_url_retry"  # Shows error + re-prompt
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"

    # Actions - perform operation
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"
    SELECT_TMUX = "select_tmux"

    # Errors
    ERROR = "error"

    # Thread-specific
    THREAD_SHOW_STATUS = "thread_show_status"
    THREAD_LAUNCH = "thread_launch"
    UPGRADE_PENDING_THREAD = "upgrade_pending_thread"
    REGISTER_UNKNOWN_TOPIC = "register_unknown_topic"

    # Restart flow
    ASK_RESTART_CONFIRM = "ask_restart_confirm"
    RESTART_DONE = "restart_done"
    CANCELLED = "cancelled"


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
    # Thread-specific
    thread_id: int | None = None
    thread_name: str | None = None


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
            return self._handle_topic_start(chat_id, thread_id, args)

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
        self, chat_id: int, thread_id: int, args: list[str]
    ) -> FlowResult:
        """Handle /start in a topic."""
        # Case 1: No project for this chat
        project = self.pm.get_by_chat(chat_id)
        if not project:
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

    def handle_restart(
        self, chat_id: int, thread_id: int | None = None
    ) -> FlowResult:
        """Handle /restart command.

        Args:
            chat_id: Telegram chat ID
            thread_id: Topic thread ID (None for main chat)

        Returns:
            FlowResult with ASK_RESTART_CONFIRM or ERROR
        """
        project = self.pm.get_by_chat(chat_id)
        if not project:
            return FlowResult(
                action=FlowAction.ERROR,
                error="No active session to restart.",
            )

        # Determine tmux session
        if thread_id:
            thread = project.threads.get(thread_id)
            if not thread:
                return FlowResult(
                    action=FlowAction.ERROR,
                    error="No active session to restart.",
                )
            tmux_name = thread.get_tmux_session(project.project_name)
        else:
            # Main thread or legacy
            main_thread = project.threads.get(None)
            if main_thread:
                tmux_name = main_thread.get_tmux_session(project.project_name)
            elif project.tmux_session:
                tmux_name = project.tmux_session
            else:
                return FlowResult(
                    action=FlowAction.ERROR,
                    error="No active session to restart.",
                )

        # Check tmux exists
        if not is_tmux_session_exists(tmux_name):
            return FlowResult(
                action=FlowAction.ERROR,
                error="No active session to restart.",
            )

        return FlowResult(
            action=FlowAction.ASK_RESTART_CONFIRM,
            project=project.project_name,
            tmux_session=tmux_name,
            thread_id=thread_id,
        )

    def handle_restart_confirm(self, tmux_session: str) -> FlowResult:
        """Handle restart confirmation - kill tmux session.

        Args:
            tmux_session: Name of the tmux session to kill

        Returns:
            FlowResult with RESTART_DONE action
        """
        kill_tmux_session(tmux_session)
        return FlowResult(action=FlowAction.RESTART_DONE)

    def handle_cancel(self) -> FlowResult:
        """Handle cancel button.

        Returns:
            FlowResult with CANCELLED action
        """
        return FlowResult(action=FlowAction.CANCELLED)
