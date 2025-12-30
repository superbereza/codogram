"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

from .telegram_queue import OutgoingBatch, KeyboardBatch
from .screen import parse_screen, PermissionPrompt, is_claude_ready
from .keyboards import permission_keyboard
from .chunker import chunk_message
from .state import permission_messages
from .session_manager import ProjectState, ThreadInfo
from .tmux import TmuxSession
from .logging_config import logger


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


# Separator for Telegram display
SEPARATOR_SOLID = "────────────"

# Crash detection signatures
CRASH_SIGNATURES = [
    "panicked at",
    "fatal runtime error",
    "core dumped",
    "SIGSEGV",
    "SIGABRT",
]

# Shell prompts indicating Claude exited
SHELL_PROMPTS = ["➜", "$ ", "# ", "❯ "]


def _detect_crash(screen: str) -> str | None:
    """Detect if Claude has crashed. Returns crash reason or None.

    Only triggers if ALL conditions met:
    1. Claude UI NOT visible (is_claude_ready = False)
    2. Shell prompt visible (Claude exited to shell)
    3. Crash signature in LAST 15 lines (not scrollback)
    """
    # If Claude UI is visible, definitely not crashed
    if is_claude_ready(screen):
        return None

    lines = screen.split("\n")
    last_lines = "\n".join(lines[-15:])  # Only check last 15 lines

    # Must have shell prompt (Claude exited)
    has_shell = any(p in last_lines for p in SHELL_PROMPTS)
    if not has_shell:
        return None

    # Check for crash signatures in last lines only
    for sig in CRASH_SIGNATURES:
        if sig in last_lines:
            return sig
    return None


