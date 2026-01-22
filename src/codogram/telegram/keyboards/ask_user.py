"""Inline keyboard for AskUserQuestion prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# Keywords that indicate "type your own answer" option
OTHER_KEYWORDS = ("type something", "other", "что-то другое", "другое")


def _is_other_option(label: str) -> bool:
    """Check if option is 'type something' / 'other'."""
    return any(kw in label.lower() for kw in OTHER_KEYWORDS)


def ask_user_keyboard(
    options: list[str],
    tmux_session: str,
    is_multi: bool = False,
    total: int = 0,
) -> InlineKeyboardMarkup:
    """Build keyboard for AskUserQuestion.

    Callback formats:
    - ask:{num}:{tmux} - single-select (sends num, finishes)
    - ask:other:{num}:{tmux} - single-select "type something" option
    - ask:{num}:{total}:{tmux} - multi-select toggle (sends num, updates checkboxes)
    - ask:submit:{tmux} - submit multi-select
    - ask:esc:{tmux} - cancel
    """
    buttons = []

    for opt in options:
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip() if "." in opt else opt
        display_label = label[:25]

        if is_multi:
            callback = f"ask:{num}:{total}:{tmux_session}"
        elif _is_other_option(label):
            callback = f"ask:other:{num}:{tmux_session}"
        else:
            callback = f"ask:{num}:{tmux_session}"

        buttons.append([InlineKeyboardButton(text=f"{num}. {display_label}", callback_data=callback)])

    # Footer row: Cancel left, Submit right
    if is_multi:
        buttons.append([
            InlineKeyboardButton(text="Cancel", callback_data=f"ask:esc:{tmux_session}"),
            InlineKeyboardButton(text="Submit", callback_data=f"ask:submit:{tmux_session}"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="Cancel", callback_data=f"ask:esc:{tmux_session}")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
