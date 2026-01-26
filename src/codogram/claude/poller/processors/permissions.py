# src/codogram/claude/poller/processors/permissions.py
"""Permission prompt processor with state machine."""
import asyncio
from enum import Enum

from ..base import BaseProcessor
from ...screen import parse_screen, PermissionPrompt
from ....telegram.queue import OutgoingBatch
from ....telegram.keyboards import permission_keyboard
from ....state import permission_states, PermissionPromptState
from ....auto_accept import try_auto_accept
from ....config import settings
from ....utils.truncate import truncate_body
from .ask_user import _parse_review_answers


class PermissionState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


SEPARATOR_SOLID = "────────────"


class PermissionProcessor(BaseProcessor):
    """Handles permission prompts with debounce and state machine."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = PermissionState.IDLE
        self.debounce_start: float = 0.0
        self.last_options: list[str] | None = None
        self.last_body: str | None = None

        # Single message approach (replaces content_msg_ids + kb_msg_id)
        self.msg_id: int | None = None
        self.expanded: bool = False
        self.current_page: int = 0
        self.chunks: list[str] | None = None  # Body chunks for pagination

    async def process(self, screen: str) -> None:
        parsed = parse_screen(screen)
        is_permission = isinstance(parsed, PermissionPrompt)


        if self.state == PermissionState.IDLE:
            await self._handle_idle(parsed, is_permission)
        elif self.state == PermissionState.DEBOUNCING:
            await self._handle_debouncing(parsed, is_permission)
        elif self.state == PermissionState.SHOWING:
            await self._handle_showing(parsed, is_permission)

    async def _handle_idle(self, parsed, is_permission: bool) -> None:
        if is_permission:
            self.log_debug(f"IDLE->DEBOUNCING: detected permission, options={parsed.options}")
            self.log_debug(f"body={parsed.body[:100] if parsed.body else 'none'}...")
            self.state = PermissionState.DEBOUNCING
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options

    async def _handle_debouncing(self, parsed, is_permission: bool) -> None:
        if not is_permission:
            self.log_debug("DEBOUNCING->IDLE: permission disappeared")
            self.state = PermissionState.IDLE
            self.last_options = None
            return

        if parsed.options != self.last_options:
            self.debounce_start = asyncio.get_event_loop().time()
            self.last_options = parsed.options
            return

        elapsed = asyncio.get_event_loop().time() - self.debounce_start
        if elapsed < settings.permission_poller_debounce:
            return

        # Debounce complete - check auto-accept or show prompt
        auto_accept = self.ctx.thread.auto_accept if self.ctx.thread else self.ctx.project.auto_accept
        verbose = self.ctx.thread.verbose if self.ctx.thread else self.ctx.project.verbose

        self.log_debug(f"DEBOUNCING: auto_accept={auto_accept} prompt_type={parsed.prompt_type.value}")

        if auto_accept:
            accepted = await try_auto_accept(
                parsed.options, parsed.body, self.ctx.tmux,
                self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                self.ctx.context_name, prompt_type=parsed.prompt_type, verbose=verbose,
            )
            if accepted:
                self.log_info("DEBOUNCING->SHOWING: auto-accepted successfully")
                self.state = PermissionState.SHOWING
                self.last_body = parsed.body
                return
            else:
                self.log_info("DEBOUNCING: auto_accept returned False, falling through to manual")

        # Show prompt in Telegram
        await self._send_permission(parsed, verbose)

    async def _handle_showing(self, parsed, is_permission: bool) -> None:
        if not is_permission:
            self.log_debug("SHOWING->IDLE: permission gone, cleaning up")
            await self._cleanup_messages()
            self._reset_state()
            return

        if parsed.options != self.last_options or parsed.body != self.last_body:
            # Options/body changed - check auto-accept or resend
            auto_accept = self.ctx.thread.auto_accept if self.ctx.thread else self.ctx.project.auto_accept
            verbose = self.ctx.thread.verbose if self.ctx.thread else self.ctx.project.verbose

            self.log_debug(f"SHOWING: options/body changed! auto_accept={auto_accept}")

            if auto_accept:
                accepted = await try_auto_accept(
                    parsed.options, parsed.body, self.ctx.tmux,
                    self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                    self.ctx.context_name, prompt_type=parsed.prompt_type, verbose=verbose,
                )
                if accepted:
                    self.log_info("SHOWING: options/body changed, auto-accepted again")
                    self.last_options = parsed.options
                    self.last_body = parsed.body
                    return

            # Resend prompt
            self.log_debug("SHOWING: body/options changed, resending")
            await self._cleanup_messages()
            await self._send_permission(parsed, verbose)

    async def _send_permission(self, parsed: PermissionPrompt, verbose: bool) -> None:
        try:
            # Check if this is a review screen (AskUserQuestion final review)
            review_answers = _parse_review_answers(parsed.body) if parsed.body else None

            messages = []
            if review_answers:
                # Format review answers nicely
                lines = ["\ud83d\udccb Review your answers", ""]
                for question, answer in review_answers:
                    lines.append(f"\u25cf {question}")
                    lines.append(f"  \u2192 {answer}")
                    lines.append("")
                body_text = SEPARATOR_SOLID + "\n" + "\n".join(lines).strip()
                messages.append({"text": body_text})
            elif parsed.body:
                display_body = truncate_body(parsed.body, verbose=verbose)
                if display_body:
                    body_text = SEPARATOR_SOLID + "\n" + display_body
                    messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

            options_text = "\n".join(parsed.options)
            messages.append({"text": options_text})
            messages.append({"text": "\ud83d\udc46"})

            kb = permission_keyboard(parsed.options, self.ctx.tmux_name)
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=messages,
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.msg_id = msg_ids[-1] if msg_ids else None
            if self.msg_id:
                # Store state for callback routing
                permission_states[self.msg_id] = PermissionPromptState(
                    tmux_name=self.ctx.tmux_name,
                    body=parsed.body or "",
                    options=parsed.options,
                    expanded=False,
                    current_page=0,
                    chunks=[],  # Will be populated when expanded
                )
                self.log_debug(f"saved permission_states[{self.msg_id}]")

            self.state = PermissionState.SHOWING
            self.last_body = parsed.body
            self.log_debug(f"SHOWING: sent {len(parsed.options)} options, msg_id={self.msg_id}")
        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = PermissionState.IDLE

    async def _cleanup_messages(self) -> None:
        if self.msg_id:
            try:
                await self.ctx.bot.delete_message(self.ctx.chat_id, self.msg_id)
            except Exception:
                pass
            permission_states.pop(self.msg_id, None)

    def _reset_state(self) -> None:
        self.state = PermissionState.IDLE
        self.last_options = None
        self.last_body = None
        self.msg_id = None
        self.expanded = False
        self.current_page = 0
        self.chunks = None
