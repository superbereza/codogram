"""Message routing to tmux sessions."""
from dataclasses import dataclass
from enum import Enum

from ..session_manager import project_manager, ProjectState, ThreadInfo
from ..tmux import TmuxSession
from ..logging_config import logger


class RouteAction(Enum):
    """Possible routing actions."""
    SEND_TO_TMUX = "send_to_tmux"
    CREATE_PENDING = "create_pending"
    SKIP_PENDING = "skip_pending"
    START_BINDING = "start_binding"
    NO_PROJECT = "no_project"
    NO_TMUX = "no_tmux"


@dataclass
class RouteResult:
    """Result of message routing decision."""
    action: RouteAction
    project: ProjectState | None = None
    thread: ThreadInfo | None = None
    tmux_name: str | None = None
    cwd: str | None = None


class MessageRouterService:
    """Route messages to appropriate tmux sessions."""

    def __init__(self, pm=None):
        self.pm = pm or project_manager

    def route(self, chat_id: int, thread_id: int | None, text: str) -> RouteResult:
        """Determine where to route a message.

        Args:
            chat_id: Telegram chat ID
            thread_id: Topic thread ID (None for main/private)
            text: Message text

        Returns:
            RouteResult with action and context
        """
        project = self.pm.get_by_chat(chat_id)
        if not project:
            return RouteResult(action=RouteAction.NO_PROJECT)

        # Get thread for this topic
        thread = project.threads.get(thread_id)

        # Unknown topic - need to create pending
        if thread_id is not None and not thread:
            return RouteResult(
                action=RouteAction.CREATE_PENDING,
                project=project,
            )

        # Auto-create main thread if missing
        if thread_id is None and not thread:
            thread = project.get_or_create_thread(None, "main")
            self.pm._save()

        # Skip pending threads
        if thread and thread.name == "pending":
            return RouteResult(action=RouteAction.SKIP_PENDING)

        # Check if session needs binding
        if thread and thread.session_id is None:
            tmux_name = thread.get_tmux_session(project.project_name)
            return RouteResult(
                action=RouteAction.START_BINDING,
                project=project,
                thread=thread,
                tmux_name=tmux_name,
                cwd=project.cwd,
            )

        # Ready to send to tmux
        tmux_name = thread.get_tmux_session(project.project_name)
        return RouteResult(
            action=RouteAction.SEND_TO_TMUX,
            project=project,
            thread=thread,
            tmux_name=tmux_name,
            cwd=project.cwd,
        )

    def send_to_tmux(self, result: RouteResult, text: str) -> bool:
        """Send text to tmux session.

        Returns True if sent successfully.
        """
        if not result.tmux_name or not result.cwd:
            return False

        tmux = TmuxSession(result.tmux_name, result.cwd)
        if not tmux.exists():
            logger.warning(f"no_tmux_session: {result.tmux_name}")
            return False

        tmux.send(text)
        logger.debug(f"sent_to_tmux: {text[:50]}")
        return True
