# src/codogram/claude/poller/processors/compact.py
"""Compact notification processor."""
from ..base import BaseProcessor
from ...screen import detect_compacting
from .... import strings


class CompactProcessor(BaseProcessor):
    """Sends one-time notification when Claude starts compacting."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.notified: bool = False

    async def process(self, screen: str) -> None:
        is_compacting = detect_compacting(screen)

        if is_compacting and not self.notified:
            self.log_info("compact detected, sending notification")
            await self.send_nowait(strings.COMPACTING_STARTED, parse_mode="MarkdownV2")
            self.notified = True
        elif not is_compacting:
            self.notified = False
