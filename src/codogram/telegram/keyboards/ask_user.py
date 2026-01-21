"""Inline keyboard for AskUserQuestion prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def ask_user_keyboard(
    options: list[str],
    tmux_session: str,
    checked: dict[str, bool] | None = None,
) -> InlineKeyboardMarkup:
    """Build inline keyboard from AskUserQuestion options.

    Args:
        options: List of options in format ["1. Option", "2. Option", ...]
        tmux_session: Tmux session name for stable routing
        checked: For multi-select: {"1": True, "2": False} checkbox states

    Returns:
        InlineKeyboardMarkup with buttons for each option plus Cancel/Submit
    """
    buttons = []
    is_multi_select = checked is not None

    if is_multi_select:
        # Multi-select: all options get checkboxes
        for opt in options:
            num = opt.split(".")[0].strip()
            label = opt.split(".", 1)[1].strip()[:20]
            is_checked = checked.get(num, False)
            display = f"✓ {label}" if is_checked else f"☐ {label}"

            # Type something needs special handling (multi + type prompt)
            is_type = "type" in label.lower()
            callback = f"ask:{num}:multitype:{tmux_session}" if is_type else f"ask:{num}:multi:{tmux_session}"

            buttons.append([InlineKeyboardButton(text=display, callback_data=callback)])

        # Submit + Cancel
        buttons.append([
            InlineKeyboardButton(text="Submit", callback_data=f"ask:submit:{tmux_session}"),
            InlineKeyboardButton(text=strings.BTN_CANCEL_X, callback_data=f"ask:esc:{tmux_session}"),
        ])
    else:
        # Single-select: one button per row with label
        for opt in options:
            num = opt.split(".")[0].strip()
            label = opt.split(".", 1)[1].strip()[:20]

            is_type = "type" in label.lower()
            callback = f"ask:{num}:type:{tmux_session}" if is_type else f"ask:{num}:{tmux_session}"

            buttons.append([InlineKeyboardButton(text=label, callback_data=callback)])

        buttons.append([InlineKeyboardButton(
            text=strings.BTN_CANCEL_X,
            callback_data=f"ask:esc:{tmux_session}"
        )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
