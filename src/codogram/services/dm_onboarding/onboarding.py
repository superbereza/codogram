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


def format_validation_checks(results: list, indent: str = "  ") -> str:
    """Format validation checks with icons, one per line.

    Args:
        results: List of ValidationResult
        indent: Prefix for each line (default: 2 spaces)

    Returns:
        Formatted string with each check on its own line
    """
    lines = []
    for r in results:
        if r.ok:
            lines.append(f"{indent}✓ {r.name}")
        else:
            lines.append(f"{indent}✗ {r.name}")
    return "\n".join(lines)


def format_optional_checks(results: list, indent: str = "  ") -> str:
    """Format optional checks with icons, using ○ for not configured.

    Args:
        results: List of ValidationResult
        indent: Prefix for each line (default: 2 spaces)

    Returns:
        Formatted string with each check on its own line
    """
    lines = []
    for r in results:
        if r.ok:
            lines.append(f"{indent}✓ {r.name}")
        else:
            # Use ○ for optional items that aren't configured
            lines.append(f"{indent}○ {r.name}")
    return "\n".join(lines)


def format_validation_errors(results: list) -> str:
    """Format failed checks with fix hints.

    Args:
        results: List of ValidationResult (only failed ones)

    Returns:
        Formatted string with errors and hints
    """
    lines = []
    for r in results:
        if not r.ok:
            lines.append(f"✗ {r.message}")
            if r.fix_hint:
                lines.append(f"  `{r.fix_hint}`")
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
