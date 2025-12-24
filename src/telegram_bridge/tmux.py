import subprocess
import shlex
from dataclasses import dataclass

@dataclass
class TmuxSession:
    name: str
    cwd: str

    def _build_send_command(self, text: str) -> str:
        escaped = text.replace("'", "'\\''")
        return f"tmux send-keys -t {shlex.quote(self.name)} '{escaped}' Enter"

    def send(self, text: str) -> None:
        cmd = self._build_send_command(text)
        subprocess.run(cmd, shell=True, check=True)

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
