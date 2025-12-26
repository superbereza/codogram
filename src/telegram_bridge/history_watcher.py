"""Periodic watcher for history.jsonl changes."""
import asyncio
from aiogram import Bot

from .session_manager import project_manager, ProjectState
from .history_reader import HISTORY_PATH
from .logging_config import logger
from .tmux import TmuxSession

REFRESH_INTERVAL = 15  # seconds


class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
        self.project_manager = project_manager
        self._last_mtime = 0
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the watcher task."""
        self._task = asyncio.create_task(self._watch_loop())
        return self._task

    async def stop(self):
        """Stop the watcher task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self):
        """Main watch loop."""
        while True:
            try:
                await self._check_for_changes()
            except Exception as e:
                logger.error("watch_loop_error", extra={"error": str(e)})

            await asyncio.sleep(REFRESH_INTERVAL)

    # NOTE: Runs every 15s. Tmux check runs always, session check only on mtime change.

    async def _check_for_changes(self):
        """Check tmux health (always) and session changes (on mtime change)."""
        from .session_manager import should_cleanup_project

        # Check mtime for session changes (optimized)
        history_changed = False
        if HISTORY_PATH.exists():
            mtime = HISTORY_PATH.stat().st_mtime
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                history_changed = True

        # Check each project
        for project in list(self.project_manager.projects.values()):
            if not project.chat_id or not project.cwd:
                continue

            # 1. Check if should cleanup (inactive > 30 days) — ALWAYS
            if should_cleanup_project(project):
                logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
                if project.watcher_task:
                    project.watcher_task.cancel()
                if project.poller_task:
                    project.poller_task.cancel()
                del self.project_manager.projects[project.project_name]
                continue

            # 2. Check if tmux died — ALWAYS (every 15s)
            if project.tmux_session:
                tmux = TmuxSession(project.tmux_session, project.cwd)
                if not tmux.exists():
                    logger.warning("tmux_died", extra={"project": project.project_name, "tmux": project.tmux_session})
                    # Notify user
                    try:
                        await self.bot.send_message(
                            project.chat_id,
                            f"⚠️ Claude session closed (tmux died): {project.project_name}"
                        )
                    except Exception:
                        pass
                    if project.watcher_task:
                        project.watcher_task.cancel()
                        project.watcher_task = None
                    if project.poller_task:
                        project.poller_task.cancel()
                        project.poller_task = None
                    project.tmux_session = None
                    project.session_id = None
                    continue

            # 3. Check if session changed — ONLY if history.jsonl changed
            if not history_changed:
                continue

            old_session = project.session_id
            changed = self.project_manager.refresh_project_session(project)

            if changed:
                logger.info("session_changed", extra={
                    "project": project.project_name,
                    "old_session": old_session[:8] if old_session else None,
                    "new_session": project.session_id[:8] if project.session_id else None,
                })

                # Start new before stop old (avoid message loss)
                old_watcher = project.watcher_task
                await self.project_manager._maybe_start_tasks(project, self.start_poller, self.start_watcher)
                if old_watcher:
                    old_watcher.cancel()


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
