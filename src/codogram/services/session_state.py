"""Session state service - status bar parsing and mode control."""
import time
from dataclasses import dataclass

from ..screen import StatusBar, parse_status_bar
from ..tmux.session import TmuxSession


@dataclass
class StatusResult:
    """Result of get_status operation."""
    success: bool
    status_bar: StatusBar | None = None
    error: str | None = None


@dataclass
class CycleResult:
    """Result of cycle_approval_mode operation."""
    success: bool
    old_mode: str | None = None
    new_mode: str | None = None
    error: str | None = None


class SessionStateService:
    """Service for reading and controlling Claude session state."""

    def get_status(self, tmux: TmuxSession) -> StatusResult:
        """Get current session status from tmux.

        Args:
            tmux: TmuxSession instance

        Returns:
            StatusResult with parsed status bar or error
        """
        if not tmux.exists():
            return StatusResult(success=False, error="tmux session not found")

        output = tmux.capture_pane()
        status_bar = parse_status_bar(output)

        return StatusResult(success=True, status_bar=status_bar)

    def cycle_approval_mode(self, tmux: TmuxSession) -> CycleResult:
        """Send Shift+Tab to cycle approval mode.

        Args:
            tmux: TmuxSession instance

        Returns:
            CycleResult with old and new mode
        """
        if not tmux.exists():
            return CycleResult(success=False, error="tmux session not found")

        # Capture current mode
        output_before = tmux.capture_pane()
        old_status = parse_status_bar(output_before)
        old_mode = old_status.approval_mode

        # Send Shift+Tab (BTab in tmux terminology)
        try:
            tmux.send_key("BTab")
        except Exception as e:
            return CycleResult(success=False, error=f"Failed to send key: {e}")

        # Wait and capture new mode
        time.sleep(0.2)

        output_after = tmux.capture_pane()
        new_status = parse_status_bar(output_after)
        new_mode = new_status.approval_mode

        # Retry once if mode unchanged
        if new_mode == old_mode:
            time.sleep(0.2)
            output_after = tmux.capture_pane()
            new_status = parse_status_bar(output_after)
            new_mode = new_status.approval_mode

        return CycleResult(
            success=True,
            old_mode=old_mode,
            new_mode=new_mode,
        )
