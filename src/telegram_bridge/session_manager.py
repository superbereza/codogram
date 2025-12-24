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

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, SessionState] = {}
        self.projects: dict[str, int] = {}  # project_name -> chat_id
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

    def register_project(self, project_name: str, chat_id: int) -> None:
        """Register project -> chat mapping."""
        self.projects[project_name] = chat_id
        self._save()

    def get_chat_id(self, project_name: str) -> int | None:
        """Get chat_id for project."""
        return self.projects.get(project_name)

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
        project_name = get_project_name(Path(cwd))
        chat_id = self.get_chat_id(project_name)

        # Find jsonl path
        project_hash = cwd.replace("/", "-")
        projects_dir = Path.home() / ".claude" / "projects" / project_hash
        jsonl_path = None
        if projects_dir.exists():
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
            if session.watcher_task:
                session.watcher_task.cancel()
        self._save()

    async def restore_sessions(
        self,
        start_poller: Callable[[SessionState], Awaitable[asyncio.Task]],
        start_watcher: Callable[[SessionState], Awaitable[asyncio.Task]],
    ) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})
        for session_id, data in saved_sessions.items():
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
                # Verify tmux session still exists
                tmux = TmuxSession(session.tmux_session, session.cwd)
                if tmux.exists():
                    session.poller_task = await start_poller(session)
                    if session.jsonl_path:
                        session.watcher_task = await start_watcher(session)

manager = SessionManager()
