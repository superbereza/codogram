# src/codogram/claude/poller/processors/ask_user.py
"""AskUserQuestion prompt processor."""
import asyncio
from enum import Enum

from ..base import BaseProcessor
from ...screen import parse_screen, AskUserQuestion
from ....telegram.queue import OutgoingBatch
from ....telegram.keyboards import ask_user_keyboard
from ....state import permission_messages
from ....config import settings


class AskUserState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


SEPARATOR_SOLID = "------------"


class AskUserQuestionProcessor(BaseProcessor):
    """Handles AskUserQuestion prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = AskUserState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_question: str | None = None
        self.content_msg_ids: list[int] = []
        self.kb_msg_id: int | None = None

    async def process(self, screen: str) -> None:
        parsed = parse_screen(screen)
        is_ask_user = isinstance(parsed, AskUserQuestion)

        if self.state == AskUserState.IDLE:
            await self._handle_idle(parsed, is_ask_user)
        elif self.state == AskUserState.DEBOUNCING:
            await self._handle_debouncing(parsed, is_ask_user)
        elif self.state == AskUserState.SHOWING:
            await self._handle_showing(parsed, is_ask_user)

    async def _handle_idle(self, parsed, is_ask_user: bool) -> None:
        if is_ask_user:
            self.log_debug(f"IDLE->DEBOUNCING: detected AskUserQuestion, header={parsed.header}")
            self.state = AskUserState.DEBOUNCING
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options

    async def _handle_debouncing(self, parsed, is_ask_user: bool) -> None:
        if not is_ask_user:
            self.log_debug("DEBOUNCING->IDLE: AskUserQuestion disappeared")
            self.state = AskUserState.IDLE
            self.last_options = None
            return

        if parsed.options != self.last_options:
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options
            return

        elapsed = asyncio.get_event_loop().time() - self.debounce_start
        if elapsed < settings.permission_poller_debounce:
            return

        # Debounce complete - show prompt
        await self._send_ask_user(parsed)

    async def _handle_showing(self, parsed, is_ask_user: bool) -> None:
        if not is_ask_user:
            self.log_debug("SHOWING->IDLE: AskUserQuestion gone, cleaning up")
            await self._cleanup_messages()
            self._reset_state()
            return

        if parsed.options != self.last_options or parsed.question != self.last_question:
            # Options/question changed - resend
            self.log_debug("SHOWING: options/question changed, resending")
            await self._cleanup_messages()
            await self._send_ask_user(parsed)

    async def _send_ask_user(self, parsed: AskUserQuestion) -> None:
        try:
            # Build message content
            # Format: header + question + options with descriptions
            lines = [SEPARATOR_SOLID]
            lines.append(f"[ ] {parsed.header}")
            lines.append("")
            lines.append(parsed.question)
            lines.append("")

            for opt in parsed.options:
                num = opt.split(".")[0]
                desc = parsed.descriptions.get(num, "")
                if desc:
                    lines.append(f"{opt} -- {desc}")
                else:
                    lines.append(opt)

            body_text = "\n".join(lines)

            messages = [
                {"text": body_text},
                {"text": "point up"},
            ]

            kb = ask_user_keyboard(parsed.options, self.ctx.tmux_name)
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=messages,
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.kb_msg_id = msg_ids[-1] if msg_ids else None
            self.content_msg_ids = msg_ids[:-1] if len(msg_ids) > 1 else []
            if self.kb_msg_id:
                permission_messages[self.kb_msg_id] = self.content_msg_ids

            self.state = AskUserState.SHOWING
            self.last_question = parsed.question
            self.log_debug(f"SHOWING: sent AskUserQuestion, kb_msg={self.kb_msg_id}")
        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = AskUserState.IDLE

    async def _cleanup_messages(self) -> None:
        if self.kb_msg_id and self.kb_msg_id in permission_messages:
            for msg_id in permission_messages[self.kb_msg_id]:
                try:
                    await self.ctx.bot.delete_message(self.ctx.chat_id, msg_id)
                except Exception:
                    pass
            try:
                await self.ctx.bot.delete_message(self.ctx.chat_id, self.kb_msg_id)
            except Exception:
                pass
            permission_messages.pop(self.kb_msg_id, None)

    def _reset_state(self) -> None:
        self.state = AskUserState.IDLE
        self.last_options = None
        self.last_question = None
        self.content_msg_ids = []
        self.kb_msg_id = None
