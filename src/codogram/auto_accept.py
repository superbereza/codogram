"""Auto-accept mode for permission prompts."""
import re
from typing import TYPE_CHECKING

from .telegram_queue import OutgoingBatch
from .tmux import TmuxSession
from .logging_config import logger

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

AUTO_ACCEPT_PHRASES = ["yes", "allow"]


def select_option(options: list[str]) -> str | None:
    """Select safe option for auto-accept.

    Returns option number ("1", "2") or None if no safe option.
    Skips session-wide permissions ("all", "session").
    """
    if not options:
        return None

    for option in options:
        option_lower = option.lower()

        # Skip session-wide (too permissive)
        # Match "all" as a word boundary (not as part of "allow")
        if "session" in option_lower or re.search(r'\ball\b', option_lower):
            continue

        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            match = re.match(r'^(\d+)\.', option.strip())
            return match.group(1) if match else None

    return None


async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    thread_id: int | None,
    context_name: str,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.
    """
    selected = select_option(options)
    if selected is None:
        return False

    body_text = body if body else "[no details]"
    logger.info(f"auto_accept {context_name} option={selected}")

    batch = OutgoingBatch(
        chat_id=chat_id,
        thread_id=thread_id,
        messages=[{"text": f"🤖 Auto: {body_text}", "parse_mode": "MarkdownV2"}],
    )
    await telegram_queue.enqueue_nowait(batch)

    tmux.send_key(selected)
    return True
