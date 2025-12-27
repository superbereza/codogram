import subprocess
import time
from dataclasses import dataclass

@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text to tmux session and press Enter."""
        if not text.strip():
            return  # Don't send empty messages

        # Use shell=False for safety (no escaping needed)
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "-l", "--", text],
            check=True
        )
        time.sleep(0.1)  # Delay to ensure text is processed before Enter
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "Enter"],
            check=True
        )

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
