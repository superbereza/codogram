"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum

from aiogram import Bot

from .config import settings
from .screen import parse_screen, PermissionPrompt
from .keyboards import permission_keyboard
from .chunker import chunk_message
from .state import permission_messages


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


# Separators for Telegram display
SEPARATOR_SOLID = "─" * 20
SEPARATOR_DASHED = "╌" * 20


def format_permission_content(perm) -> str:
    """Format permission prompt content for Telegram display."""
    parts = []

    if perm.description:
        parts.append(SEPARATOR_SOLID)
        parts.append(perm.description)

    if perm.content:
        parts.append(SEPARATOR_DASHED)
        parts.append(perm.content)
        parts.append(SEPARATOR_DASHED)

    if perm.question:
        parts.append(perm.question)

    return "\n".join(parts)


async def permission_poller_task(bot: Bot, get_session_fn):
    """
    Background poller for permission prompts.

    Polls tmux every 0.5s, uses debounce before sending.
    State machine: IDLE → DEBOUNCING → SHOWING → IDLE
    """
    print("Permission poller: started")

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    content_msg_ids: list[int] = []
    kb_msg = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            session = get_session_fn()
            screen = session.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            print(f"Permission poller: capture error: {e}")
            continue

        is_permission = isinstance(parsed, PermissionPrompt)

        # State machine transitions - Task 5
        pass
