"""Periodic watcher for history.jsonl changes."""
import asyncio
from aiogram import Bot

from .session_manager import project_manager, ProjectState
from .history_reader import HISTORY_PATH

REFRESH_INTERVAL = 15  # seconds


class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
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
                print(f"HistoryWatcher error: {e}")

            await asyncio.sleep(REFRESH_INTERVAL)

    async def _check_for_changes(self):
        """Check if history.jsonl changed and refresh sessions."""
        if not HISTORY_PATH.exists():
            return

        # Quick mtime check
        mtime = HISTORY_PATH.stat().st_mtime
        if mtime == self._last_mtime:
            return
        self._last_mtime = mtime

        # Check each project with chat_id
        for project in project_manager.projects.values():
            if not project.chat_id or not project.cwd:
                continue

            old_session = project.session_id
            changed = project_manager.refresh_project_session(project)

            if changed:
                print(f"HistoryWatcher: session changed for {project.project_name}: {old_session} -> {project.session_id}")

                # Cancel old watcher if exists
                old_watcher = project.watcher_task
                if old_watcher:
                    old_watcher.cancel()
                    try:
                        await old_watcher
                    except asyncio.CancelledError:
                        pass
                    project.watcher_task = None

                # Start new tasks
                await project_manager._maybe_start_tasks(
                    project, self.start_poller, self.start_watcher
                )


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
