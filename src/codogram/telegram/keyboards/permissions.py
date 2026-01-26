"""Permission prompt keyboards."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def permission_keyboard(
    options: list[str],
    tmux_name: str,
    expanded: bool = False,
    current_page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Build permission prompt keyboard.

    Args:
        options: Permission options (e.g., ["1. Yes", "2. Yes, allow all", ...])
        tmux_name: Tmux session name for callback routing
        expanded: Whether body is expanded
        current_page: Current page index (0-based)
        total_pages: Total number of pages

    Returns:
        Inline keyboard with option buttons and expand/collapse controls

    Example:
        >>> options = ["1. Yes", "2. Yes, allow all", "3. No"]
        >>> keyboard = permission_keyboard(options, "claude-myproject", expanded=True, total_pages=3)
    """
    buttons = []

    # Expand/collapse and pagination controls
    if expanded and total_pages > 1:
        # Show pagination: [<] [>]
        nav_row = []
        if current_page > 0:
            nav_row.append(InlineKeyboardButton(
                text="\u25c0",  # <
                callback_data=f"perm:{tmux_name}:page:{current_page - 1}"
            ))
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="\u25b6",  # >
                callback_data=f"perm:{tmux_name}:page:{current_page + 1}"
            ))
        if nav_row:
            buttons.append(nav_row)

    # Expand/collapse button
    if expanded:
        buttons.append([InlineKeyboardButton(
            text="Show less",
            callback_data=f"perm:{tmux_name}:collapse"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="Show more",
            callback_data=f"perm:{tmux_name}:expand"
        )])

    # Option buttons (numbered) in a single row
    option_row = []
    for i, opt in enumerate(options[:3]):  # Max 3 options
        option_row.append(InlineKeyboardButton(
            text=f"[{i + 1}]",
            callback_data=f"perm:{tmux_name}:{i + 1}"
        ))
    # Add Cancel button to the same row
    option_row.append(InlineKeyboardButton(
        text=strings.BTN_CANCEL_X,
        callback_data=f"perm:{tmux_name}:esc"
    ))
    buttons.append(option_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
