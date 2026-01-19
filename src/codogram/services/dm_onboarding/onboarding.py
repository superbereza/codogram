"""DM onboarding business logic."""
from ... import strings  # 3 levels up: dm_onboarding -> services -> codogram


SLIDES = [
    strings.DM_SLIDE_1,
    strings.DM_SLIDE_2,
    strings.DM_SLIDE_3,
]


def get_slide_content(index: int) -> str | None:
    """Get content for a carousel slide.

    Args:
        index: 0-indexed slide number

    Returns:
        Slide content string or None if invalid index
    """
    if 0 <= index < len(SLIDES):
        return SLIDES[index]
    return None


def get_total_slides() -> int:
    """Get total number of carousel slides."""
    return len(SLIDES)


def format_validation_checks(results: list) -> str:
    """Format all validation checks with status indicators.

    Args:
        results: List of ValidationResult (both ok and not ok)

    Returns:
        Formatted string with [v] or [x] for each check
    """
    lines = []
    for r in results:
        if r.ok:
            lines.append(f"`[v]` {r.name}")
        else:
            lines.append(f"`[x]` {r.message}")
            if r.fix_hint:
                lines.append(f"    `{r.fix_hint}`")
    return "\n".join(lines)


def format_validation_warnings(results: list) -> str:
    """Format validation warnings for display.

    Args:
        results: List of ValidationResult with ok=False

    Returns:
        Formatted string with warnings (using [!] indicator)
    """
    lines = []
    for r in results:
        if not r.ok:
            lines.append(f"`[!]` {r.message}")
    return "\n".join(lines)
