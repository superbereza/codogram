"""Dashboard service for showing all projects."""
from dataclasses import dataclass

from .. import strings


@dataclass
class ProjectInfo:
    """Information about a project for dashboard display."""
    chat_name: str
    directory: str
    creator: str
    members: int
    active_sessions: int


def format_dashboard(projects: list[ProjectInfo]) -> str:
    """Format dashboard message with all projects.

    Args:
        projects: List of ProjectInfo objects

    Returns:
        Formatted dashboard string
    """
    if not projects:
        return strings.DASH_EMPTY

    lines = [strings.DASH_HEADER, ""]

    for i, p in enumerate(projects, 1):
        if p.active_sessions > 0:
            status = strings.DASH_STATUS_ACTIVE.format(count=p.active_sessions)
        else:
            status = strings.DASH_STATUS_INACTIVE

        lines.append(strings.DASH_PROJECT.format(
            num=i,
            chat_name=p.chat_name,
            directory=p.directory,
            creator=p.creator,
            members=p.members,
            status=status,
        ))
        lines.append("")

    total = len(projects)
    active = count_active_sessions(projects)
    lines.append(strings.DASH_FOOTER.format(total=total, active=active))

    return "\n".join(lines)


def count_active_sessions(projects: list[ProjectInfo]) -> int:
    """Count total active Claude sessions across all projects."""
    return sum(p.active_sessions for p in projects)
