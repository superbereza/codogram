"""AskUserQuestion callback handlers."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..core.session_manager import project_manager
from ..tmux.session import TmuxSession
from ..state import permission_messages
from ..logging_config import logger
from .. import strings

router = Router(name="ask_user")


def parse_ask_callback(data: str) -> dict | None:
    """Parse ask callback data.

    Formats:
    - ask:{num}:{tmux}           → single select
    - ask:{num}:type:{tmux}      → single select "type something"
    - ask:{num}:multi:{tmux}     → multi-select toggle
    - ask:{num}:multitype:{tmux} → multi-select "type something"
    - ask:submit:{tmux}          → submit multi-select
    - ask:esc:{tmux}             → cancel

    Returns dict with keys: action, tmux, is_multi, is_type, is_submit, is_esc
    """
    parts = data.split(":")
    if len(parts) < 3:
        return None

    action = parts[1]

    # Handle special actions
    if action == "esc":
        return {"action": "esc", "tmux": parts[2], "is_esc": True}
    if action == "submit":
        return {"action": "submit", "tmux": parts[2], "is_submit": True}

    # Parse option number callbacks
    if len(parts) == 3:
        # ask:{num}:{tmux} - single select
        return {"action": action, "tmux": parts[2], "is_multi": False, "is_type": False}
    elif len(parts) == 4:
        modifier = parts[2]
        tmux = parts[3]
        if modifier == "type":
            return {"action": action, "tmux": tmux, "is_multi": False, "is_type": True}
        elif modifier == "multi":
            return {"action": action, "tmux": tmux, "is_multi": True, "is_type": False}
        elif modifier == "multitype":
            return {"action": action, "tmux": tmux, "is_multi": True, "is_type": True}

    return None


@router.callback_query(F.data.startswith("ask:"))
async def on_ask_user_callback(callback: CallbackQuery):
    """Handle AskUserQuestion button press."""
    logger.info(f"ask_callback: data={callback.data}")

    parsed = parse_ask_callback(callback.data)
    if not parsed:
        logger.warning(f"ask_callback: invalid format data={callback.data}")
        await callback.answer("Invalid callback format")
        return

    tmux_session = parsed["tmux"]
    action = parsed["action"]

    # Find project
    project = project_manager.get_by_tmux(tmux_session)
    if not project or not project.cwd:
        logger.warning(f"ask_callback: project not found tmux={tmux_session}")
        await callback.answer("Session not found")
        return

    # Check tmux exists
    tmux = TmuxSession(tmux_session, project.cwd)
    if not tmux.exists():
        logger.warning(f"ask_callback: tmux closed tmux={tmux_session}")
        await callback.answer("Tmux session closed")
        return

    # Handle ESC
    if parsed.get("is_esc"):
        logger.info(f"ask_callback: ESC → tmux={tmux_session}")
        tmux.send_key("Escape")
        await _finish_interaction(callback, "✗ Cancelled")
        return

    # Handle Submit
    if parsed.get("is_submit"):
        logger.info(f"ask_callback: SUBMIT → tmux={tmux_session}")
        tmux.send_key("Enter")
        await _finish_interaction(callback, "✓ Submitted")
        return

    # Handle multi-select toggle (don't edit message, poller will update keyboard)
    if parsed.get("is_multi") and not parsed.get("is_type"):
        logger.info(f"ask_callback: MULTI_TOGGLE {action} → tmux={tmux_session}")
        tmux.send_key(action)
        await callback.answer()  # Just acknowledge, no edit
        return

    # Handle multi-select "type something" (toggle + show prompt)
    if parsed.get("is_multi") and parsed.get("is_type"):
        logger.info(f"ask_callback: MULTI_TYPE {action} → tmux={tmux_session}")
        tmux.send_key(action)
        await callback.answer(strings.ASK_USER_TYPE_PROMPT, show_alert=True)
        return

    # Handle single-select
    logger.info(f"ask_callback: SINGLE {action} → tmux={tmux_session}")
    tmux.send_key(action)

    if parsed.get("is_type"):
        await _finish_interaction(callback, f"✓ Selected: {action}\n{strings.ASK_USER_TYPE_PROMPT}")
    else:
        await _finish_interaction(callback, f"✓ Selected: {action}")


async def _finish_interaction(callback: CallbackQuery, text: str):
    """Edit message and clean up tracking."""
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception as e:
        logger.warning(f"ask_callback: edit failed: {e}")

    kb_msg_id = callback.message.message_id
    permission_messages.pop(kb_msg_id, None)
    await callback.answer()
