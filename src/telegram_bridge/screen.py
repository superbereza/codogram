import re
from dataclasses import dataclass

@dataclass
class PermissionPrompt:
    options: list[str]           # ["1. Yes", "2. Yes, allow all..."]
    description: str = ""        # "Create file test.txt"
    content: str = ""            # diff/preview between ╌╌╌ markers
    question: str = ""           # "Do you want to create test.txt?"

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
        description = ""
        content = ""
        question = ""

        lines = output.split("\n")

        # Parse options
        for line in lines:
            # Match lines like "❯ 1. Yes" or "  2. Yes, allow..."
            match = re.match(r'\s*[❯\s]\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())

        # Parse description: first non-empty line after ──── solid separator
        in_header = False
        for i, line in enumerate(lines):
            if "─" in line and "─" * 10 in line:  # Solid separator
                in_header = True
                continue
            if in_header and line.strip() and "╌" not in line:
                description = line.strip()
                break

        # Parse content: lines between ╌╌╌ dashed separators
        in_content = False
        content_lines = []
        for line in lines:
            if "╌" in line and "╌" * 10 in line:  # Dashed separator
                if in_content:
                    break  # End of content block
                else:
                    in_content = True  # Start of content block
                continue
            if in_content:
                content_lines.append(line)
        content = "\n".join(content_lines).strip()

        # Parse question: line with "?" before options (before ❯)
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip lines that are part of previous output (start with ●)
            if stripped.startswith("●"):
                continue
            if "?" in line and "❯" not in line:
                # Check if this is before the options section
                for j in range(i + 1, len(lines)):
                    if "❯" in lines[j]:
                        question = line.strip()
                        break
                if question:
                    break

        if options:
            return PermissionPrompt(
                options=options,
                description=description,
                content=content,
                question=question
            )

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
