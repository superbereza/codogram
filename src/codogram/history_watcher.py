"""Periodic watcher for history.jsonl changes."""
import asyncio
import time
from aiogram import Bot

from .session_manager import project_manager, ProjectState, ThreadInfo
from .history_reader import find_session_for_project
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
                # Cancel all thread tasks
                for thread in project.threads.values():
                    if thread.watcher_task:
                        thread.watcher_task.cancel()
                    if thread.poller_task:
                        thread.poller_task.cancel()
                # Cancel legacy tasks
                if project.watcher_task:
                    project.watcher_task.cancel()
                if project.poller_task:
                    project.poller_task.cancel()
                del self.project_manager.projects[project.project_name]
                continue

            # 2. Check thread health (tmux died detection for ALL threads)
            for thread in list(project.threads.values()):
                # Skip if awaiting or binding
                if thread.awaiting_new_session:
                    continue
                if thread.binding_task and not thread.binding_task.done():
                    continue

                tmux_name = thread.get_tmux_session(project.project_name)
                tmux = TmuxSession(tmux_name, project.cwd)

                # Check if tmux died
                if thread.session_id and not tmux.exists():
                    logger.warning(f"thread_tmux_died: project={project.project_name}, thread={thread.name}")

                    # Stop thread tasks
                    if thread.watcher_task:
                        thread.watcher_task.cancel()
                        thread.watcher_task = None
                    if thread.poller_task:
                        thread.poller_task.cancel()
                        thread.poller_task = None

                    # Notify user
                    try:
                        await self.bot.send_message(
                            project.chat_id,
                            f"⚠️ Claude session closed: {thread.name}",
                            message_thread_id=thread.thread_id
                        )
                    except Exception:
                        pass

                    # Reset thread state
                    thread.session_id = None
                    thread.jsonl_path = None

            # NOTE: Legacy project-level checks removed - all handled through threads now


BINDING_TIMEOUT = 300  # 5 minutes
BINDING_INTERVAL = 0.5  # seconds


async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo):
    """Watch jsonl for a specific thread and send messages to that thread."""
    from .watcher import JsonlWatcher, send_entry_to_telegram
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                await send_entry_to_telegram(
                    bot,
                    project.chat_id,
                    entry,
                    message_thread_id=thread.thread_id
                )
            except Exception as e:
                logger.error("watch_thread_error", extra={"error": str(e)})
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise


async def poll_for_session_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
) -> None:
    """Poll for a session that matches thread.last_sent_message.

    Scans ALL sessions for this cwd (not just the latest) because multiple
    threads may have different Claude sessions in the same project directory.
    """
    try:
        from .history_reader import find_session_by_user_message
    except Exception as e:
        logger.error(f"poll_for_session_thread: import error: {e}")
        return

    logger.debug(f"poll_for_session_thread called: cwd={project.cwd}, msg={thread.last_sent_message}")

    if not project.cwd or not thread.last_sent_message:
        logger.warning("poll_for_session_thread: missing cwd or last_sent_message")
        return

    logger.debug("poll_for_session_thread: passed validation, starting loop")
    start_time = time.time()

    try:
        logger.debug(f"poll_for_session_thread_start: project={project.project_name}, thread={thread.name}")
    except Exception as e:
        logger.error(f"poll_for_session_thread: logging error: {e}")

    logger.debug("poll_for_session_thread: entering while loop")
    while time.time() - start_time < BINDING_TIMEOUT:
        try:
            # Scan ALL sessions for this cwd to find one with matching user message
            result = find_session_by_user_message(project.cwd, thread.last_sent_message)
            logger.debug(f"poll_for_session_thread: search result={result is not None}")

            if result:
                session_id, jsonl_path = result

                logger.info(f"session_bound_thread: project={project.project_name}, thread={thread.name}, session={session_id[:8]}")

                thread.session_id = session_id
                thread.jsonl_path = str(jsonl_path)
                thread.awaiting_new_session = False

                # Start thread-specific watcher
                if not thread.watcher_task or thread.watcher_task.done():
                    thread.watcher_task = asyncio.create_task(
                        watch_thread_jsonl(bot, project, thread)
                    )

                # Start thread-specific permission poller
                from .permission_poller import create_poller_task_for_thread
                if not thread.poller_task or thread.poller_task.done():
                    thread.poller_task = await create_poller_task_for_thread(bot, project, thread)

                logger.info(f"thread_watcher_started: thread={thread.name}, session={session_id[:8]}")
                return

        except Exception as e:
            logger.warning(f"poll_for_session_thread_error: {e}")

        await asyncio.sleep(BINDING_INTERVAL)

    # Timeout
    logger.warning(f"poll_for_session_thread_timeout: project={project.project_name}, thread={thread.name}")
    thread.awaiting_new_session = False
    try:
        await bot.send_message(
            project.chat_id,
            "⚠️ Сессия не обнаружена. Проверьте что Claude запущен.",
            message_thread_id=thread.thread_id
        )
    except Exception:
        pass


async def check_session_for_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
) -> None:
    """Check if session changed for a thread."""
    if not project.cwd:
        return

    old_session = thread.session_id
    new_session_id = find_session_for_project(project.cwd)

    if new_session_id and new_session_id != old_session:
        # Session changed - user did /new or /compact
        logger.info(
            f"session_changed_thread: project={project.project_name}, thread={thread.name}, "
            f"old={old_session[:8] if old_session else None}, new={new_session_id[:8]}"
        )

        # Reset and wait for binding
        thread.session_id = None
        thread.jsonl_path = None
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
