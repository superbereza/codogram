"""Periodic watcher for history.jsonl changes."""
import asyncio
import time
from aiogram import Bot

from .session_manager import project_manager, ProjectState
from .history_reader import (
    HISTORY_PATH,
    find_session_for_project,
    compute_jsonl_path,
    get_last_user_message_from_jsonl,
)
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

    async def _check_for_changes(self):
        """Check tmux health and session changes for all projects."""
        from .session_manager import should_cleanup_project

        for project in list(self.project_manager.projects.values()):
            if not project.chat_id or not project.cwd:
                continue

            # 1. Check if should cleanup (inactive > 30 days)
            if should_cleanup_project(project):
                logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
                if project.watcher_task:
                    project.watcher_task.cancel()
                if project.poller_task:
                    project.poller_task.cancel()
                del self.project_manager.projects[project.project_name]
                continue

            # 2. Check if tmux died
            if project.tmux_session:
                tmux = TmuxSession(project.tmux_session, project.cwd)
                if not tmux.exists():
                    logger.warning("tmux_died", extra={"project": project.project_name, "tmux": project.tmux_session})
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

            # 3. Skip if awaiting new session (after /start, before first message)
            if project.awaiting_new_session:
                continue

            # 4. Skip if binding_task is running (poll_for_session is waiting for new session)
            if project.binding_task and not project.binding_task.done():
                continue

            # 4. Check for new/changed sessions (discover new Claude sessions)
            old_session = project.session_id
            changed = self.project_manager.refresh_project_session(project)

            if changed:
                logger.info("session_changed", extra={
                    "project": project.project_name,
                    "old_session": old_session[:8] if old_session else None,
                    "new_session": project.session_id[:8] if project.session_id else None,
                })

                # Cancel old watcher and start new one
                if project.watcher_task:
                    project.watcher_task.cancel()
                    project.watcher_task = None

                # Only send missed if this is a REAL session change
                send_missed = old_session is not None
                await self.project_manager._maybe_start_tasks(
                    project, self.start_poller, self.start_watcher, send_missed=send_missed
                )


async def check_session_for_project(project: ProjectState, bot: Bot, start_poller, start_watcher) -> None:
    """Check if session changed for a project and restart watcher if needed.

    Call this when user sends a message to ensure watcher tracks current session.
    """
    from .session_manager import project_manager

    if not project.chat_id or not project.cwd:
        return

    old_session = project.session_id
    changed = project_manager.refresh_project_session(project)

    if changed:
        logger.info("session_changed", extra={
            "project": project.project_name,
            "old_session": old_session[:8] if old_session else None,
            "new_session": project.session_id[:8] if project.session_id else None,
        })

        # Cancel old watcher FIRST
        if project.watcher_task:
            project.watcher_task.cancel()
            project.watcher_task = None

        # Only send missed if this is a REAL session change (old_session was not None)
        # If old_session is None, this is just initial discovery after bot restart
        send_missed = old_session is not None
        await project_manager._maybe_start_tasks(project, start_poller, start_watcher, send_missed=send_missed)


BINDING_TIMEOUT = 300  # 5 minutes
BINDING_INTERVAL = 0.5  # seconds


async def poll_for_session(
    project: ProjectState,
    bot: Bot,
    start_poller,
    start_watcher,
) -> None:
    """Poll for a session that matches project.last_sent_message.

    This is used after /start to wait for the NEW session (not grab old one).
    Matches session by comparing user message in jsonl with what we sent.
    """
    if not project.cwd or not project.last_sent_message:
        logger.warning("poll_for_session: missing cwd or last_sent_message")
        return

    old_session_id = project.session_id
    start_time = time.time()

    logger.info("poll_for_session_start", extra={
        "project": project.project_name,
        "old_session": old_session_id[:8] if old_session_id else None,
        "looking_for": project.last_sent_message[:30] if project.last_sent_message else None,
    })

    while time.time() - start_time < BINDING_TIMEOUT:
        try:
            # Get latest session for this cwd
            latest_session_id = find_session_for_project(project.cwd)

            if latest_session_id and latest_session_id != old_session_id:
                # New session appeared! Check if user message matches
                jsonl_path = compute_jsonl_path(project.cwd, latest_session_id)

                if jsonl_path.exists():
                    last_user_msg = get_last_user_message_from_jsonl(jsonl_path)

                    if last_user_msg == project.last_sent_message:
                        # Found it! Bind this session
                        logger.info("session_bound", extra={
                            "project": project.project_name,
                            "session_id": latest_session_id[:8],
                            "matched_msg": last_user_msg[:30] if last_user_msg else None,
                        })

                        project.session_id = latest_session_id
                        project.jsonl_path = str(jsonl_path)
                        project.awaiting_new_session = False

                        # Start watcher with send_missed=True
                        await project_manager._maybe_start_tasks(
                            project, start_poller, start_watcher, send_missed=True
                        )
                        return

        except Exception as e:
            logger.warning("poll_for_session_error", extra={"error": str(e)})

        await asyncio.sleep(BINDING_INTERVAL)

    # Timeout reached
    logger.warning("poll_for_session_timeout", extra={
        "project": project.project_name,
    })
    project.awaiting_new_session = False
    try:
        await bot.send_message(
            project.chat_id,
            "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."
        )
    except Exception:
        pass


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
