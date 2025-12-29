"""Periodic watcher for history.jsonl changes."""
import asyncio
import time
from typing import TYPE_CHECKING

from aiogram import Bot

from .session_manager import project_manager, ProjectState, ThreadInfo

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue
from .history_reader import find_session_for_project
from .logging_config import logger
from .tmux import TmuxSession

REFRESH_INTERVAL = 15  # seconds


class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue"):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
        self.telegram_queue = telegram_queue
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

                    # Notify user through queue
                    from .telegram_queue import OutgoingBatch
                    try:
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread.thread_id,
                            messages=[{"text": f"⚠️ Claude session closed: {thread.name}"}],
                        )
                        await self.telegram_queue.enqueue_nowait(batch)
                    except Exception:
                        pass

                    # Reset thread state
                    thread.session_id = None
                    thread.jsonl_path = None

            # After thread health checks, bind awaiting threads
            await self._bind_awaiting_threads(project)

            # NOTE: Legacy project-level checks removed - all handled through threads now

    async def _bind_awaiting_threads(self, project: ProjectState):
        """Find new sessions and bind to awaiting threads.

        NOTE: Binds only ONE thread per cycle to prevent race condition where
        multiple awaiting threads bind to the same session.
        """
        from .history_reader import find_session_for_project

        # Get latest session once
        new_session = find_session_for_project(project.cwd)
        if not new_session:
            return

        # Find first awaiting thread that can bind to this session
        for thread in project.threads.values():
            if not thread.awaiting_new_session:
                continue
            if thread.session_id == new_session:
                continue  # Already has this session

            # Bind ONE thread and exit - next cycle will handle others
            await self._bind_thread_to_session(project, thread, new_session)
            return

    async def _bind_thread_to_session(
        self,
        project: ProjectState,
        thread: ThreadInfo,
        new_session_id: str
    ):
        """Bind thread to new session."""
        from .history_reader import compute_jsonl_path

        logger.info(
            f"session_bound: project={project.project_name}, thread={thread.name}, "
            f"old={thread.session_id[:8] if thread.session_id else None}, "
            f"new={new_session_id[:8]}"
        )

        # Cancel old watcher if exists
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None

        # Update binding
        thread.session_id = new_session_id
        thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))
        thread.awaiting_new_session = False

        # Start new watcher
        thread.watcher_task = asyncio.create_task(
            watch_thread_jsonl(self.bot, project, thread, self.telegram_queue)
        )

        # Restart permission poller
        if thread.poller_task:
            thread.poller_task.cancel()
        from .permission_poller import create_poller_task_for_thread
        thread.poller_task = await create_poller_task_for_thread(
            self.bot, project, thread, self.telegram_queue
        )

        # Notify user
        from .telegram_queue import OutgoingBatch
        try:
            batch = OutgoingBatch(
                chat_id=project.chat_id,
                thread_id=thread.thread_id,
                messages=[{"text": "✅ Новая сессия создана"}],
            )
            # Fire-and-forget notification
            await self.telegram_queue.enqueue_nowait(batch)
        except Exception:
            pass

        # Save config
        self.project_manager._save()


BINDING_TIMEOUT = 300  # 5 minutes
BINDING_INTERVAL = 0.5  # seconds


async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
    """Watch jsonl for a specific thread and send messages through queue."""
    from .watcher import JsonlWatcher, _entry_to_messages
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        logger.warning(f"watch_thread_jsonl: no jsonl_path for thread={thread.name}")
        return

    logger.info(f"thread_watcher_started: thread={thread.name}, session={thread.session_id[:8] if thread.session_id else 'None'}")
    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                messages = _entry_to_messages(entry)
                if messages:
                    text_preview = messages[0].get("text", "")[:40].replace("\n", " ")
                    # Use hash of preview as tracking ID
                    msg_id = hash(text_preview) & 0xFFFFFF
                    logger.info(f"message_read: msg_id={msg_id:06x} thread={thread.name} preview='{text_preview}'")

                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    telegram_ids = await telegram_queue.enqueue(batch)
                    logger.info(f"message_sent: msg_id={msg_id:06x} thread={thread.name} telegram_ids={telegram_ids}")
            except Exception as e:
                logger.error(f"watch_thread_error: {e}")
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise


async def poll_for_session_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
    telegram_queue: "TelegramQueue",
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
                        watch_thread_jsonl(bot, project, thread, telegram_queue)
                    )

                # Start thread-specific permission poller
                from .permission_poller import create_poller_task_for_thread
                if not thread.poller_task or thread.poller_task.done():
                    thread.poller_task = await create_poller_task_for_thread(bot, project, thread, telegram_queue)

                logger.info(f"thread_watcher_started: thread={thread.name}, session={session_id[:8]}")
                return

        except Exception as e:
            logger.warning(f"poll_for_session_thread_error: {e}")

        await asyncio.sleep(BINDING_INTERVAL)

    # Timeout
    logger.warning(f"poll_for_session_thread_timeout: project={project.project_name}, thread={thread.name}")
    thread.awaiting_new_session = False
    try:
        from .telegram_queue import OutgoingBatch
        batch = OutgoingBatch(
            chat_id=project.chat_id,
            thread_id=thread.thread_id,
            messages=[{"text": "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."}],
        )
        await telegram_queue.enqueue_nowait(batch)
    except Exception:
        pass


async def create_history_watcher(bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue") -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher, telegram_queue)
    await watcher.start()
    return watcher
