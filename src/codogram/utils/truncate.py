"""Body truncation for short/long display mode."""

from .. import strings

MAX_LINES = 5


def truncate_body(text: str | None, verbose: bool, max_lines: int | None = MAX_LINES) -> str | None:
    """Truncate body text based on verbose setting.

    Args:
        text: Body text to truncate (or None)
        verbose: If True, return full text. If False, truncate to max_lines.
        max_lines: Number of lines to keep when truncating (default 5).

    Returns:
        Truncated text with SNIP suffix, or full text if verbose=True.
    """
    if text is None:
        return None

    if max_lines is None:
        max_lines = MAX_LINES

    if verbose:
        return text

    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    truncated = lines[:max_lines]
    # Remove trailing empty lines before ellipsis
    while truncated and not truncated[-1].strip():
        truncated.pop()

    return "\n".join(truncated) + f"\n{strings.SNIP}"
