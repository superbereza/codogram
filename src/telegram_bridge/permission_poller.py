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
        if state == PollerState.IDLE:
            if is_permission:
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
                    # Send to Telegram
                    try:
                        content_text = format_permission_content(parsed)
                        content_msg_ids = []

                        if content_text.strip():
                            for chunk in chunk_message(content_text):
                                try:
                                    msg = await bot.send_message(
                                        settings.chat_id, chunk, parse_mode="Markdown"
                                    )
                                except Exception:
                                    msg = await bot.send_message(settings.chat_id, chunk)
                                content_msg_ids.append(msg.message_id)

                        kb = permission_keyboard(parsed.options)
                        kb_msg = await bot.send_message(
                            settings.chat_id, "👆", reply_markup=kb
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        print(f"Permission poller: sent {len(parsed.options)} options")
                    except Exception as e:
                        print(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                # Cleanup if messages still exist
                if kb_msg and kb_msg.message_id in permission_messages:
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(settings.chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(settings.chat_id, kb_msg.message_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg.message_id, None)

                state = PollerState.IDLE
                last_options = None
                content_msg_ids = []
                kb_msg = None
            elif parsed.options != last_options:
                try:
                    kb = permission_keyboard(parsed.options)
                    if kb_msg:
                        await kb_msg.edit_reply_markup(reply_markup=kb)
                    last_options = parsed.options
                except Exception:
                    pass
