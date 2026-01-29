# src/codogram/claude/poller/processors/thinking.py
"""Thinking status display processor."""
import asyncio
from ..base import BaseProcessor
from ...screen import parse_thinking_status
from ....config import get_global_defaults
from ....core.session_manager import get_thread_setting


class ThinkingProcessor(BaseProcessor):
    """Displays and updates Claude's thinking status."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.msg_key: str | None = None
        self.last_update: float = 0.0
        self.last_text: str | None = None

    async def process(self, screen: str) -> None:
        # Check if feature enabled
        global_defaults = get_global_defaults()
        working_status = get_thread_setting(self.ctx.thread, "working_status", global_defaults)
        if not working_status:
            return

        thinking_text = parse_thinking_status(screen)

        if thinking_text:
            now = asyncio.get_event_loop().time()
            # Throttle: update every 3 seconds
            if now - self.last_update >= 3.0:
                key = f"thinking:{self.ctx.chat_id}:{self.ctx.thread_id}"
                needs_resend = self.ctx.thread.thinking_needs_resend if self.ctx.thread else False

                if self.msg_key is None:
                    # First time - send new message
                    self.log_debug(f"thinking status SEND: {thinking_text[:50]}...")
                    await self.send_nowait(thinking_text, replace_key=key)
                    self.msg_key = key

                elif needs_resend:
                    # Watcher sent message - delete + send to keep at bottom
                    self.log_debug(f"thinking status RESEND: {thinking_text[:50]}...")
                    await self.delete_by_key(self.msg_key)
                    await self.send_nowait(thinking_text, replace_key=key)
                    if self.ctx.thread:
                        self.ctx.thread.thinking_needs_resend = False

                else:
                    # No new messages - just edit in place
                    self.log_debug(f"thinking status EDIT: {thinking_text[:50]}...")
                    await self.edit_by_key(thinking_text, key)

                self.last_update = now
                self.last_text = thinking_text

        elif self.msg_key:
            # Claude finished thinking - delete status message
            self.log_debug("thinking status DELETE")
            await self.delete_by_key(self.msg_key)
            self.msg_key = None
            self.last_text = None
            self.last_update = 0.0
