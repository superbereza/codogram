import subprocess
import shlex
from dataclasses import dataclass

@dataclass
class TmuxSession:
    name: str
    cwd: str

    def send(self, text: str) -> None:
        """Send text to tmux session and press Enter."""
        session = shlex.quote(self.name)
        escaped = text.replace("'", "'\\''")
        # Send text with -l (literal) flag, then Enter separately
        subprocess.run(f"tmux send-keys -t {session} -l -- '{escaped}'", shell=True, check=True)
        subprocess.run(f"tmux send-keys -t {session} Enter", shell=True, check=True)

    def send_key(self, key: str) -> None:
        """Send a special key (Escape, Enter, C-c, etc.) to tmux session."""
        session = shlex.quote(self.name)
        subprocess.run(f"tmux send-keys -t {session} {key}", shell=True, check=True)

    def exists(self) -> bool:
        result = subprocess.run(
            f"tmux has-session -t {shlex.quote(self.name)} 2>/dev/null",
            shell=True
        )
        return result.returncode == 0

    def create(self) -> None:
        if not self.exists():
            subprocess.run(
                f"tmux new-session -d -s {shlex.quote(self.name)} -c {shlex.quote(self.cwd)}",
                shell=True, check=True
            )

    def attach_command(self) -> str:
        return f"tmux attach -t {shlex.quote(self.name)}"

    def capture_pane(self) -> str:
        """Capture current pane content."""
        session = shlex.quote(self.name)
        result = subprocess.run(
            f"tmux capture-pane -t {session} -p -S -",
            shell=True,
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else ""


def find_all_tmux_by_cwd(cwd: str) -> list[str]:
    """Find all tmux sessions with panes in the given cwd.

    Returns list of session names (may be empty).
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_current_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        sessions = set()
        for line in result.stdout.splitlines():
            parts = line.split(" ", 1)
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
