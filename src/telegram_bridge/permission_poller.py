"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum
from datetime import datetime
from pathlib import Path

from aiogram import Bot

# Log directory
LOG_DIR = Path("/home/superbereza/dev/personal-agent/tmp/telegram-bridge-logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    """Write to debug log."""
    with open(LOG_DIR / "poller-debug.log", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


def log_sent(action: str, body: str = None, options: list = None):
    """Log what was sent/deleted to Telegram."""
    with open(LOG_DIR / "poller-sent.log", "a") as f:
        f.write(f"\n=== {action} at {datetime.now()} ===\n")
        if body:
            f.write(f"BODY:\n{body}\n")
        if options:
            f.write(f"OPTIONS:\n{chr(10).join(options)}\n")

from .config import settings
from .screen import parse_screen, PermissionPrompt
from .keyboards import permission_keyboard
from .chunker import chunk_message
from .state import permission_messages
from .session_manager import ProjectState
from .tmux import TmuxSession


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


# Separator for Telegram display
SEPARATOR_SOLID = "─────────────────────"


async def create_poller_task(bot: Bot, project: ProjectState) -> asyncio.Task:
    """Create permission poller task for project."""
    return asyncio.create_task(permission_poller_for_project(bot, project))


async def permission_poller_for_project(bot: Bot, project: ProjectState):
    """
    Background poller for permission prompts.

    Polls tmux every 0.5s, uses debounce before sending.
    State machine: IDLE → DEBOUNCING → SHOWING → IDLE
    """
    log("Poller started")

    # Create TmuxSession from project data
    tmux = TmuxSession(project.tmux_session, project.cwd)
    chat_id = project.chat_id

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg = None

    DEBOUNCE_TIME = 0.5
    POLL_INTERVAL = 0.5

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            print(f"Permission poller: capture error: {e}")
            continue

        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug: log if ❯ detected but no permission parsed
        if "❯" in screen and not is_permission:
            log(f"DEBUG: ❯ found but no permission! parsed={type(parsed).__name__}")
            # Save screen for debugging
            with open(LOG_DIR / "poller-debug-screen.txt", "w") as f:
                f.write(screen)

        # State machine transitions
        if state == PollerState.IDLE:
            if is_permission:
                log(f"IDLE→DEBOUNCING: detected permission, options={parsed.options}")
                log(f"  body={parsed.body[:100] if parsed.body else 'none'}...")
                # Save raw screen for debugging
                with open(LOG_DIR / "poller-screen-raw.txt", "w") as f:
                    f.write(f"=== CAPTURE AT {datetime.now()} ===\n")
                    f.write(screen)
                    f.write("\n=== END ===\n")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                log("DEBOUNCING→IDLE: permission disappeared")
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    # Send to Telegram
                    log(f"DEBOUNCING→SHOWING: sending to TG")
                    log(f"  body:\n{parsed.body[:200]}...")
                    try:
                        content_msg_ids = []

                        # Send body (description + content + question)
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                try:
                                    msg = await bot.send_message(
                                        chat_id, chunk, parse_mode="Markdown"
                                    )
                                except Exception:
                                    msg = await bot.send_message(chat_id, chunk)
                                content_msg_ids.append(msg.message_id)

                        # Send options as text (buttons have character limit)
                        options_text = "\n".join(parsed.options)
                        try:
                            opts_msg = await bot.send_message(chat_id, options_text)
                            content_msg_ids.append(opts_msg.message_id)
                        except Exception:
                            pass

                        kb = permission_keyboard(parsed.options)
                        kb_msg = await bot.send_message(
                            chat_id, "👆", reply_markup=kb
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        log(f"SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg.message_id}")
                        log_sent("SEND", body=parsed.body, options=parsed.options)
                    except Exception as e:
                        print(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                log("SHOWING→IDLE: permission gone, cleaning up")
                log_sent("DELETE (permission gone)")
                # Cleanup if messages still exist
                if kb_msg and kb_msg.message_id in permission_messages:
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(chat_id, kb_msg.message_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg.message_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg = None
            elif parsed.options != last_options or parsed.body != last_body:
                # New question or options changed — resend messages
                log(f"SHOWING: body/options changed, resending")
                try:
                    # Delete old messages
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    if kb_msg:
                        try:
                            await bot.delete_message(chat_id, kb_msg.message_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg.message_id, None)

                    # Send new body
                    content_msg_ids = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        for chunk in chunk_message(body_text):
                            try:
                                msg = await bot.send_message(
                                    chat_id, chunk, parse_mode="Markdown"
                                )
                            except Exception:
                                msg = await bot.send_message(chat_id, chunk)
                            content_msg_ids.append(msg.message_id)

                    # Send options + keyboard
                    options_text = "\n".join(parsed.options)
                    try:
                        opts_msg = await bot.send_message(chat_id, options_text)
                        content_msg_ids.append(opts_msg.message_id)
                    except Exception:
                        pass

                    kb = permission_keyboard(parsed.options)
                    kb_msg = await bot.send_message(
                        chat_id, "👆", reply_markup=kb
                    )
                    permission_messages[kb_msg.message_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                    log_sent("RESEND", body=parsed.body, options=parsed.options)
                except Exception as e:
                    log(f"SHOWING: resend error: {e}")
