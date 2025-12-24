"""Background permission poller - independent of jsonl watcher."""
from enum import Enum


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"


# Separators for Telegram display
SEPARATOR_SOLID = "─" * 20
SEPARATOR_DASHED = "╌" * 20


def format_permission_content(perm) -> str:
    """Format permission prompt content for Telegram display."""
    parts = []

    if perm.description:
        parts.append(SEPARATOR_SOLID)
        parts.append(perm.description)

    if perm.content:
        parts.append(SEPARATOR_DASHED)
        parts.append(perm.content)
        parts.append(SEPARATOR_DASHED)

    if perm.question:
        parts.append(perm.question)

    return "\n".join(parts)
