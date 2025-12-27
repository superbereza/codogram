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
    Does NOT cleanup if tmux session is still running (new project not yet registered).
    """
    import subprocess

    # If tmux session is running, don't cleanup (even if no jsonl yet)
    if project.tmux_session:
        result = subprocess.run(
            ["tmux", "has-session", "-t", project.tmux_session],
            capture_output=True
        )
        if result.returncode == 0:
            return False  # Tmux exists, don't cleanup

    if not project.jsonl_path:
        return True  # No jsonl and no tmux = cleanup

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
class ThreadInfo:
    """State for a single thread (topic) within a project."""
    thread_id: int | None  # None = General topic
    name: str              # mystic, arcane, user-provided, or "main"

    # Runtime state (from history.jsonl):
    session_id: str | None = None
    jsonl_path: str | None = None

    # Tasks:
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    binding_task: asyncio.Task | None = field(default=None, repr=False)

    # For session binding:
    last_sent_message: str | None = None
    awaiting_new_session: bool = False

    def get_tmux_session(self, project_name: str) -> str:
        """Get tmux session name for this thread."""
        if self.name == "main":
            return f"claude-{project_name}"
        return f"claude-{project_name}-{self.name}"


@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Multi-thread support: thread_id -> ThreadInfo
    threads: dict[int | None, ThreadInfo] = field(default_factory=dict)

    # Legacy fields (for migration, will be moved to ThreadInfo)
    session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    last_sent_message: str | None = None
    binding_task: asyncio.Task | None = field(default=None, repr=False)
    awaiting_new_session: bool = False

    def get_thread(self, thread_id: int | None) -> ThreadInfo | None:
        """Get thread by thread_id."""
        return self.threads.get(thread_id)

    def get_or_create_thread(self, thread_id: int | None, name: str) -> ThreadInfo:
        """Get existing thread or create new one."""
        if thread_id not in self.threads:
            self.threads[thread_id] = ThreadInfo(thread_id=thread_id, name=name)
        return self.threads[thread_id]

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
                # Load threads
                threads_data = data.get("threads", {})
                for tid_str, thread_data in threads_data.items():
                    tid = None if tid_str == "null" else int(tid_str)
                    project.threads[tid] = ThreadInfo(
                        thread_id=tid,
                        name=thread_data.get("name", "main")
                    )
            self.projects[project_name] = project

    def _save(self) -> None:
        """Persist to disk."""
        projects_data = {}
        for name, p in self.projects.items():
            if p.chat_id is None:
                continue
            project_data = {"chat_id": p.chat_id, "cwd": p.cwd}
            if p.threads:
                project_data["threads"] = {
                    str(tid) if tid is not None else "null": {"name": t.name}
                    for tid, t in p.threads.items()
                }
            projects_data[name] = project_data
        self._config["projects"] = projects_data
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

    async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher,
                                 send_missed: bool = False) -> None:
        """Start tasks if all required data is present."""
        # Poller: needs tmux_session + chat_id
        if project.tmux_session and project.chat_id:
            if not project.poller_task or project.poller_task.done():
                project.poller_task = await start_poller(project)

        # Watcher: needs jsonl_path + chat_id
        if project.jsonl_path and project.chat_id:
            if not project.watcher_task or project.watcher_task.done():
                project.watcher_task = await start_watcher(project, send_missed)

    async def restore_projects(self, bot, start_poller, start_watcher) -> None:
        """Restore sessions from history.jsonl after bot restart."""
        from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
        from .tmux_selector import create_tmux_selection_keyboard

        for project in list(self.projects.values()):  # Copy to allow removal
            if not project.chat_id or not project.cwd:
                continue

            # 1. Find tmux by cwd or convention FIRST (needed for cleanup check)
            if not project.tmux_session:
                tmux_list = find_all_tmux_by_cwd(project.cwd)
                if len(tmux_list) == 1:
                    project.tmux_session = tmux_list[0]
                elif len(tmux_list) == 0:
                    # Fallback to convention
                    tmux_by_convention = find_tmux_by_convention(project.project_name)
                    if tmux_by_convention:
                        project.tmux_session = tmux_by_convention
                # Multiple tmux handled after cleanup check

            # 2. Find session_id from history.jsonl (sets jsonl_path)
            self.refresh_project_session(project)

            # 3. Check if project should be cleaned up
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

            # 4. Handle multiple tmux sessions (ask user to select)
            if not project.tmux_session:
                tmux_list = find_all_tmux_by_cwd(project.cwd)
                if len(tmux_list) > 1:
                    keyboard = create_tmux_selection_keyboard(tmux_list, project.project_name)
                    try:
                        await bot.send_message(
                            project.chat_id,
                            f"🔄 Bot restarted. Multiple tmux sessions found for {project.project_name}:\n\n"
                            "Select which one to connect:",
                            reply_markup=keyboard
                        )
                    except Exception:
                        pass
                    continue  # Don't start tasks, wait for selection

            # 5. Start tasks if ready
            await self._maybe_start_tasks(project, start_poller, start_watcher)

        self._save()

# Project manager
project_manager = ProjectManager()
