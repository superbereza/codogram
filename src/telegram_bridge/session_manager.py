# src/telegram_bridge/session_manager.py
import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings, load_config, save_config
from .project_resolver import get_project_name
from .tmux import TmuxSession
from .history_reader import find_session_for_project, compute_jsonl_path
from .logging_config import logger

def should_cleanup_project(project: 'ProjectState') -> bool:
    """Check if project should be cleaned up (inactive > 30 days).

    Uses jsonl file mtime, not last_activity tracking.
    """
    if not project.jsonl_path:
        return True  # No jsonl = cleanup

    jsonl_path = Path(project.jsonl_path)
    if not jsonl_path.exists():
        return True  # File deleted

    try:
        mtime = jsonl_path.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        return age_days > 30
    except Exception:
        return True  # Error = cleanup

@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Watcher (one active session_id)
    session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = field(default=None, repr=False)

    # Poller (one selected tmux)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)

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
        self._config["projects"] = {
            name: {"chat_id": p.chat_id, "cwd": p.cwd}
            for name, p in self.projects.items()
            if p.chat_id is not None
        }
        # Remove sessions - no longer needed
        self._config.pop("sessions", None)
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

    def get_by_tmux(self, tmux_session: str) -> ProjectState | None:
        """Find project by tmux_session."""
        for project in self.projects.values():
            if project.tmux_session == tmux_session:
                return project
        return None

    def refresh_project_session(self, project: ProjectState) -> bool:
        """Refresh session_id from history.jsonl.

        Returns True if session changed, False otherwise.
        """
        if not project.cwd:
            return False

        new_session_id = find_session_for_project(project.cwd)
        if not new_session_id:
            return False

        if new_session_id == project.session_id:
            return False  # No change

        # Session changed
        project.session_id = new_session_id

        # Compute jsonl path
        jsonl_path = compute_jsonl_path(project.cwd, new_session_id)
        if jsonl_path.exists():
            project.jsonl_path = str(jsonl_path)
        else:
            project.jsonl_path = None

        return True

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

    async def restore_projects(self, bot, start_poller, start_watcher) -> None:
        """Restore sessions from history.jsonl after bot restart."""
        from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
        from .tmux_selector import create_tmux_selection_keyboard

        for project in list(self.projects.values()):  # Copy to allow removal
            if not project.chat_id or not project.cwd:
                continue

            # 1. Find session_id from history.jsonl FIRST (sets jsonl_path)
            self.refresh_project_session(project)

            # 2. NOW check if project should be cleaned up
            if should_cleanup_project(project):
                logger.info(
                    "project_cleanup",
                    extra={
                        "project": project.project_name,
                        "reason": "inactive_30_days"
                    }
                )
                self.projects.pop(project.project_name, None)
                continue

            logger.info("project_restored", extra={"project": project.project_name})

            # 2. Find tmux by cwd or convention
            if not project.tmux_session:
                tmux_list = find_all_tmux_by_cwd(project.cwd)
                if len(tmux_list) == 1:
                    project.tmux_session = tmux_list[0]
                elif len(tmux_list) == 0:
                    # Fallback to convention
                    tmux_by_convention = find_tmux_by_convention(project.project_name)
                    if tmux_by_convention:
                        project.tmux_session = tmux_by_convention
                else:
                    # Multiple tmux - send selection keyboard to chat
                    keyboard = create_tmux_selection_keyboard(tmux_list, project.project_name)
                    try:
                        await bot.send_message(
                            project.chat_id,
                            f"🔄 Bot restarted. Multiple tmux sessions found for {project.project_name}:\n\n"
                            "Select which one to connect:",
                            reply_markup=keyboard
                        )
                    except Exception:
                        # If message fails, skip this project (user can reconnect manually)
                        pass
                    continue  # Don't start tasks, wait for selection

            # 3. Start tasks if ready
            await self._maybe_start_tasks(project, start_poller, start_watcher)

        self._save()

# Project manager
project_manager = ProjectManager()
