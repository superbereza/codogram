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
from ....chunker import _split_text
from .ask_user import _parse_review_answers


class PermissionState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


SEPARATOR_SOLID = "────────────"
PERMISSION_PAGE_SIZE = 500  # Characters per page for expanded view


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

        # Cleanup old permission message from before restart
        self._cleanup_old_permission_msg()

    def _cleanup_old_permission_msg(self) -> None:
        """Delete permission message that survived bot restart."""
        thread = self.ctx.thread
        if not thread:
            return
        old_msg_id = getattr(thread, 'last_permission_msg_id', None)
        if old_msg_id:
            self.log_debug(f"cleaning up old permission msg_id={old_msg_id}")
            # Schedule deletion (can't await in __init__)
            asyncio.create_task(self._delete_old_msg(old_msg_id))
            thread.last_permission_msg_id = None

    async def _delete_old_msg(self, msg_id: int) -> None:
        """Delete old permission message."""
        try:
            await self.ctx.bot.delete_message(self.ctx.chat_id, msg_id)
            self.log_debug(f"deleted old permission msg_id={msg_id}")
        except Exception as e:
            self.log_debug(f"failed to delete old permission msg_id={msg_id}: {e}")

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
        display_mode = self.ctx.thread.display_mode if self.ctx.thread else self.ctx.project.display_mode
        line_limit = self.ctx.thread.line_limit if self.ctx.thread else self.ctx.project.line_limit

        self.log_debug(f"DEBOUNCING: auto_accept={auto_accept} prompt_type={parsed.prompt_type.value}")

        if auto_accept:
            accepted = await try_auto_accept(
                parsed.options, parsed.body, self.ctx.tmux,
                self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                self.ctx.context_name, prompt_type=parsed.prompt_type,
                display_mode=display_mode, line_limit=line_limit,
            )
            if accepted:
                self.log_info("DEBOUNCING->SHOWING: auto-accepted successfully")
                self.state = PermissionState.SHOWING
                self.last_body = parsed.body
                return
            else:
                self.log_info("DEBOUNCING: auto_accept returned False, falling through to manual")

        # Show prompt in Telegram
        await self._send_permission(parsed, display_mode)

    async def _handle_showing(self, parsed, is_permission: bool) -> None:
        if not is_permission:
            self.log_debug("SHOWING->IDLE: permission gone, cleaning up")
            await self._cleanup_messages()
            self._reset_state()
            return

        if parsed.options != self.last_options or parsed.body != self.last_body:
            # Options/body changed - check auto-accept or resend
            auto_accept = self.ctx.thread.auto_accept if self.ctx.thread else self.ctx.project.auto_accept
            display_mode = self.ctx.thread.display_mode if self.ctx.thread else self.ctx.project.display_mode
            line_limit = self.ctx.thread.line_limit if self.ctx.thread else self.ctx.project.line_limit

            self.log_debug(f"SHOWING: options/body changed! auto_accept={auto_accept}")

            if auto_accept:
                accepted = await try_auto_accept(
                    parsed.options, parsed.body, self.ctx.tmux,
                    self.ctx.queue, self.ctx.chat_id, self.ctx.thread_id,
                    self.ctx.context_name, prompt_type=parsed.prompt_type,
                    display_mode=display_mode, line_limit=line_limit,
                )
                if accepted:
                    self.log_info("SHOWING: options/body changed, auto-accepted again")
                    self.last_options = parsed.options
                    self.last_body = parsed.body
                    return

            # Resend prompt
            self.log_debug("SHOWING: body/options changed, resending")
            await self._cleanup_messages()
            await self._send_permission(parsed, display_mode)

    async def _send_permission(self, parsed: PermissionPrompt, display_mode: str) -> None:
        """Send permission prompt as single collapsible message."""
        try:
            # Check if this is a review screen (AskUserQuestion final review)
            review_answers = _parse_review_answers(parsed.body) if parsed.body else None

            # Build message text (collapsed by default)
            text = self._build_permission_text(parsed, collapsed=True, review_answers=review_answers)

            # Build keyboard (no pagination needed when collapsed)
            kb = permission_keyboard(
                parsed.options,
                self.ctx.tmux_name,
                expanded=False,
                current_page=0,
                total_pages=1,
            )

            # Send single message
            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=[{"text": text, "parse_mode": "MarkdownV2"}],
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.msg_id = msg_ids[0] if msg_ids else None

            # Save to thread for restart persistence
            if self.ctx.thread and self.msg_id:
                self.ctx.thread.last_permission_msg_id = self.msg_id
                # Persist config
                from ....core.session_manager import project_manager
                project_manager._save()
                self.log_debug(f"saved last_permission_msg_id={self.msg_id} to thread")
            else:
                self.log_debug(f"NOT saving last_permission_msg_id: thread={self.ctx.thread is not None}, msg_id={self.msg_id}")

            # Save state for callback handlers
            if self.msg_id:
                permission_states[self.msg_id] = PermissionPromptState(
                    tmux_name=self.ctx.tmux_name,
                    body=parsed.body or "",
                    options=parsed.options,
                    expanded=False,
                    current_page=0,
                    chunks=[],  # Computed lazily on expand
                )
                self.log_debug(f"saved permission_states[{self.msg_id}]")

            self.state = PermissionState.SHOWING
            self.last_body = parsed.body
            self.log_debug(f"SHOWING: sent collapsed prompt, msg={self.msg_id}")

        except Exception as e:
            self.log_warning(f"send error: {e}")
            self.state = PermissionState.IDLE

    def _build_permission_text(
        self,
        parsed: PermissionPrompt,
        collapsed: bool,
        review_answers: list[tuple[str, str]] | None = None,
    ) -> str:
        """Build permission prompt message text.

        Args:
            parsed: Parsed permission prompt
            collapsed: If True, show only header. If False, show body page.
            review_answers: Parsed review answers (for AskUserQuestion review screen)

        Returns:
            Formatted message text
        """
        # Header: tool name + brief description
        header = self._get_prompt_header(parsed)

        if collapsed:
            # Collapsed: header + hint + options
            lines = [header, "click `Show more` to expand", ""]
            lines.extend(parsed.options)
            return "\n".join(lines)

        # Expanded: body content only (no header duplication)
        lines = [SEPARATOR_SOLID]

        if review_answers:
            # Format review answers nicely
            review_lines = []
            for question, answer in review_answers:
                review_lines.append(f"* {question}")
                review_lines.append(f"  -> {answer}")
                review_lines.append("")
            body_content = "\n".join(review_lines).strip()
        elif self.chunks:
            # Show current page with indicator
            total = len(self.chunks)
            if total > 1:
                body_content = f"[{self.current_page + 1}/{total}]\n{self.chunks[self.current_page]}"
            else:
                body_content = self.chunks[self.current_page]
        else:
            body_content = parsed.body or ""

        lines.append(body_content)
        lines.append(SEPARATOR_SOLID)
        lines.append("")
        lines.extend(parsed.options)

        return "\n".join(lines)

    def _get_prompt_header(self, parsed: PermissionPrompt) -> str:
        """Extract brief header from permission prompt body."""
        if not parsed.body:
            return "Permission request"

        # Try to extract tool name and brief description from first line
        first_line = parsed.body.split("\n")[0][:60]
        return first_line if first_line else "Permission request"

    async def _cleanup_messages(self) -> None:
        """Delete permission message and state."""
        if self.msg_id:
            # Remove state
            permission_states.pop(self.msg_id, None)
            # Delete message
            try:
                await self.ctx.bot.delete_message(self.ctx.chat_id, self.msg_id)
            except Exception:
                pass
            # Clear thread persistence
            if self.ctx.thread:
                self.ctx.thread.last_permission_msg_id = None
            self.msg_id = None

    def _reset_state(self) -> None:
        self.state = PermissionState.IDLE
        self.last_options = None
        self.last_body = None
        self.msg_id = None
        self.expanded = False
        self.current_page = 0
        self.chunks = None
