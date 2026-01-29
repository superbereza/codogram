# src/codogram/claude/poller/crash.py
"""Crash detection logic."""
from ..screen import is_claude_ready

CRASH_SIGNATURES = [
    "panicked at",
    "fatal runtime error",
    "core dumped",
    "SIGSEGV",
    "SIGABRT",
]

SHELL_PROMPTS = ["➜", "$ ", "# ", "❯ "]


def detect_crash(screen: str) -> str | None:
    """Detect if Claude has crashed. Returns crash reason or None.

    Only triggers if ALL conditions met:
    1. Claude UI NOT visible (is_claude_ready = False)
    2. Shell prompt visible (Claude exited to shell)
    3. Crash signature in LAST 15 lines (not scrollback)
    """
    if is_claude_ready(screen):
        return None

    lines = screen.split("\n")
    last_lines = "\n".join(lines[-15:])

    has_shell = any(p in last_lines for p in SHELL_PROMPTS)
    if not has_shell:
        return None

    for sig in CRASH_SIGNATURES:
        if sig in last_lines:
            return sig
    return None
