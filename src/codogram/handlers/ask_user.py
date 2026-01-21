"""AskUserQuestion callback handlers."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..core.session_manager import project_manager
from ..tmux.session import TmuxSession
from ..state import permission_messages
from ..logging_config import logger

router = Router(name="ask_user")


@router.callback_query(F.data.startswith("ask:"))
async def on_ask_user_callback(callback: CallbackQuery):
    """Handle AskUserQuestion button press.

    Note: Admin check done by global AdminMiddleware on dp level.
    """
    logger.info(f"ask_user_callback: data={callback.data} from user={callback.from_user.id}")

    # Parse callback data: ask:{action}:{tmux_session}
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        logger.warning(f"ask_user_callback: invalid format data={callback.data}")
        await callback.answer("Invalid callback format")
        return

    action = parts[1]
    tmux_session = parts[2]
    logger.debug(f"ask_user_callback: action={action} tmux={tmux_session}")

    # Find project
    project = project_manager.get_by_tmux(tmux_session)
    if not project:
        logger.warning(f"ask_user_callback: project not found for tmux={tmux_session}")
        await callback.answer("Session not found")
        return

    if not project.cwd:
        logger.warning(f"ask_user_callback: project has no cwd tmux={tmux_session}")
        await callback.answer("Project has no cwd")
        return

    # Check tmux exists
    tmux = TmuxSession(tmux_session, project.cwd)
    if not tmux.exists():
        logger.warning(f"ask_user_callback: tmux session closed tmux={tmux_session}")
        await callback.answer("Tmux session closed")
        return

    # Send key to tmux
    if action == "esc":
        logger.info(f"ask_user_callback: sending Escape to tmux={tmux_session}")
        tmux.send_key("Escape")
        selected_text = "✗ Cancelled"
    else:
        logger.info(f"ask_user_callback: sending {action} to tmux={tmux_session}")
        tmux.send_key(action)
        selected_text = f"✓ Selected: {action}"

    # Edit message to show selection (keep history, remove keyboard)
    try:
        await callback.message.edit_text(selected_text)
        logger.debug(f"ask_user_callback: edited message to show selection")
    except Exception as e:
        logger.warning(f"ask_user_callback: failed to edit message: {e}")

    # Remove from permission_messages tracking
    kb_msg_id = callback.message.message_id
    permission_messages.pop(kb_msg_id, None)

    await callback.answer()
