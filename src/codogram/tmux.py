import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .logging_config import logger

# Debug log for tmux send operations
TMUX_DEBUG_LOG = Path(__file__).parent.parent.parent / "logs/tmux-send-debug.log"
TMUX_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)


def _log_tmux_debug(msg: str) -> None:
    """Append debug message to tmux send log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with open(TMUX_DEBUG_LOG, "a") as f:
        f.write(f"{timestamp} {msg}\n")


@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text to tmux session and press Enter."""
        if not text.strip():
            return  # Don't send empty messages

        logger.info(f"tmux_send: session={self.name} text={repr(text[:100])}")
        _log_tmux_debug(f"{'='*60}")
        _log_tmux_debug(f"SEND session={self.name} text={repr(text)}")

        # Capture state BEFORE
        before = self._capture_last_lines(20)
        _log_tmux_debug(f"BEFORE:\n{before}")

        # Step 1: Send C-c
        _log_tmux_debug("[1] Sending C-c...")
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "C-c"],
            check=True
        )
        time.sleep(0.05)

        after_cc = self._capture_last_lines(20)
        _log_tmux_debug(f"AFTER C-c:\n{after_cc}")

        # Step 2: Send text with -l (literal)
        _log_tmux_debug(f"[2] Sending text with -l...")
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "-l", "--", text],
            check=True
        )
        time.sleep(0.1)

        after_text = self._capture_last_lines(20)
        _log_tmux_debug(f"AFTER text:\n{after_text}")

        # Step 3: Send Enter
        _log_tmux_debug("[3] Sending Enter...")
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "Enter"],
            check=True
        )
        time.sleep(0.2)

        after_enter = self._capture_last_lines(20)
        _log_tmux_debug(f"AFTER Enter:\n{after_enter}")
        _log_tmux_debug(f"DONE\n")

    def _capture_last_lines(self, n: int = 20) -> str:
        """Capture last N lines from pane."""
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", self.name, "-p", "-S", f"-{n}"],
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else f"<capture failed: {result.stderr}>"

    def send_key(self, key: str) -> None:
        """Send a special key (Escape, Enter, C-c, etc.) to tmux session."""
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, key],
            check=True
        )

    def exists(self) -> bool:
        """Check if tmux session exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", self.name],
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

    def is_claude_ready(self) -> bool:
        """Check if Claude UI is loaded and ready for input."""
        from .screen import is_claude_ready
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
