# src/codogram/core/session_manager.py
import asyncio
import fcntl
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..config import settings, load_config, get_config_path


class DisplayMode(str, Enum):
    """Display mode for tool call output."""
    SHOW_ALL = "show_all"       # Full output without truncation
    LINES = "lines"             # Truncate to N lines (default)
    HEADERS = "headers"         # Only tool headers, no body
    CURRENT = "current"         # Single message, edited with each tool call
    SILENCE = "silence"         # Hide tool calls, show only text responses
from ..git.resolver import get_project_name
from ..tmux.session import TmuxSession
from ..claude.session_finder import find_session_for_project, compute_jsonl_path
from ..logging_config import logger


def get_thread_setting(thread: 'ThreadInfo', key: str, global_defaults: dict[str, Any]) -> Any:
    """Get effective setting: thread override or global default.

    Args:
        thread: ThreadInfo instance
        key: Setting key (e.g. "auto_accept")
        global_defaults: Dict of global defaults

    Returns:
        Thread value if not None, otherwise global default
    """
    thread_value = getattr(thread, key, None)
    if thread_value is not None:
        return thread_value
    return global_defaults.get(key)


def get_project_setting(project: 'ProjectState', key: str, global_defaults: dict[str, Any]) -> Any:
    """Get effective setting: project override or global default.

    Args:
        project: ProjectState instance
        key: Setting key (e.g. "feat_avatar_pack")
        global_defaults: Dict of global defaults

    Returns:
        Project value if not None, otherwise global default
    """
    project_value = getattr(project, key, None)
    if project_value is not None:
        return project_value
    return global_defaults.get(key)


def should_cleanup_project(project: 'ProjectState') -> bool:
    """Check if project should be cleaned up (inactive > 30 days).

    Uses jsonl file mtime, not last_activity tracking.
    Does NOT cleanup if tmux session is still running (new project not yet registered).
    """
    import subprocess

    # Check any thread awaiting new session
    for thread in project.threads.values():
        if thread.awaiting_new_session:
            return False
        if thread.binding_task and not thread.binding_task.done():
            return False

    # Legacy checks (for transition period)
    if project.awaiting_new_session:
        return False
    if project.binding_task and not project.binding_task.done():
        return False

    # Check tmux for all threads (use '=' for exact match)
    for thread in project.threads.values():
        tmux_name = thread.get_tmux_session(project.project_name)
        result = subprocess.run(
            ["tmux", "has-session", "-t", f"={tmux_name}"],
            capture_output=True
        )
        if result.returncode == 0:
            return False  # Tmux exists, don't cleanup

    # Legacy tmux check (use '=' for exact match)
    if project.tmux_session:
        result = subprocess.run(
            ["tmux", "has-session", "-t", f"={project.tmux_session}"],
            capture_output=True
        )
        if result.returncode == 0:
            return False

    # Check jsonl mtime for any thread
    newest_mtime = 0
    for thread in project.threads.values():
        if thread.jsonl_path:
            jsonl_path = Path(thread.jsonl_path)
            if jsonl_path.exists():
                try:
                    mtime = jsonl_path.stat().st_mtime
                    newest_mtime = max(newest_mtime, mtime)
                except Exception:
                    pass

    # Legacy jsonl check
    if project.jsonl_path:
        jsonl_path = Path(project.jsonl_path)
        if jsonl_path.exists():
            try:
                mtime = jsonl_path.stat().st_mtime
                newest_mtime = max(newest_mtime, mtime)
            except Exception:
                pass

    if newest_mtime == 0:
        # No jsonl = never had a Claude session
        # Don't cleanup if project has chat_id (registered from Telegram)
        if project.chat_id is not None:
            return False  # Keep newly registered projects
        return True  # No jsonl and no chat_id = orphan, cleanup

    age_days = (time.time() - newest_mtime) / 86400
    return age_days > settings.project_cleanup_days


