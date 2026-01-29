# src/codogram/claude/poller/processors/suggestions.py
"""Input suggestions processor."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from ..base import BaseProcessor
from ...screen import parse_input_suggestion, parse_thinking_status
from ....core.session_manager import project_manager, get_thread_setting
from ....config import get_global_defaults
from ....telegram.queue import OutgoingBatch

# Track last suggestion per thread to avoid duplicates
_last_suggestions: dict[str, str | None] = {}


class SuggestionsProcessor(BaseProcessor):
    """Shows input suggestions as ReplyKeyboard."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.msg_key: str | None = None

    async def process(self, screen: str) -> None:
        # Check if feature enabled
        global_defaults = get_global_defaults()
        feat_suggestions = get_thread_setting(self.ctx.thread, "feat_suggestions", global_defaults)
        if not feat_suggestions:
            if self.msg_key:
                # Feature disabled but message exists - cleanup
                self.log_debug("suggestion DELETE (feature disabled)")
                await self.delete_by_key(self.msg_key)
                self.msg_key = None
                _last_suggestions[self._suggestion_key] = None
            return

        # Don't show suggestions while thinking
        thinking_text = parse_thinking_status(screen)
        if thinking_text:
            return

        suggestion = parse_input_suggestion(screen)

        if suggestion and suggestion != _last_suggestions.get(self._suggestion_key):
            # New suggestion - send lightbulb with ReplyKeyboard
            self.log_debug(f"suggestion NEW: {suggestion[:50]}...")
            self.msg_key = f"suggestion:{self.ctx.chat_id}:{self.ctx.thread_id}"

            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=[{"text": "\U0001F4A1"}],
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=suggestion)]],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
                replace_key=self.msg_key,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)
            _last_suggestions[self._suggestion_key] = suggestion

            # Persist message ID for cleanup after restart
            if self.ctx.thread and msg_ids:
                self.ctx.thread.last_suggestion_msg_id = msg_ids[0]
                project_manager._save()

        elif not suggestion and _last_suggestions.get(self._suggestion_key):
            # Suggestion gone - delete lightbulb message
            self.log_debug("suggestion DELETE")
            if self.msg_key:
                await self.delete_by_key(self.msg_key)
                self.msg_key = None
            # Clear persisted message ID
            if self.ctx.thread:
                self.ctx.thread.last_suggestion_msg_id = None
                project_manager._save()
            _last_suggestions[self._suggestion_key] = None

    @property
    def _suggestion_key(self) -> str:
        return f"{self.ctx.chat_id}:{self.ctx.thread_id}"
