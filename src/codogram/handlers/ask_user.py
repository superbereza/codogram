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

    # Cleanup messages
    await _cleanup_messages(callback)

    # Send key to tmux
    if action == "esc":
        logger.info(f"ask_user_callback: sending Escape to tmux={tmux_session}")
        tmux.send_key("Escape")
    else:
        logger.info(f"ask_user_callback: sending {action} to tmux={tmux_session}")
        tmux.send_key(action)

    await callback.answer()


async def _cleanup_messages(callback: CallbackQuery):
    """Delete content messages and keyboard."""
    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    # Delete content messages
    logger.debug(f"cleanup: kb_msg_id={kb_msg_id}, permission_messages keys={list(permission_messages.keys())}")
    content_ids = permission_messages.pop(kb_msg_id, [])
    logger.debug(f"cleanup: content_ids={content_ids}")
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
            logger.debug(f"cleanup: deleted content msg {msg_id}")
        except Exception as e:
            logger.warning(f"cleanup: failed to delete content msg {msg_id}: {e}")

    # Delete keyboard message
    try:
        await callback.message.delete()
        logger.debug(f"cleanup: deleted keyboard msg {kb_msg_id}")
    except Exception as e:
        logger.warning(f"cleanup: failed to delete keyboard msg {kb_msg_id}: {e}")
