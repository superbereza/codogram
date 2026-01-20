"""Auto-accept mode for permission prompts."""
import re
from typing import TYPE_CHECKING

from .screen import PromptType
from .telegram_queue import OutgoingBatch
from .tmux import TmuxSession
from .logging_config import logger
from .utils.truncate import truncate_body

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

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
    thread_id: int | None,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
    verbose: bool = False,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.
    """
    logger.debug(
        f"try_auto_accept ENTER: context={context_name} type={prompt_type.value} "
        f"options={options!r} body_len={len(body) if body else 0}"
    )

    # Security: only auto-accept whitelisted prompt types
    if prompt_type not in AUTO_ACCEPT_TYPES:
        logger.info(f"try_auto_accept SKIP: {prompt_type.value} not in AUTO_ACCEPT_TYPES")
        return False

    selected = select_option(options)
    if selected is None:
        logger.info(f"try_auto_accept SKIP: no matching option for {options!r}")
        return False

    body_text = truncate_body(body, verbose=verbose) if body else "[no details]"
    logger.info(f"try_auto_accept OK: {context_name} sending key={selected!r}")

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
