# src/codogram/keyboards/setup/folder_select.py
"""Folder selection keyboard with pagination."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings

FOLDERS_PER_PAGE = 10


def folder_select_keyboard(
    folders: list[str],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Create folder selection keyboard with pagination.

    Args:
        folders: Folder names for current page
        page: Current page (0-indexed)
        total_pages: Total number of pages
    """
    rows = []

    # Folder buttons (one per row for readability)
    for folder in folders:
        # Truncate long names
        display_name = folder if len(folder) <= 30 else folder[:27] + "..."
        rows.append([
            InlineKeyboardButton(
                text=display_name,
                callback_data=f"folder:select:{folder}",
            )
        ])

    # Pagination row (if needed)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="<",
                callback_data=f"folder:page:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop",  # non-interactive
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text=">",
                callback_data=f"folder:page:{page + 1}",
            ))
        rows.append(nav_row)

    # View connected button
    rows.append([
        InlineKeyboardButton(
            text=strings.BTN_VIEW_CONNECTED,
            callback_data="folder:view_connected",
        )
    ])

    # Go back button
    rows.append([
        InlineKeyboardButton(
            text=strings.BTN_GO_BACK,
            callback_data="folder:back",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def connected_projects_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for view connected projects screen."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_BACK_TO_FOLDERS,
            callback_data="folder:back_connected",
        )]
    ])
