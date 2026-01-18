"""Keyboards for create flow."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..domain.create_flow import CreateType
from .. import strings

# Callback data constants
CALLBACK_MAGIC_PREFIX = "create_magic:"
CALLBACK_CANCEL = "create_cancel"


def build_name_prompt_keyboard(create_type: CreateType) -> InlineKeyboardMarkup:
    """Build keyboard for name prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_MAGIC_NAME,
            callback_data=f"{CALLBACK_MAGIC_PREFIX}{create_type.value}"
        )],
        [InlineKeyboardButton(
            text=strings.BTN_GO_BACK,
            callback_data=CALLBACK_CANCEL
        )],
    ])
