# src/codogram/claude/poller/context.py
"""Shared context for all poller processors."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from ...telegram.queue import TelegramQueue
    from ...core.session_manager import ProjectState, ThreadInfo
    from ...tmux.session import TmuxSession


@dataclass
class PollerContext:
    """Shared context passed to all processors."""
    bot: Bot
    project: "ProjectState"
    thread: "ThreadInfo | None"
    tmux: "TmuxSession"
    queue: "TelegramQueue"
    chat_id: int
    thread_id: int | None
    log_prefix: str
    context_name: str
    tmux_name: str