async def create_poller_task(bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for project."""
    return asyncio.create_task(permission_poller_for_project(bot, project, telegram_queue))


async def permission_poller_for_project(bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue"):
    """
    Background poller for permission prompts.

    Polls tmux every 0.5s, uses debounce before sending.
    State machine: IDLE → DEBOUNCING → SHOWING → IDLE
    """
    logger.info(f"Permission poller started for project {project.project_name}")

    # Create TmuxSession from project data
    tmux = TmuxSession(project.tmux_session, project.cwd)
    chat_id = project.chat_id

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg_id: int | None = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            logger.warning(f"Permission poller: capture error: {e}")
            continue

        # Crash detection
        crash_reason = _detect_crash(screen)
        if crash_reason:
            logger.error(f"Permission poller: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=chat_id,
                    thread_id=None,
                    messages=[{"text": f"`[!]` Claude crashed: {crash_reason}\nUse /restart to restart.", "parse_mode": "Markdown"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return  # Exit poller

        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug: log if ❯ detected but no permission parsed
        if "❯" in screen and not is_permission:
            logger.debug(f"Poller: ❯ found but no permission! parsed={type(parsed).__name__}")

        # State machine transitions
        if state == PollerState.IDLE:
            if is_permission:
                logger.debug(f"Poller IDLE→DEBOUNCING: detected permission, options={parsed.options}")
                logger.debug(f"Poller: body={parsed.body[:100] if parsed.body else 'none'}...")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                logger.debug("Poller DEBOUNCING→IDLE: permission disappeared")
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    logger.debug(f"Poller DEBOUNCING→SHOWING: sending to Telegram")
                    logger.debug(f"Poller: body preview: {parsed.body[:200]}...")
                    try:
                        # Build batch of body messages
                        body_messages = []
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                        # Options as text
                        options_text = "\n".join(parsed.options)
                        body_messages.append({"text": options_text})

                        # Send body through queue, get IDs for cleanup
                        batch = OutgoingBatch(
                            chat_id=chat_id,
                            thread_id=None,
                            messages=body_messages,
                        )
                        content_msg_ids = await telegram_queue.enqueue(batch)

                        # Keyboard through queue (rate limited)
                        kb = permission_keyboard(parsed.options, project.tmux_session)
                        kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                            chat_id=chat_id,
                            text="👆",
                            reply_markup=kb,
                            thread_id=None,
                        ))
                        kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                        if kb_msg_id:
                            permission_messages[kb_msg_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"Poller SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg_id}")
                    except Exception as e:
                        logger.warning(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug("Poller SHOWING→IDLE: permission gone, cleaning up")
                if kb_msg_id and kb_msg_id in permission_messages:
                    for msg_id in permission_messages[kb_msg_id]:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(chat_id, kb_msg_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg_id = None
            elif parsed.options != last_options or parsed.body != last_body:
                logger.debug(f"Poller SHOWING: body/options changed, resending")
                try:
                    # Delete old messages
                    if kb_msg_id and kb_msg_id in permission_messages:
                        for msg_id in permission_messages[kb_msg_id]:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        try:
                            await bot.delete_message(chat_id, kb_msg_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg_id, None)

                    # Build new body messages
                    body_messages = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        for chunk in chunk_message(body_text):
                            body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                    options_text = "\n".join(parsed.options)
                    body_messages.append({"text": options_text})

                    # Send through queue
                    batch = OutgoingBatch(chat_id=chat_id, thread_id=None, messages=body_messages)
                    content_msg_ids = await telegram_queue.enqueue(batch)

                    # Keyboard through queue (rate limited)
                    kb = permission_keyboard(parsed.options, project.tmux_session)
                    kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                        chat_id=chat_id,
                        text="👆",
                        reply_markup=kb,
                        thread_id=None,
                    ))
                    kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                    if kb_msg_id:
                        permission_messages[kb_msg_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"Poller SHOWING: resend error: {e}")


async def create_poller_task_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller_for_thread(bot, project, thread, telegram_queue))


async def permission_poller_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
    """
    Background poller for permission prompts in a specific thread/topic.

    Same as permission_poller_for_project but sends to message_thread_id.
    """
    tmux_name = thread.get_tmux_session(project.project_name)
    logger.info(f"Permission poller started for thread {thread.name} (tmux: {tmux_name})")

    tmux = TmuxSession(tmux_name, project.cwd)
    chat_id = project.chat_id
    thread_id = thread.thread_id  # For sending to correct topic

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg_id: int | None = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            logger.warning(f"Thread poller {thread.name}: capture error: {e}")
            continue

        # Crash detection
        crash_reason = _detect_crash(screen)
        if crash_reason:
            logger.error(f"Thread poller {thread.name}: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=chat_id,
                    thread_id=thread_id,
                    messages=[{"text": f"`[!]` Claude crashed: {crash_reason}\nUse /restart to restart.", "parse_mode": "Markdown"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return  # Exit poller

        is_permission = isinstance(parsed, PermissionPrompt)

        if state == PollerState.IDLE:
            if is_permission:
                logger.debug(f"Thread poller {thread.name} IDLE→DEBOUNCING")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    logger.debug(f"Thread poller {thread.name} DEBOUNCING→SHOWING")
                    try:
                        # Build batch of body messages
                        body_messages = []
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                        # Options as text
                        options_text = "\n".join(parsed.options)
                        body_messages.append({"text": options_text})

                        # Send body through queue, get IDs for cleanup
                        batch = OutgoingBatch(
                            chat_id=chat_id,
                            thread_id=thread_id,
                            messages=body_messages,
                        )
                        content_msg_ids = await telegram_queue.enqueue(batch)

                        # Keyboard through queue (rate limited)
                        kb = permission_keyboard(parsed.options, tmux_name)
                        kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                            chat_id=chat_id,
                            text="👆",
                            reply_markup=kb,
                            thread_id=thread_id,
                        ))
                        kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                        if kb_msg_id:
                            permission_messages[kb_msg_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"Thread poller {thread.name} SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg_id}")
                    except Exception as e:
                        logger.warning(f"Thread poller {thread.name}: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug(f"Thread poller {thread.name} SHOWING→IDLE: cleanup")
                if kb_msg_id and kb_msg_id in permission_messages:
                    for msg_id in permission_messages[kb_msg_id]:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(chat_id, kb_msg_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg_id = None
            elif parsed.options != last_options or parsed.body != last_body:
                logger.debug(f"Thread poller {thread.name} SHOWING: resending")
                try:
                    # Delete old messages
                    if kb_msg_id and kb_msg_id in permission_messages:
                        for msg_id in permission_messages[kb_msg_id]:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        try:
                            await bot.delete_message(chat_id, kb_msg_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg_id, None)

                    # Build new body messages
                    body_messages = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        for chunk in chunk_message(body_text):
                            body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                    options_text = "\n".join(parsed.options)
                    body_messages.append({"text": options_text})

                    # Send through queue
                    batch = OutgoingBatch(chat_id=chat_id, thread_id=thread_id, messages=body_messages)
                    content_msg_ids = await telegram_queue.enqueue(batch)

                    # Keyboard through queue (rate limited)
                    kb = permission_keyboard(parsed.options, tmux_name)
                    kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                        chat_id=chat_id,
                        text="👆",
                        reply_markup=kb,
                        thread_id=thread_id,
                    ))
                    kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                    if kb_msg_id:
                        permission_messages[kb_msg_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"Thread poller {thread.name}: resend error: {e}")
