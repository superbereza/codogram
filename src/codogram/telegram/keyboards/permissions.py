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

    # Option buttons - each on its own row, with full label
    for i, opt in enumerate(options[:3]):  # Max 3 options
        # Use option text as-is (e.g., "1. Yes"), truncate if needed
        label = opt
        if len(label) > 40:
            label = label[:37] + "..."
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"perm:{tmux_name}:{i + 1}"
        )])

    # Navigation + Cancel row: [◀] [Cancel] [▶]
    nav_cancel_row = []
    if expanded and total_pages > 1:
        # Left button: active or placeholder
        if current_page > 0:
            nav_cancel_row.append(InlineKeyboardButton(
                text="◀",
                callback_data=f"perm:{tmux_name}:page:{current_page - 1}"
            ))
        else:
            nav_cancel_row.append(InlineKeyboardButton(
                text="•",
                callback_data=f"perm:{tmux_name}:noop"
            ))
    nav_cancel_row.append(InlineKeyboardButton(
        text=strings.BTN_CANCEL_X,
        callback_data=f"perm:{tmux_name}:esc"
    ))
    if expanded and total_pages > 1:
        # Right button: active or placeholder
        if current_page < total_pages - 1:
            nav_cancel_row.append(InlineKeyboardButton(
                text="▶",
                callback_data=f"perm:{tmux_name}:page:{current_page + 1}"
            ))
        else:
            nav_cancel_row.append(InlineKeyboardButton(
                text="•",
                callback_data=f"perm:{tmux_name}:noop"
            ))
    buttons.append(nav_cancel_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