@dataclass
class ThreadInfo:
    """State for a single thread (topic) within a project."""
    thread_id: int | None  # None = General topic
    name: str              # mystic, arcane, user-provided, or "main"
    topic_name: str | None = None  # Telegram topic name for debugging

    # Runtime state (from history.jsonl):
    session_id: str | None = None
    jsonl_path: str | None = None

    # Tasks:
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    binding_task: asyncio.Task | None = field(default=None, repr=False)
    launch_task: asyncio.Task | None = field(default=None, repr=False)

    # For session binding:
    last_sent_message: str | None = None
    awaiting_new_session: bool = False
    # For session binding race condition fix:
    start_requested_at: float | None = None

    # Worktree support:
    worktree_path: str | None = None   # None = main repo directory
    base_branch: str | None = None     # Branch this worktree was created from
    archived: bool = False             # True = topic closed after /branch_finish

    # Settings - None means inherit from global defaults
    auto_accept: bool | None = None
    display_mode: str | None = None
    line_limit: int | None = None
    display_bullet: bool | None = None
    display_thinking_text: bool | None = None
    working_status: bool | None = None
    response_mode: str | None = None
    feat_suggestions: bool | None = None
    # Note: feat_avatar_pack is per-project (not per-thread) - see ProjectState

    # Persisted message IDs (for cleanup after restart):
    last_suggestion_msg_id: int | None = None  # Last 💡 message ID
    last_ask_msg_id: int | None = None  # Last AskUserQuestion keyboard message ID
    last_permission_msg_id: int | None = None  # Last permission prompt message ID

    # Runtime-only (not persisted):
    notified_closed: bool = False      # True = already sent "session closed" notification
    thinking_needs_resend: bool = False  # True = watcher sent message, thinking needs delete+send

    def get_tmux_session(self, project_name: str) -> str:
        """Get tmux session name for this thread."""
        if self.name == "main":
            return f"claude-{project_name}"
        return f"claude-{project_name}-{self.name}"

    def has_valid_session(self) -> bool:
        """Check if thread has a valid resumable session.

        Returns True only if:
        - session_id is set
        - jsonl_path is set
        - jsonl file exists on disk
        """
        if not self.session_id or not self.jsonl_path:
            return False
        return Path(self.jsonl_path).exists()

    def has_valid_worktree(self) -> bool:
        """Check if thread has a valid worktree directory.

        Returns True only if worktree_path is set and directory exists.
        """
        if not self.worktree_path:
            return False
        return Path(self.worktree_path).is_dir()


