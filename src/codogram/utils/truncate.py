"""Body truncation for short/long display mode."""

from .. import strings

MAX_LINES = 5


def truncate_body(text: str | None, verbose: bool) -> str | None:
    """Truncate body text based on verbose setting.

    Args:
        text: Body text to truncate (or None)
        verbose: If True, return full text. If False, truncate to MAX_LINES.

    Returns:
        Truncated text with SNIP suffix, or full text if verbose=True.
    """
    if text is None:
        return None

    if verbose:
        return text

    lines = text.splitlines()
    if len(lines) <= MAX_LINES:
        return text

    return "\n".join(lines[:MAX_LINES]) + f"\n{strings.SNIP}"
