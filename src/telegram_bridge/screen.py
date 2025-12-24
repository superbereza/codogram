import re
from dataclasses import dataclass

@dataclass
class PermissionPrompt:
    options: list[str]  # ["1. Yes", "2. Yes, allow all...", ...]

@dataclass
class ToolProgress:
    tool: str
    output: str

@dataclass
class Idle:
    pass

ScreenState = PermissionPrompt | ToolProgress | Idle

def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state."""

    # Permission prompt: look for ❯ marker with numbered options
    if "❯" in output:
        options = []
        for line in output.split("\n"):
            # Match lines like "❯ 1. Yes" or "  2. Yes, allow..."
            match = re.match(r'\s*[❯\s]\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
        if options:
            return PermissionPrompt(options=options)

    # Tool progress: look for ● or ✶ with tool name
    progress_match = re.search(r'[●✶]\s*(\w+)\(([^)]*)\)', output)
    if progress_match and "❯" not in output:
        tool = progress_match.group(1)
        # Extract recent output (last lines before prompt)
        lines = output.strip().split("\n")
        output_lines = []
        for line in lines:
            if line.strip().startswith("⎿") or (line.strip() and not line.strip().startswith(("●", "✶", ">", "─"))):
                output_lines.append(line.strip())
        return ToolProgress(tool=tool, output="\n".join(output_lines[-5:]))

    return Idle()
