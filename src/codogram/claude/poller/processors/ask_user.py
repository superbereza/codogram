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


SEPARATOR_SOLID = "────────────"


class AskUserQuestionProcessor(BaseProcessor):
    """Handles AskUserQuestion prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = AskUserState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_body: str | None = None
        self.last_checked: dict[str, bool] | None = None
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
            self.log_debug(f"IDLE->DEBOUNCING: detected AskUserQuestion, options={len(parsed.options)}")
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
            # AskUserQuestion gone - just reset state, keep messages for history
            self.log_debug("SHOWING->IDLE: AskUserQuestion gone")
            self._reset_state()
            return

        # Same body = same question, just update keyboard if checkboxes changed
        if parsed.body == self.last_body:
            if parsed.checked != self.last_checked:
                self.log_debug(f"SHOWING: checkbox changed old={self.last_checked} new={parsed.checked}")
                if self.kb_msg_id:
                    await self._update_keyboard(parsed)
                else:
                    self.log_warning("SHOWING: no kb_msg_id to update!")
            return

        # Different body = truly new question
        self.log_debug("SHOWING: new question detected (body changed), sending")
        await self._send_ask_user(parsed)

    async def _send_ask_user(self, parsed: AskUserQuestion) -> None:
        try:
            # Build messages like PermissionProcessor - body + options as-is
            messages = []

            if parsed.body:
                body_text = SEPARATOR_SOLID + "\n" + parsed.body
                messages.append({"text": body_text})

            options_text = "\n".join(parsed.options)
            messages.append({"text": options_text})
            messages.append({"text": "👆 select or text me"})

            kb = ask_user_keyboard(parsed.options, self.ctx.tmux_name, parsed.checked)
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
            self.last_body = parsed.body
            self.last_checked = parsed.checked
            self.log_debug(f"SHOWING: sent AskUserQuestion, kb_msg={self.kb_msg_id}")
        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = AskUserState.IDLE

    async def _update_keyboard(self, parsed: AskUserQuestion) -> None:
        """Update keyboard without sending new messages (for checkbox toggle)."""
        try:
            kb = ask_user_keyboard(parsed.options, self.ctx.tmux_name, parsed.checked)
            await self.ctx.bot.edit_message_reply_markup(
                chat_id=self.ctx.chat_id,
                message_id=self.kb_msg_id,
                reply_markup=kb,
            )
            self.last_checked = parsed.checked
            self.log_debug(f"SHOWING: updated keyboard for checkbox toggle")
        except Exception as e:
            self.log_warning(f"keyboard update error: {e}")

    def _reset_state(self) -> None:
        self.state = AskUserState.IDLE
        self.last_options = None
        self.last_body = None
        self.last_checked = None
        self.content_msg_ids = []
        self.kb_msg_id = None
