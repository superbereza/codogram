# src/codogram/claude/poller/processors/stuck.py
"""Stuck message detection processor."""
from ..base import BaseProcessor
from ...screen import extract_input_text, PASTED_PATTERN


class StuckProcessor(BaseProcessor):
    """Detects stuck messages and sends Enter to unstick."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.input_text: str | None = None
        self.seen_count: int = 0

    async def process(self, screen: str) -> None:
        input_text = extract_input_text(screen)

        if not input_text:
            self._reset()
            return

        # Get effective thread for last_sent_message
        effective_thread = self.ctx.thread if self.ctx.thread else self.ctx.project.threads.get(None)
        last_msg = effective_thread.last_sent_message if effective_thread else None

        # Compare first line only (input_text is single line, last_msg may be multiline)
        # Use startswith because tmux wraps long lines - input_text may be truncated
        first_line = last_msg.split('\n')[0] if last_msg else None
        is_potentially_stuck = (
            PASTED_PATTERN.match(input_text) is not None or
            (first_line is not None and first_line.startswith(input_text))
        )

        if not is_potentially_stuck:
            self._reset()
            return

        if input_text == self.input_text:
            self.seen_count += 1
        else:
            self.input_text = input_text
            self.seen_count = 1

        # Debounce: seen twice in a row = stuck, send Enter
        if self.seen_count >= 2:
            self.log_info(f"stuck message detected ({self.seen_count}x), sending Enter")
            self.ctx.tmux.send_key("Enter")
            self._reset()
            # Clear last_sent_message to prevent re-triggering
            if effective_thread:
                effective_thread.last_sent_message = None

    def _reset(self) -> None:
        self.input_text = None
        self.seen_count = 0
