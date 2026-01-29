"""Auto-accept mode for permission prompts."""
import re
from typing import TYPE_CHECKING

from .claude.screen import PromptType
from .telegram.queue import OutgoingBatch, EditBatch
from .tmux.session import TmuxSession
from .logging_config import logger
from .utils.truncate import truncate_body
from .core.session_manager import ThreadInfo, get_thread_setting
from .config import get_global_defaults
from . import strings

if TYPE_CHECKING:
    from .telegram.queue import TelegramQueue

AUTO_ACCEPT_PHRASES = ["yes", "allow"]

# Only auto-accept regular prompts (not MCP trust prompts for security)
AUTO_ACCEPT_TYPES = {PromptType.REGULAR}


def select_option(options: list[str]) -> str | None:
    """Select safe option for auto-accept.

    Returns option number ("1", "2") or None if no safe option.
    Skips session-wide permissions ("all", "session").
    """
    if not options:
        logger.debug("select_option: no options provided")
        return None

    for option in options:
        option_lower = option.lower()

        # Skip session-wide (too permissive)
        # Match "all" as a word boundary (not as part of "allow")
        if "session" in option_lower or re.search(r'\ball\b', option_lower):
            logger.debug(f"select_option: skipping session-wide option: {option!r}")
            continue

        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            match = re.match(r'^(\d+)\.', option.strip())
            if match:
                logger.debug(f"select_option: matched option {match.group(1)!r} from {option!r}")
                return match.group(1)
            else:
                logger.warning(f"select_option: phrase matched but no number in: {option!r}")
                return None

    logger.debug(f"select_option: no matching option in {options!r}")
    return None


async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
    thread: "ThreadInfo | None" = None,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.

    Args:
        thread: Thread info containing settings for display_mode/line_limit
    """
    # Extract settings from thread
    global_defaults = get_global_defaults()
    thread_id = thread.thread_id if thread else None
    display_mode = get_thread_setting(thread, "display_mode", global_defaults) if thread else "lines"
    line_limit = get_thread_setting(thread, "line_limit", global_defaults) if thread else 5

    logger.debug(
        f"try_auto_accept ENTER: context={context_name} type={prompt_type.value} "
        f"options={options!r} body_len={len(body) if body else 0} display_mode={display_mode}"
    )

    # Security: only auto-accept whitelisted prompt types
    if prompt_type not in AUTO_ACCEPT_TYPES:
        logger.info(f"try_auto_accept SKIP: {prompt_type.value} not in AUTO_ACCEPT_TYPES")
        return False

    selected = select_option(options)
    if selected is None:
        logger.info(f"try_auto_accept SKIP: no matching option for {options!r}")
        return False

    logger.info(f"try_auto_accept OK: {context_name} sending key={selected!r}")

    # Send notification based on display_mode
    if display_mode in ("silence", "current"):
        # No notification in silence/current mode
        pass
    else:
        # Try to edit last tool message (inline auto-accept)
        edited = False
        if thread and thread.last_tool_msg_text:
            replace_key = f"tool:{chat_id}:{thread.thread_id}"

            # Build suffix with optional hint
            thread.auto_accept_count += 1
            # Prefix depends on display_mode:
            # - lines/show_all: empty line (double newline)
            # - headers: single newline
            # - current: space
            if display_mode in ("lines", "show_all"):
                prefix = "\n\n"
            elif display_mode == "headers":
                prefix = "\n"
            else:
                prefix = " "
            suffix = prefix + strings.AUTO_ACCEPT_SUFFIX
            if thread.auto_accept_count % 10 == 0:
                suffix += strings.AUTO_ACCEPT_HINT

            new_text = thread.last_tool_msg_text + suffix

            # Check length limit (Telegram max 4096)
            if len(new_text) <= 4096:
                try:
                    batch = EditBatch(
                        chat_id=chat_id,
                        message_id=0,  # Lookup from sent_statuses via replace_key
                        text=new_text,
                        parse_mode="MarkdownV2",
                        replace_key=replace_key,
                    )
                    await telegram_queue.enqueue(batch)
                    # Update stored text for potential next edit
                    thread.last_tool_msg_text = new_text
                    edited = True
                    logger.debug("try_auto_accept: edited tool message with suffix")
                except Exception as e:
                    logger.debug(f"try_auto_accept: edit failed, falling back: {e}")
            else:
                logger.debug(f"try_auto_accept: message too long ({len(new_text)} chars), sending new message")

        # Fallback: send new message if edit failed
        if not edited:
            # Build body text based on display_mode
            if display_mode == "headers":
                body_text = body.split("\n")[0][:60] if body else "[no details]"
            elif display_mode == "show_all":
                body_text = body if body else "[no details]"
            else:
                body_text = truncate_body(body, verbose=False, max_lines=line_limit) if body else "[no details]"

            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=thread_id,
                messages=[{"text": f"🤖 Auto: {body_text}", "parse_mode": "MarkdownV2"}],
            )
            await telegram_queue.enqueue_nowait(batch)

    try:
        tmux.send_key(selected)
        logger.debug(f"try_auto_accept: tmux.send_key({selected!r}) completed")
    except Exception as e:
        logger.error(f"try_auto_accept: tmux.send_key failed: {e}")
        return False

    return True