@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Migration support:
    old_chat_id: int | None = None        # Previous chat_id before group→supergroup migration
    awaiting_admin_rights: bool = False   # Block until bot gets admin rights

    # Multi-thread support: thread_id -> ThreadInfo
    threads: dict[int | None, ThreadInfo] = field(default_factory=dict)

    # Auto-accept permissions (project-wide default):
    auto_accept: bool = False

    # Display mode (project-wide default, replaces verbose):
    display_mode: str = "lines"        # show_all, lines, headers, current, silence
    line_limit: int = 5                # Used in 'lines' mode
    display_bullet: bool = True        # Show ● prefix
    display_thinking_text: bool = True # Show <thinking> blocks

    # Working status indicator (renamed from feat_thinking_status):
    working_status: bool = False

    # Experimental features (project-wide default):
    feat_suggestions: bool = True

    # Response mode: "all", "polite", "mentions"
    response_mode: str = "all"

    # Avatar emoji pack:
    feat_avatar_pack: bool | None = None  # None = inherit from global defaults
    emoji_pack_name: str | None = None
    emoji_map: dict[int, str] = field(default_factory=dict)  # {user_id: custom_emoji_id}

    # DEPRECATED: Legacy fields kept for backward compatibility with old configs.
    # All new code should use threads[None] for main thread.
    # These fields are used by: handlers/, permission_poller.py (permission_poller),
    # history_watcher.py, and session_manager.py itself.
    session_id: str | None = None  # DEPRECATED: use threads[None].session_id
    jsonl_path: str | None = None  # DEPRECATED: use threads[None].jsonl_path
    watcher_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED: use threads[None].watcher_task
    tmux_session: str | None = None  # DEPRECATED: use threads[None].get_tmux_session()
    poller_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED: use threads[None].poller_task
    last_sent_message: str | None = None  # DEPRECATED: use threads[None].last_sent_message
    binding_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED: use threads[None].binding_task
    awaiting_new_session: bool = False  # DEPRECATED: use threads[None].awaiting_new_session

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
                project.old_chat_id = data.get("old_chat_id")
                project.awaiting_admin_rights = data.get("awaiting_admin_rights", False)
                project.auto_accept = data.get("auto_accept", False)

                # Migration: verbose -> display_mode
                if "verbose" in data:
                    if data["verbose"]:
                        project.display_mode = "show_all"
                    else:
                        project.display_mode = "lines"
                        project.line_limit = 5
                else:
                    project.display_mode = data.get("display_mode", "lines")
                    project.line_limit = data.get("line_limit", 5)
                project.display_bullet = data.get("display_bullet", True)
                project.display_thinking_text = data.get("display_thinking_text", True)

                # Migration: feat_thinking_status -> working_status
                if "feat_thinking_status" in data:
                    project.working_status = data["feat_thinking_status"]
                else:
                    project.working_status = data.get("working_status", False)

                project.feat_suggestions = data.get("feat_suggestions", False)
                project.feat_avatar_pack = data.get("feat_avatar_pack", True)
                project.emoji_pack_name = data.get("emoji_pack_name")
                # Convert string keys back to int (JSON serialization converts int keys to strings)
                emoji_map_raw = data.get("emoji_map", {})
                project.emoji_map = {int(k): v for k, v in emoji_map_raw.items()}
                project.response_mode = data.get("response_mode", "all")

                # Load explicit threads first
                threads_data = data.get("threads", {})
                logger.debug(f"_load_projects: {project_name} has {len(threads_data)} threads")
                for tid_str, thread_data in threads_data.items():
                    tid = None if tid_str == "null" else int(tid_str)
                    thread_name = thread_data.get("name", "main")
                    logger.debug(f"_load_projects: loading thread tid={tid} name={thread_name}")
                    # Migration: verbose -> display_mode for thread
                    if "verbose" in thread_data:
                        thread_display_mode = "show_all" if thread_data["verbose"] else "lines"
                        thread_line_limit = 5
                    else:
                        # None = inherit from global (new behavior)
                        thread_display_mode = thread_data.get("display_mode")
                        thread_line_limit = thread_data.get("line_limit")

                    # Migration: feat_thinking_status -> working_status for thread
                    if "feat_thinking_status" in thread_data:
                        thread_working_status = thread_data["feat_thinking_status"]
                    else:
                        # None = inherit from global (new behavior)
                        thread_working_status = thread_data.get("working_status")

                    project.threads[tid] = ThreadInfo(
                        thread_id=tid,
                        name=thread_name,
                        topic_name=thread_data.get("topic_name"),
                        session_id=thread_data.get("session_id"),
                        jsonl_path=thread_data.get("jsonl_path"),
                        # NOTE: awaiting_new_session and start_requested_at are NOT loaded
                        # They always start as False/None - runtime-only state
                        worktree_path=thread_data.get("worktree_path"),
                        base_branch=thread_data.get("base_branch"),
                        archived=thread_data.get("archived", False),
                        # Settings - None = inherit from global
                        auto_accept=thread_data.get("auto_accept"),
                        display_mode=thread_display_mode,
                        line_limit=thread_line_limit,
                        display_bullet=thread_data.get("display_bullet"),
                        display_thinking_text=thread_data.get("display_thinking_text"),
                        working_status=thread_working_status,
                        response_mode=thread_data.get("response_mode"),
                        feat_suggestions=thread_data.get("feat_suggestions"),
                        last_suggestion_msg_id=thread_data.get("last_suggestion_msg_id"),
                        last_ask_msg_id=thread_data.get("last_ask_msg_id"),
                        last_permission_msg_id=thread_data.get("last_permission_msg_id"),
                        # Assume already notified if session exists but tmux likely dead
                        notified_closed=bool(thread_data.get("session_id")),
                    )

                # Migrate legacy → threads[None] if not already present
                if None not in project.threads and data.get("cwd"):
                    project.threads[None] = ThreadInfo(
                        thread_id=None,
                        name="main",
                        session_id=data.get("session_id"),
                        jsonl_path=data.get("jsonl_path"),
                        notified_closed=bool(data.get("session_id")),
                    )

            self.projects[project_name] = project

    def _save(self) -> None:
        """Persist to disk with file locking."""
        config_path = get_config_path()

        # Ensure file exists
        if not config_path.exists():
            config_path.write_text("{}")

        with open(config_path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Read current state
                f.seek(0)
                try:
                    current = json.load(f)
                except json.JSONDecodeError:
                    current = {}

                # Build projects data
                projects_data = {}
                for name, p in self.projects.items():
                    if p.chat_id is None:
                        continue
                    project_data = {
                        "chat_id": p.chat_id,
                        "cwd": p.cwd,
                        "old_chat_id": p.old_chat_id,
                        "awaiting_admin_rights": p.awaiting_admin_rights,
                        "auto_accept": p.auto_accept,
                        "display_mode": p.display_mode,
                        "line_limit": p.line_limit,
                        "display_bullet": p.display_bullet,
                        "display_thinking_text": p.display_thinking_text,
                        "working_status": p.working_status,
                        "feat_suggestions": p.feat_suggestions,
                        "feat_avatar_pack": p.feat_avatar_pack,
                        "emoji_pack_name": p.emoji_pack_name,
                        "emoji_map": p.emoji_map,
                    }
                    if p.response_mode != "all":
                        project_data["response_mode"] = p.response_mode

                    # Backward compat: duplicate threads[None] to legacy fields
                    if None in p.threads:
                        main_thread = p.threads[None]
                        project_data["session_id"] = main_thread.session_id
                        project_data["jsonl_path"] = main_thread.jsonl_path

                    # Save all threads with full state
                    if p.threads:
                        threads_dict = {}
                        for tid, t in p.threads.items():
                            thread_data = {
                                "name": t.name,
                                "topic_name": t.topic_name,
                                "session_id": t.session_id,
                                "jsonl_path": t.jsonl_path,
                                # NOTE: awaiting_new_session and start_requested_at are NOT persisted
                                # They are runtime-only state that should reset on bot restart
                            }
                            # Worktree fields - only save if set
                            if t.worktree_path:
                                thread_data["worktree_path"] = t.worktree_path
                            if t.base_branch:
                                thread_data["base_branch"] = t.base_branch
                            if t.archived:
                                thread_data["archived"] = t.archived
                            # Settings - only save if not None (explicit override)
                            if t.auto_accept is not None:
                                thread_data["auto_accept"] = t.auto_accept
                            if t.display_mode is not None:
                                thread_data["display_mode"] = t.display_mode
                            if t.line_limit is not None:
                                thread_data["line_limit"] = t.line_limit
                            if t.display_bullet is not None:
                                thread_data["display_bullet"] = t.display_bullet
                            if t.display_thinking_text is not None:
                                thread_data["display_thinking_text"] = t.display_thinking_text
                            if t.working_status is not None:
                                thread_data["working_status"] = t.working_status
                            if t.response_mode is not None:
                                thread_data["response_mode"] = t.response_mode
                            if t.feat_suggestions is not None:
                                thread_data["feat_suggestions"] = t.feat_suggestions
                            if t.last_suggestion_msg_id:
                                thread_data["last_suggestion_msg_id"] = t.last_suggestion_msg_id
                            if t.last_ask_msg_id:
                                thread_data["last_ask_msg_id"] = t.last_ask_msg_id
                            if t.last_permission_msg_id:
                                thread_data["last_permission_msg_id"] = t.last_permission_msg_id
                            threads_dict[str(tid) if tid is not None else "null"] = thread_data
                        project_data["threads"] = threads_dict
                    projects_data[name] = project_data

                # Update config
                current["projects"] = projects_data
                current.pop("sessions", None)

                # Write back
                f.seek(0)
                f.truncate()
                json.dump(current, f, indent=2)

                # Update internal state
                self._config = current
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def get_or_create(self, project_name: str) -> ProjectState:
        """Get existing project or create new one."""
        if project_name not in self.projects:
            self.projects[project_name] = ProjectState(project_name=project_name)
        return self.projects[project_name]

    def get_by_chat(self, chat_id: int) -> ProjectState | None:
        """Find project by chat_id or old_chat_id.

        Also checks old_chat_id to handle race conditions during migration.
        When a group migrates to supergroup, messages may arrive at new chat_id
        before migration handler updates the project.
        """
        # First try exact match on chat_id
        for project in self.projects.values():
            if project.chat_id == chat_id:
                return project

        # Fallback: check old_chat_id (migration in progress)
        for project in self.projects.values():
            if project.old_chat_id == chat_id:
                logger.debug(f"get_by_chat: found by old_chat_id={chat_id} project={project.project_name}")
                return project

        return None

    def get_by_tmux(self, tmux_session: str) -> ProjectState | None:
        """Find project by tmux_session (including thread sessions)."""
        for project in self.projects.values():
            # Check main project tmux
            if project.tmux_session == tmux_session:
                return project
            # Check thread tmux sessions
            for thread in project.threads.values():
                if thread.get_tmux_session(project.project_name) == tmux_session:
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

        self._save()
        return project

    async def restore_projects(self, bot, start_poller, start_watcher, telegram_queue) -> None:
        """Restore sessions from history.jsonl after bot restart."""
        from ..claude.history_watcher import watch_thread_jsonl

        # DEBUG: Log what we have at restore time
        for pname, p in self.projects.items():
            logger.info(f"restore_debug: project={pname} threads={len(p.threads)} names={[t.name for t in p.threads.values()]}")

        for project in list(self.projects.values()):
            if not project.chat_id or not project.cwd:
                continue

            # 1. Check if should cleanup
            if should_cleanup_project(project):
                logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
                self.projects.pop(project.project_name, None)
                continue

            logger.info("project_restored", extra={"project": project.project_name})

            # 2. Ensure threads[None] exists for main thread
            if None not in project.threads:
                project.threads[None] = ThreadInfo(thread_id=None, name="main")

            # 3. For each thread, try to restore tmux and session
            for thread in project.threads.values():
                tmux_name = thread.get_tmux_session(project.project_name)

                # Check if tmux exists (use '=' for exact match)
                import subprocess
                result = subprocess.run(
                    ["tmux", "has-session", "-t", f"={tmux_name}"],
                    capture_output=True
                )

                if result.returncode != 0:
                    # No tmux - will need /start to launch
                    continue

                # Tmux exists - refresh session if we have one
                if thread.session_id and thread.jsonl_path:
                    from pathlib import Path
                    if Path(thread.jsonl_path).exists():
                        # Start watcher for this thread
                        if not thread.watcher_task or thread.watcher_task.done():
                            logger.info(f"restore: starting watcher for thread={thread.name}")
                            thread.watcher_task = asyncio.create_task(
                                watch_thread_jsonl(bot, project, thread, telegram_queue)
                            )
                    else:
                        logger.warning(f"restore: jsonl not found for thread={thread.name}: {thread.jsonl_path}")
                else:
                    logger.debug(f"restore: no session for thread={thread.name} (session_id={thread.session_id}, jsonl={thread.jsonl_path})")

                # Start poller for this thread (regardless of watcher)
                from ..claude.poller import create_poller_task_for_thread
                if not thread.poller_task or thread.poller_task.done():
                    thread.poller_task = await create_poller_task_for_thread(bot, project, thread, telegram_queue)

        self._save()

# Project manager
project_manager = ProjectManager()
