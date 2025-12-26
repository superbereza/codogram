# src/telegram_bridge/session_manager.py
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings, load_config, save_config
from .project_resolver import get_project_name
from .tmux import TmuxSession
from .history_reader import find_session_for_project, compute_jsonl_path

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

    # DEPRECATED fields (for backwards compat during migration)
    # TODO: Remove after migration complete
    @property
    def claude_session_id(self) -> str | None:
        """Alias for session_id (backwards compat)."""
        return self.session_id

    @claude_session_id.setter
    def claude_session_id(self, value: str | None):
        """Alias for session_id (backwards compat)."""
        self.session_id = value

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

    async def restore_projects(self, bot, start_poller, start_watcher) -> None:
        """Restore sessions from history.jsonl after bot restart."""
        from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
        from .tmux_selector import create_tmux_selection_keyboard

        for project in list(self.projects.values()):  # Copy to allow removal
            if not project.chat_id or not project.cwd:
                continue

            # 1. Find session_id from history.jsonl
            self.refresh_project_session(project)

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
