"""Background permission poller - independent of jsonl watcher."""
import asyncio
from enum import Enum
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from .config import settings
from .screen import parse_screen, PermissionPrompt
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
SEPARATOR_SOLID = "──────────────────"


async def create_poller_task(bot: Bot, project: ProjectState) -> asyncio.Task:
    """Create permission poller task for project."""
    return asyncio.create_task(permission_poller_for_project(bot, project))


async def permission_poller_for_project(bot: Bot, project: ProjectState):
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
    kb_msg = None

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
                    # Send to Telegram
                    logger.debug(f"Poller DEBOUNCING→SHOWING: sending to Telegram")
                    logger.debug(f"Poller: body preview: {parsed.body[:200]}...")
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

                        kb = permission_keyboard(parsed.options, project.tmux_session)
                        kb_msg = await bot.send_message(
                            chat_id, "👆", reply_markup=kb
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"Poller SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg.message_id}")
                    except Exception as e:
                        logger.warning(f"Permission poller: send error: {e}")
                        # Cleanup already-sent messages to avoid orphans
                        for msg_id in content_msg_ids:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        content_msg_ids = []
                        # Handle flood control - wait before retry
                        if "retry after" in str(e).lower():
                            try:
                                retry_after = int(str(e).split("retry after")[1].split()[0])
                                logger.info(f"Permission poller: flood control, waiting {retry_after}s")
                                await asyncio.sleep(retry_after)
                            except (ValueError, IndexError):
                                await asyncio.sleep(5)
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug("Poller SHOWING→IDLE: permission gone, cleaning up")
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
                logger.debug(f"Poller SHOWING: body/options changed, resending")
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

                    kb = permission_keyboard(parsed.options, project.tmux_session)
                    kb_msg = await bot.send_message(
                        chat_id, "👆", reply_markup=kb
                    )
                    permission_messages[kb_msg.message_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"Poller SHOWING: resend error: {e}")
                    # Cleanup already-sent messages
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    content_msg_ids = []
                    # Handle flood control
                    if "retry after" in str(e).lower():
                        try:
                            retry_after = int(str(e).split("retry after")[1].split()[0])
                            logger.info(f"Permission poller: flood control, waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                        except (ValueError, IndexError):
                            await asyncio.sleep(5)


async def create_poller_task_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo) -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller_for_thread(bot, project, thread))


async def permission_poller_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo):
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
    kb_msg = None

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
                        content_msg_ids = []

                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                try:
                                    msg = await bot.send_message(
                                        chat_id, chunk, parse_mode="Markdown",
                                        message_thread_id=thread_id
                                    )
                                except Exception:
                                    msg = await bot.send_message(
                                        chat_id, chunk, message_thread_id=thread_id
                                    )
                                content_msg_ids.append(msg.message_id)

                        options_text = "\n".join(parsed.options)
                        try:
                            opts_msg = await bot.send_message(
                                chat_id, options_text, message_thread_id=thread_id
                            )
                            content_msg_ids.append(opts_msg.message_id)
                        except Exception:
                            pass

                        kb = permission_keyboard(parsed.options, tmux_name)
                        kb_msg = await bot.send_message(
                            chat_id, "👆", reply_markup=kb, message_thread_id=thread_id
                        )
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                    except Exception as e:
                        logger.warning(f"Thread poller {thread.name}: send error: {e}")
                        # Cleanup already-sent messages to avoid orphans
                        for msg_id in content_msg_ids:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        content_msg_ids = []
                        # Handle flood control - wait before retry
                        if "retry after" in str(e).lower():
                            try:
                                retry_after = int(str(e).split("retry after")[1].split()[0])
                                logger.info(f"Thread poller {thread.name}: flood control, waiting {retry_after}s")
                                await asyncio.sleep(retry_after)
                            except (ValueError, IndexError):
                                await asyncio.sleep(5)  # Default backoff
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug(f"Thread poller {thread.name} SHOWING→IDLE: cleanup")
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
                logger.debug(f"Thread poller {thread.name} SHOWING: resending")
                try:
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

                    content_msg_ids = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        for chunk in chunk_message(body_text):
                            try:
                                msg = await bot.send_message(
                                    chat_id, chunk, parse_mode="Markdown",
                                    message_thread_id=thread_id
                                )
                            except Exception:
                                msg = await bot.send_message(
                                    chat_id, chunk, message_thread_id=thread_id
                                )
                            content_msg_ids.append(msg.message_id)

                    options_text = "\n".join(parsed.options)
                    try:
                        opts_msg = await bot.send_message(
                            chat_id, options_text, message_thread_id=thread_id
                        )
                        content_msg_ids.append(opts_msg.message_id)
                    except Exception:
                        pass

                    kb = permission_keyboard(parsed.options, tmux_name)
                    kb_msg = await bot.send_message(
                        chat_id, "👆", reply_markup=kb, message_thread_id=thread_id
                    )
                    permission_messages[kb_msg.message_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"Thread poller {thread.name}: resend error: {e}")
                    # Cleanup already-sent messages
                    for msg_id in content_msg_ids:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    content_msg_ids = []
                    # Handle flood control
                    if "retry after" in str(e).lower():
                        try:
                            retry_after = int(str(e).split("retry after")[1].split()[0])
                            logger.info(f"Thread poller {thread.name}: flood control, waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                        except (ValueError, IndexError):
                            await asyncio.sleep(5)
