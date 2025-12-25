# src/telegram_bridge/session_manager.py
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

from .config import settings, load_config, save_config
from .project_resolver import get_project_name
from .tmux import TmuxSession

@dataclass
class SessionState:
    session_id: str
    tmux_session: str
    cwd: str
    project_name: str
    jsonl_path: str | None = None
    chat_id: int | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    watcher_task: asyncio.Task | None = field(default=None, repr=False)

@dataclass
class ProjectState:
    """Всё что знаем о проекте. Поля заполняются постепенно."""
    project_name: str

    # Telegram (появляется при /start)
    chat_id: int | None = None

    # Filesystem
    cwd: str | None = None

    # Tmux (появляется при /start или hook)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)

    # Claude (появляется при hook)
    claude_session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = field(default=None, repr=False)

class ProjectManager:
    """Manages ProjectState instances."""

    def __init__(self):
        self.projects: dict[str, ProjectState] = {}  # by project_name
        self._config = load_config()
        self._load_projects()

    def _load_projects(self) -> None:
        """Load projects from config."""
        saved_projects = self._config.get("projects", {})
        for project_name, data in saved_projects.items():
            project = ProjectState(project_name=project_name)
            if isinstance(data, int):
                # Old format: just chat_id
                project.chat_id = data
            else:
                # New format: dict with chat_id and cwd
                project.chat_id = data.get("chat_id")
                project.cwd = data.get("cwd")
            self.projects[project_name] = project

    def _save(self) -> None:
        """Persist to disk."""
        # Projects (permanent)
        self._config["projects"] = {
            name: {"chat_id": p.chat_id, "cwd": p.cwd}
            for name, p in self.projects.items()
            if p.chat_id is not None
        }
        # Sessions (temporary)
        self._config["sessions"] = {
            name: {
                "tmux_session": p.tmux_session,
                "claude_session_id": p.claude_session_id,
                "jsonl_path": p.jsonl_path,
            }
            for name, p in self.projects.items()
            if p.claude_session_id is not None
        }
        save_config(self._config)

    def get_or_create(self, project_name: str) -> ProjectState:
        """Get existing project or create new one."""
        if project_name not in self.projects:
            self.projects[project_name] = ProjectState(project_name=project_name)
        return self.projects[project_name]

    def get_by_chat(self, chat_id: int) -> ProjectState | None:
        """Find project by chat_id."""
        for project in self.projects.values():
            if project.chat_id == chat_id:
                return project
        return None

    def get_by_session(self, session_id: str) -> ProjectState | None:
        """Find project by claude_session_id."""
        for project in self.projects.values():
            if project.claude_session_id == session_id:
                return project
        return None

    def get_by_tmux(self, tmux_session: str) -> ProjectState | None:
        """Find project by tmux_session."""
        for project in self.projects.values():
            if project.tmux_session == tmux_session:
                return project
        return None

    async def update_from_telegram(
        self,
        project_name: str,
        chat_id: int,
        cwd: str | None,
        start_poller,
        start_watcher,
    ) -> ProjectState:
        """Update project from /start command."""
        project = self.get_or_create(project_name)
        project.chat_id = chat_id
        if cwd:
            project.cwd = cwd

        await self._maybe_start_tasks(project, start_poller, start_watcher)
        self._save()
        return project

    async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher) -> None:
        """Start tasks if all required data is present."""
        # Poller: needs tmux_session + chat_id
        if project.tmux_session and project.chat_id:
            if not project.poller_task or project.poller_task.done():
                project.poller_task = await start_poller(project)

        # Watcher: needs jsonl_path + chat_id
        if project.jsonl_path and project.chat_id:
            if not project.watcher_task or project.watcher_task.done():
                project.watcher_task = await start_watcher(project)

    async def update_from_hook(
        self,
        session_id: str,
        cwd: str,
        tmux_session: str,
        start_poller,
        start_watcher,
    ) -> ProjectState:
        """Update project from Claude hook."""
        project_name = get_project_name(Path(cwd))
        project = self.get_or_create(project_name)

        # Clear old session if different (prevents race with /new)
        if project.claude_session_id and project.claude_session_id != session_id:
            await self._stop_tasks(project)

        project.cwd = cwd
        project.tmux_session = tmux_session
        project.claude_session_id = session_id
        project.jsonl_path = self._find_jsonl(cwd, session_id)

        await self._maybe_start_tasks(project, start_poller, start_watcher)
        self._save()
        return project

    def _find_jsonl(self, cwd: str, session_id: str) -> str | None:
        """Find jsonl file for session."""
        project_hash = cwd.replace("/", "-")
        projects_dir = Path.home() / ".claude" / "projects" / project_hash

        if not projects_dir.exists():
            return None

        # Try exact match first
        exact = projects_dir / f"{session_id}.jsonl"
        if exact.exists():
            return str(exact)

        # Fallback to most recent
        jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if jsonl_files:
            return str(jsonl_files[-1])

        return None

    async def _stop_tasks(self, project: ProjectState) -> None:
        """Stop running tasks."""
        if project.poller_task:
            project.poller_task.cancel()
            try:
                await project.poller_task
            except asyncio.CancelledError:
                pass
            project.poller_task = None

        if project.watcher_task:
            project.watcher_task.cancel()
            try:
                await project.watcher_task
            except asyncio.CancelledError:
                pass
            project.watcher_task = None

    async def handle_session_end(self, session_id: str) -> None:
        """Handle Claude session end."""
        project = self.get_by_session(session_id)
        if not project:
            return

        # Race condition protection: ignore if session_id changed
        if project.claude_session_id != session_id:
            return

        # Clear Claude-related fields
        project.claude_session_id = None
        project.jsonl_path = None

        # Stop tasks
        await self._stop_tasks(project)

        # Keep: chat_id, cwd, tmux_session
        self._save()

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, SessionState] = {}
        self.projects: dict[str, int | dict] = {}  # project_name -> chat_id or {chat_id, path}
        self._config = load_config()
        self.projects = self._config.get("projects", {})

    def _save(self) -> None:
        """Persist config to disk."""
        self._config["projects"] = self.projects
        self._config["sessions"] = {
            sid: {
                "tmux_session": s.tmux_session,
                "cwd": s.cwd,
                "project_name": s.project_name,
                "jsonl_path": s.jsonl_path,
            }
            for sid, s in self.sessions.items()
        }
        save_config(self._config)

    def register_project(self, project_name: str, chat_id: int, path: str | None = None) -> None:
        """Register project -> chat mapping with optional custom path."""
        self.projects[project_name] = {
            "chat_id": chat_id,
            "path": path,  # None means use convention ~/dev/{project_name}
        }
        self._save()

    def get_chat_id(self, project_name: str) -> int | None:
        """Get chat_id for project."""
        project = self.projects.get(project_name)
        if project is None:
            return None
        # Handle both old format (int) and new format (dict)
        if isinstance(project, int):
            return project
        return project.get("chat_id")

    def get_project_path(self, project_name: str) -> str | None:
        """Get custom path for project, or None for convention."""
        project = self.projects.get(project_name)
        if project is None or isinstance(project, int):
            return None
        return project.get("path")

    def get_project_by_chat(self, chat_id: int) -> str | None:
        """Find project_name by chat_id."""
        for project_name, data in self.projects.items():
            if isinstance(data, int):
                if data == chat_id:
                    return project_name
            elif data.get("chat_id") == chat_id:
                return project_name
        return None

    def get_session_by_chat(self, chat_id: int) -> SessionState | None:
        """Find active session for chat_id."""
        for session in self.sessions.values():
            if session.chat_id == chat_id:
                return session
        return None

    async def register_session(
        self,
        session_id: str,
        cwd: str,
        tmux_session: str,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> SessionState | None:
        """Register new Claude session."""
        # If session already exists, just return it (avoid duplicates)
        if session_id in self.sessions:
            return self.sessions[session_id]

        project_name = get_project_name(Path(cwd))
        chat_id = self.get_chat_id(project_name)

        # Remove old sessions for same project (prevents duplicates)
        old_sessions = [sid for sid, s in self.sessions.items() if s.project_name == project_name]
        for old_sid in old_sessions:
            await self.unregister_session(old_sid)

        # Find jsonl path by session_id first, fallback to most recent
        project_hash = cwd.replace("/", "-")
        projects_dir = Path.home() / ".claude" / "projects" / project_hash
        jsonl_path = None
        if projects_dir.exists():
            # Try exact match first
            exact_match = projects_dir / f"{session_id}.jsonl"
            if exact_match.exists():
                jsonl_path = str(exact_match)
            else:
                # Fallback to most recent
                jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
                if jsonl_files:
                    jsonl_path = str(jsonl_files[-1])

        session = SessionState(
            session_id=session_id,
            tmux_session=tmux_session,
            cwd=cwd,
            project_name=project_name,
            jsonl_path=jsonl_path,
            chat_id=chat_id,
        )

        self.sessions[session_id] = session

        # Start tasks only if we have chat_id
        if chat_id:
            session.poller_task = await start_poller(session)
            if jsonl_path:
                session.watcher_task = await start_watcher(session)

        self._save()
        return session

    async def unregister_session(self, session_id: str) -> None:
        """Unregister Claude session."""
        session = self.sessions.pop(session_id, None)
        if session:
            if session.poller_task:
                session.poller_task.cancel()
                try:
                    await session.poller_task
                except asyncio.CancelledError:
                    pass
            if session.watcher_task:
                session.watcher_task.cancel()
                try:
                    await session.watcher_task
                except asyncio.CancelledError:
                    pass
        self._save()

    async def restore_sessions(
        self,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})

        # Deduplicate by tmux_session - keep only one session per tmux
        tmux_to_session: dict[str, tuple[str, dict]] = {}
        for session_id, data in saved_sessions.items():
            tmux_name = data["tmux_session"]
            tmux_to_session[tmux_name] = (session_id, data)

        # Only restore deduplicated sessions with live tmux
        for session_id, data in tmux_to_session.values():
            tmux = TmuxSession(data["tmux_session"], data["cwd"])
            if not tmux.exists():
                continue  # Skip dead tmux sessions

            chat_id = self.get_chat_id(data["project_name"])
            session = SessionState(
                session_id=session_id,
                tmux_session=data["tmux_session"],
                cwd=data["cwd"],
                project_name=data["project_name"],
                jsonl_path=data.get("jsonl_path"),
                chat_id=chat_id,
            )
            self.sessions[session_id] = session

            if chat_id:
                session.poller_task = await start_poller(session)
                if session.jsonl_path:
                    session.watcher_task = await start_watcher(session)

        # Save cleaned config
        self._save()

manager = SessionManager()
