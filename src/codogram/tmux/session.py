import subprocess
import time
from dataclasses import dataclass

from ..logging_config import logger


@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text to tmux session and press Enter."""
        if not text.strip():
            return  # Don't send empty messages

        logger.info(f"tmux_send: session={self.name} text={repr(text[:100])}")

        # Step 0: Cancel permission prompt if active
        self._cancel_permission_if_active()

        # Step 1: Send C-c to interrupt any running operation
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "C-c"],
            check=True
        )
        time.sleep(0.15)

        # Step 2: Send text with -l (literal)
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "-l", "--", text],
            check=True
        )
        time.sleep(0.3)

        # Step 3: Send Enter
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "Enter"],
            check=True
        )
        time.sleep(0.2)

    def _cancel_permission_if_active(self, max_attempts: int = 3) -> bool:
        """Cancel permission prompt if active.

        Sends Escape and waits for prompt to clear.
        Returns True if prompt was cancelled or wasn't active.
        Returns False if failed to cancel after max_attempts.
        """
        from ..claude.screen import parse_screen, PermissionPrompt

        for attempt in range(max_attempts):
            output = self.capture_pane()
            state = parse_screen(output)

            if not isinstance(state, PermissionPrompt):
                return True

            logger.info(f"tmux_send: cancelling permission prompt (attempt {attempt + 1})")

            subprocess.run(
                ["tmux", "send-keys", "-t", self.name, "Escape"],
                check=True
            )
            time.sleep(0.2)  # Wait for Claude to process Escape

        # Final check
        output = self.capture_pane()
        state = parse_screen(output)
        if isinstance(state, PermissionPrompt):
            logger.warning(f"tmux_send: permission prompt still active after {max_attempts} Escape attempts")
            return False

        return True

    def send_key(self, key: str) -> None:
        """Send a special key (Escape, Enter, C-c, etc.) to tmux session."""
        logger.info(f"tmux_send_key: session={self.name} key={key}")

        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, key],
            check=True
        )
        time.sleep(0.15)  # Wait for Claude UI responsiveness

    def exists(self) -> bool:
        """Check if tmux session exists.

        Uses '=' prefix for exact session name matching.
        Without '=', tmux does prefix matching which causes
        'claude-codogram' to match 'claude-codogram-immortal'.
        """
        result = subprocess.run(
            ["tmux", "has-session", "-t", f"={self.name}"],
            capture_output=True
        )
        return result.returncode == 0

    def create(self) -> None:
        """Create tmux session if not exists."""
        if not self.exists():
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self.name, "-c", self.cwd],
                check=True
            )
            # Wait for shell to initialize (zsh config, oh-my-zsh, etc.)
            # Without this, first character of next command may be lost
            time.sleep(0.5)

    def attach_command(self) -> str:
        return f"tmux attach -t {self.name}"

    def capture_pane(self) -> str:
        """Capture current pane content."""
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", self.name, "-p", "-S", "-"],
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else ""

    def clear_pane(self) -> None:
        """Clear pane content and scrollback history.

        Used before resume to prevent stale UI from affecting is_claude_ready() check.
        """
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "clear"],
            check=True
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "Enter"],
            check=True
        )
        time.sleep(0.3)  # Wait for clear to execute
        subprocess.run(
            ["tmux", "clear-history", "-t", self.name],
            check=True
        )

    def is_claude_ready(self) -> bool:
        """Check if Claude UI is loaded and ready for input."""
        from ..claude.screen import is_claude_ready
        output = self.capture_pane()
        return is_claude_ready(output)


def find_all_tmux_by_cwd(cwd: str) -> list[str]:
    """Find all tmux sessions with panes in the given cwd.

    Returns list of session names (may be empty).
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{pane_current_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        sessions = set()
        for line in result.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                session_name, pane_path = parts
                if pane_path == cwd:
                    sessions.add(session_name)

        return sorted(sessions)
    except Exception:
        return []


def find_tmux_by_convention(project_name: str) -> str | None:
    """Find tmux session by naming convention.

    Tries:
    1. claude-{project_name}
    2. {project_name}

    Returns session name if found, None otherwise.
    """
    for pattern in [f"claude-{project_name}", project_name]:
        # Check if session exists (any cwd, just need valid session)
        t = TmuxSession(pattern, "/tmp")
        if t.exists():
            return pattern
    return None


def kill_tmux_session(session_name: str) -> bool:
    """Kill a tmux session by name.

    Args:
        session_name: Name of the tmux session to kill

    Returns:
        True if session was killed, False otherwise
    """
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
