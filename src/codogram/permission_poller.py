"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

from .telegram_queue import OutgoingBatch
from .screen import parse_screen, PermissionPrompt, is_claude_ready
from .keyboards import permission_keyboard
from .state import permission_messages
from .session_manager import ProjectState, ThreadInfo
from .tmux import TmuxSession
from .logging_config import logger
from .auto_accept import try_auto_accept
from .config import settings
from . import strings


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
    """Create permission poller task for project (no thread)."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=None))


async def create_poller_task_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=thread))


async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: "TelegramQueue",
    thread: ThreadInfo | None = None,
) -> None:
    """
    Background poller for permission prompts.

    Polls tmux every interval, uses debounce before sending.
    State machine: IDLE -> DEBOUNCING -> SHOWING -> IDLE

    Args:
        bot: Telegram bot instance
        project: Project state
        telegram_queue: Queue for sending Telegram messages
        thread: Optional thread info for forum mode (None for simple mode)
    """
    # Determine context based on thread presence
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        thread_id = thread.thread_id
        log_prefix = f"Thread poller [{thread.name}]"
        context_name = thread.name
    else:
        tmux_name = project.tmux_session
        thread_id = None
        log_prefix = "Poller"
        context_name = project.project_name

    logger.info(f"{log_prefix}: started for {context_name} (tmux: {tmux_name})")

    # Create TmuxSession from context data
    tmux = TmuxSession(tmux_name, project.cwd)

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg_id: int | None = None

    debounce_time = settings.permission_poller_debounce
    poll_interval = settings.permission_poller_interval

    while True:
        await asyncio.sleep(poll_interval)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            logger.warning(f"{log_prefix}: capture error: {e}")
            continue

        # Crash detection
        crash_reason = _detect_crash(screen)
        if crash_reason:
            logger.error(f"{log_prefix}: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=project.chat_id,
                    thread_id=thread_id,
                    messages=[{"text": strings.CLAUDE_CRASHED.format(reason=crash_reason), "parse_mode": "MarkdownV2"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return  # Exit poller

        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug: log if prompt character detected but no permission parsed
        if "❯" in screen and not is_permission:
            logger.debug(f"{log_prefix}: prompt found but no permission! parsed={type(parsed).__name__}")

        # State machine transitions
        if state == PollerState.IDLE:
            if is_permission:
                logger.debug(f"{log_prefix} IDLE->DEBOUNCING: detected permission, options={parsed.options}")
                logger.debug(f"{log_prefix}: body={parsed.body[:100] if parsed.body else 'none'}...")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                logger.debug(f"{log_prefix} DEBOUNCING->IDLE: permission disappeared")
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= debounce_time:
                    # Check auto-accept (read dynamically - may have changed since poller started)
                    auto_accept_enabled = thread.auto_accept if thread else project.auto_accept
                    if auto_accept_enabled:
                        if await try_auto_accept(
                            parsed.options, parsed.body, tmux,
                            telegram_queue, project.chat_id, thread_id, context_name,
                            prompt_type=parsed.prompt_type,
                        ):
                            # Go to SHOWING to reuse existing dedup logic
                            # (wait for prompt to disappear before accepting new ones)
                            state = PollerState.SHOWING
                            last_body = parsed.body
                            continue

                    logger.debug(f"{log_prefix} DEBOUNCING->SHOWING: sending to Telegram")
                    logger.debug(f"{log_prefix}: body preview: {parsed.body[:200]}...")
                    try:
                        # Build batch of all messages (atomic send)
                        messages = []
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

                        # Options as text
                        options_text = "\n".join(parsed.options)
                        messages.append({"text": options_text})

                        # 👆 as last message (will get keyboard via reply_markup)
                        messages.append({"text": "👆"})

                        # Single atomic enqueue with keyboard on last message
                        kb = permission_keyboard(parsed.options, tmux_name)
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread_id,
                            messages=messages,
                            reply_markup=kb,
                        )
                        msg_ids = await telegram_queue.enqueue(batch)

                        # Last message is keyboard, rest are content
                        kb_msg_id = msg_ids[-1] if msg_ids else None
                        content_msg_ids = msg_ids[:-1] if len(msg_ids) > 1 else []
                        if kb_msg_id:
                            permission_messages[kb_msg_id] = content_msg_ids
                            logger.debug(f"{log_prefix}: saved permission_messages[{kb_msg_id}] = {content_msg_ids}")

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"{log_prefix} SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg_id}")
                    except Exception as e:
                        logger.warning(f"{log_prefix}: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug(f"{log_prefix} SHOWING->IDLE: permission gone, cleaning up")
                if kb_msg_id and kb_msg_id in permission_messages:
                    for msg_id in permission_messages[kb_msg_id]:
                        try:
                            await bot.delete_message(project.chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(project.chat_id, kb_msg_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg_id = None
            elif parsed.options != last_options or parsed.body != last_body:
                logger.debug(f"{log_prefix} SHOWING: body/options changed, resending")
                try:
                    # Delete old messages
                    if kb_msg_id and kb_msg_id in permission_messages:
                        for msg_id in permission_messages[kb_msg_id]:
                            try:
                                await bot.delete_message(project.chat_id, msg_id)
                            except Exception:
                                pass
                        try:
                            await bot.delete_message(project.chat_id, kb_msg_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg_id, None)

                    # Build new messages (atomic send)
                    messages = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

                    options_text = "\n".join(parsed.options)
                    messages.append({"text": options_text})

                    # 👆 as last message (will get keyboard via reply_markup)
                    messages.append({"text": "👆"})

                    # Single atomic enqueue with keyboard on last message
                    kb = permission_keyboard(parsed.options, tmux_name)
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread_id,
                        messages=messages,
                        reply_markup=kb,
                    )
                    msg_ids = await telegram_queue.enqueue(batch)

                    # Last message is keyboard, rest are content
                    kb_msg_id = msg_ids[-1] if msg_ids else None
                    content_msg_ids = msg_ids[:-1] if len(msg_ids) > 1 else []
                    if kb_msg_id:
                        permission_messages[kb_msg_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"{log_prefix} SHOWING: resend error: {e}")
