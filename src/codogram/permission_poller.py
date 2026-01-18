"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

from .telegram_queue import OutgoingBatch, EditBatch, DeleteBatch
from .screen import parse_screen, PermissionPrompt, is_claude_ready, parse_thinking_status, parse_input_suggestion, extract_input_text, PASTED_PATTERN
from .keyboards import permission_keyboard
from .state import permission_messages
from .session_manager import ProjectState, ThreadInfo
from .tmux import TmuxSession
from .logging_config import logger
from .auto_accept import try_auto_accept
from .config import settings
from . import strings
from .utils.truncate import truncate_body


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

# Track last suggestion per thread to avoid duplicates
_last_suggestions: dict[str, str | None] = {}


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

    # Thinking status state
    thinking_msg_key: str | None = None
    last_thinking_update: float = 0.0
    last_thinking_text: str | None = None

    # Suggestion state
    suggestion_msg_key: str | None = None

    # Compact notification state
    compacting_notified: bool = False

    # Stuck message detection state
    stuck_input_text: str | None = None
    stuck_seen_count: int = 0

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

        # Parse thinking status always (for compact detection)
        thinking_text = parse_thinking_status(screen)

        # Compact notification (one-time, regardless of thinking feature)
        if thinking_text and "compacting" in thinking_text.lower():
            if not compacting_notified:
                logger.info(f"{log_prefix}: compact detected, sending notification")
                batch = OutgoingBatch(
                    chat_id=project.chat_id,
                    thread_id=thread_id,
                    messages=[{"text": strings.COMPACTING_STARTED, "parse_mode": "MarkdownV2"}],
                )
                await telegram_queue.enqueue_nowait(batch)
                compacting_notified = True
        elif not thinking_text:
            # Reset when thinking ends
            compacting_notified = False

        # Display thinking status only if feature enabled
        feat_thinking_enabled = thread.feat_thinking_status if thread else project.feat_thinking_status
        if feat_thinking_enabled and thinking_text:
            now = asyncio.get_event_loop().time()
            # Throttle: update every 3 seconds
            if now - last_thinking_update >= 3.0:
                key = f"thinking:{project.chat_id}:{thread_id}"
                needs_resend = thread.thinking_needs_resend if thread else False

                if thinking_msg_key is None:
                    # First time — send new message
                    logger.debug(f"{log_prefix}: thinking status SEND: {thinking_text[:50]}...")
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread_id,
                        messages=[{"text": thinking_text}],
                        replace_key=key,
                    )
                    thinking_msg_key = key
                    await telegram_queue.enqueue_nowait(batch)

                elif needs_resend:
                    # Watcher sent message — delete + send to keep at bottom
                    logger.debug(f"{log_prefix}: thinking status RESEND: {thinking_text[:50]}...")
                    delete_batch = DeleteBatch(
                        chat_id=project.chat_id,
                        message_id=0,
                        replace_key=thinking_msg_key,
                    )
                    await telegram_queue.enqueue_nowait(delete_batch)

                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread_id,
                        messages=[{"text": thinking_text}],
                        replace_key=key,
                    )
                    await telegram_queue.enqueue_nowait(batch)
                    if thread:
                        thread.thinking_needs_resend = False

                else:
                    # No new messages — just edit in place
                    logger.debug(f"{log_prefix}: thinking status EDIT: {thinking_text[:50]}...")
                    batch = EditBatch(
                        chat_id=project.chat_id,
                        message_id=0,
                        text=thinking_text,
                        replace_key=key,
                    )
                    await telegram_queue.enqueue_nowait(batch)

                last_thinking_update = now
                last_thinking_text = thinking_text

        elif thinking_msg_key:
            # Claude finished thinking — delete status message
            logger.debug(f"{log_prefix}: thinking status DELETE")
            batch = DeleteBatch(
                chat_id=project.chat_id,
                message_id=0,
                replace_key=thinking_msg_key,
            )
            await telegram_queue.enqueue_nowait(batch)
            thinking_msg_key = None
            last_thinking_text = None
            last_thinking_update = 0.0  # Reset for next thinking cycle

        # Parse input suggestion (if feature enabled and not thinking)
        # Note: feat_suggestions is chat-wide, not per-thread
        feat_suggestions_enabled = project.feat_suggestions
        suggestion_key = f"{project.chat_id}:{thread_id}"

        if feat_suggestions_enabled and not thinking_text:
            suggestion = parse_input_suggestion(screen)

            if suggestion and suggestion != _last_suggestions.get(suggestion_key):
                # New suggestion — send 💡 with ReplyKeyboard
                logger.debug(f"{log_prefix}: suggestion NEW: {suggestion[:50]}...")
                suggestion_msg_key = f"suggestion:{project.chat_id}:{thread_id}"
                batch = OutgoingBatch(
                    chat_id=project.chat_id,
                    thread_id=thread_id,
                    messages=[{"text": "💡"}],
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text=suggestion)]],
                        resize_keyboard=True,
                        one_time_keyboard=True,
                    ),
                    replace_key=suggestion_msg_key,
                )
                await telegram_queue.enqueue_nowait(batch)
                _last_suggestions[suggestion_key] = suggestion

            elif not suggestion and _last_suggestions.get(suggestion_key):
                # Suggestion gone — delete 💡 message
                # Note: ReplyKeyboard persists until user interacts (one_time_keyboard=True helps)
                logger.debug(f"{log_prefix}: suggestion DELETE")
                if suggestion_msg_key:
                    batch = DeleteBatch(
                        chat_id=project.chat_id,
                        message_id=0,  # Lookup from sent_statuses
                        replace_key=suggestion_msg_key,
                    )
                    await telegram_queue.enqueue_nowait(batch)
                    suggestion_msg_key = None
                _last_suggestions[suggestion_key] = None

        elif suggestion_msg_key:
            # Feature disabled but message exists — cleanup
            logger.debug(f"{log_prefix}: suggestion DELETE (feature disabled)")
            batch = DeleteBatch(
                chat_id=project.chat_id,
                message_id=0,
                replace_key=suggestion_msg_key,
            )
            await telegram_queue.enqueue_nowait(batch)
            suggestion_msg_key = None
            _last_suggestions[suggestion_key] = None

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

        # Stuck message detection (before permission state machine)
        input_text = extract_input_text(screen)
        if input_text:
            last_msg = thread.last_sent_message if thread else None

            # Compare first line only (input_text is single line, last_msg may be multiline)
            is_potentially_stuck = (
                PASTED_PATTERN.match(input_text) is not None or
                (last_msg is not None and input_text == last_msg.split('\n')[0])
            )

            if is_potentially_stuck:
                if input_text == stuck_input_text:
                    stuck_seen_count += 1
                else:
                    stuck_input_text = input_text
                    stuck_seen_count = 1

                # Debounce: seen twice in a row = stuck, send Enter
                if stuck_seen_count >= 2:
                    logger.info(f"{log_prefix}: stuck message detected ({stuck_seen_count}x), sending Enter")
                    tmux.send_key("Enter")
                    # Clear state
                    stuck_input_text = None
                    stuck_seen_count = 0
                    # Clear last_sent_message to prevent re-triggering
                    if thread:
                        thread.last_sent_message = None
            else:
                # Not a stuck message, reset
                stuck_input_text = None
                stuck_seen_count = 0
        else:
            # No input text, reset
            stuck_input_text = None
            stuck_seen_count = 0

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
                    verbose_enabled = thread.verbose if thread else project.verbose
                    if auto_accept_enabled:
                        if await try_auto_accept(
                            parsed.options, parsed.body, tmux,
                            telegram_queue, project.chat_id, thread_id, context_name,
                            prompt_type=parsed.prompt_type,
                            verbose=verbose_enabled,
                        ):
                            # Go to SHOWING to reuse existing dedup logic
                            # (wait for prompt to disappear before accepting new ones)
                            state = PollerState.SHOWING
                            last_body = parsed.body
                            continue

                    logger.debug(f"{log_prefix} DEBOUNCING->SHOWING: sending to Telegram")
                    logger.debug(f"{log_prefix}: body preview: {parsed.body[:200]}...")
                    try:
                        # Get verbose setting from context
                        verbose_enabled = thread.verbose if thread else project.verbose
                        display_body = truncate_body(parsed.body, verbose=verbose_enabled)

                        # Build batch of all messages (atomic send)
                        messages = []
                        if display_body:
                            body_text = SEPARATOR_SOLID + "\n" + display_body
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
                # Check auto-accept first (race condition: prompt may change before tmux processes key)
                auto_accept_enabled = thread.auto_accept if thread else project.auto_accept
                verbose_enabled = thread.verbose if thread else project.verbose
                if auto_accept_enabled:
                    if await try_auto_accept(
                        parsed.options, parsed.body, tmux,
                        telegram_queue, project.chat_id, thread_id, context_name,
                        prompt_type=parsed.prompt_type,
                        verbose=verbose_enabled,
                    ):
                        logger.debug(f"{log_prefix} SHOWING: body/options changed, auto-accepted again")
                        last_options = parsed.options
                        last_body = parsed.body
                        continue

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

                    # Get verbose setting from context
                    verbose_enabled = thread.verbose if thread else project.verbose
                    display_body = truncate_body(parsed.body, verbose=verbose_enabled)

                    # Build new messages (atomic send)
                    messages = []
                    if display_body:
                        body_text = SEPARATOR_SOLID + "\n" + display_body
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
