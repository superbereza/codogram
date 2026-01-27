"""Permission handlers - Yes/No/Esc buttons for Claude prompts."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..core.session_manager import project_manager
from ..tmux.session import TmuxSession
from ..state import permission_states, PermissionPromptState
from ..chunker import _split_text
from ..telegram.queue import TelegramQueue
from ..logging_config import logger

router = Router(name="permissions")

PERMISSION_PAGE_SIZE = 500


def _build_permission_text(state: PermissionPromptState) -> str:
    """Build permission prompt message text from state."""
    # Header from first line of body
    header = state.body.split("\n")[0][:60] if state.body else "Permission request"

    if not state.expanded:
        # Collapsed: header + hint + options
        lines = [header, "click `Show more` to expand", ""]
        lines.extend(state.options)
        return "\n".join(lines)

    # Expanded: body only (no header duplication)
    lines = ["────────────"]

    is_last_page = True
    if state.chunks:
        total = len(state.chunks)
        is_last_page = state.current_page == total - 1
        if total > 1:
            lines.append(f"[{state.current_page + 1}/{total}]\n{state.chunks[state.current_page]}")
        else:
            lines.append(state.chunks[state.current_page])

    lines.append("────────────")

    # Options only on last page
    if is_last_page:
        lines.append("")
        lines.extend(state.options)

    return "\n".join(lines)


async def _update_permission_message(
    callback: CallbackQuery,
    state: PermissionPromptState,
    telegram_queue: TelegramQueue,
) -> None:
    """Update permission message with new state."""
    from ..telegram.keyboards import permission_keyboard

    text = _build_permission_text(state)

    total_pages = len(state.chunks) if state.chunks else 1
    kb = permission_keyboard(
        state.options,
        state.tmux_name,
        expanded=state.expanded,
        current_page=state.current_page,
        total_pages=total_pages,
    )

    await telegram_queue.edit(callback.message, text, reply_markup=kb)


@router.callback_query(F.data.startswith("perm:"))
async def callback_permission(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle permission button presses."""
    logger.info(f"permission_callback: data={callback.data} from user={callback.from_user.id}")

    parts = callback.data.split(":")
    if len(parts) < 3:
        logger.warning(f"permission_callback: invalid format data={callback.data}")
        await callback.answer("Invalid callback")
        return

    tmux_name = parts[1]
    action = parts[2]
    logger.debug(f"permission_callback: action={action} tmux={tmux_name}")

    # Find state by message_id
    msg_id = callback.message.message_id
    state = permission_states.get(msg_id)

    if not state:
        # Stale prompt (bot restarted or message expired)
        logger.warning(f"permission_callback: state not found for msg_id={msg_id}")
        await callback.message.delete()
        await callback.answer("Prompt expired")
        return

    # Verify tmux_name matches
    if state.tmux_name != tmux_name:
        logger.warning(f"permission_callback: tmux mismatch state={state.tmux_name} callback={tmux_name}")
        await callback.message.delete()
        await callback.answer("Stale prompt")
        return

    if action == "expand":
        state.expanded = True
        state.current_page = 0
        # Compute chunks if not already
        if not state.chunks and state.body:
            state.chunks = _split_text(state.body, max_len=PERMISSION_PAGE_SIZE)
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    elif action == "collapse":
        state.expanded = False
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    elif action == "page":
        if len(parts) < 4:
            await callback.answer("Invalid page")
            return
        try:
            page_num = int(parts[3])
        except ValueError:
            await callback.answer("Invalid page number")
            return
        max_page = len(state.chunks) - 1 if state.chunks else 0
        if page_num < 0 or page_num > max_page:
            await callback.answer("Invalid page")
            return
        state.current_page = page_num
        await _update_permission_message(callback, state, telegram_queue)
        await callback.answer()

    elif action == "noop":
        # Placeholder button - do nothing
        await callback.answer()
        return

    elif action == "esc":
        # Cancel - send Escape key
        project = project_manager.get_by_tmux(tmux_name)
        if project and project.cwd:
            tmux = TmuxSession(tmux_name, project.cwd)
            if tmux.exists():
                tmux.send_key("Escape")
                logger.info(f"permission_callback: sent Escape to tmux={tmux_name}")
        permission_states.pop(msg_id, None)
        await callback.message.delete()
        await callback.answer()

    else:
        # Option selection (1, 2, 3, etc.) - send key to tmux
        try:
            option_num = int(action)
            project = project_manager.get_by_tmux(tmux_name)
            if project and project.cwd:
                tmux = TmuxSession(tmux_name, project.cwd)
                if tmux.exists():
                    # Send the option number as key
                    tmux.send_key(str(option_num))
                    logger.info(f"permission_callback: sent key={option_num} to tmux={tmux_name}")

            # Cleanup
            permission_states.pop(msg_id, None)
            await callback.message.delete()
            await callback.answer()
        except ValueError:
            logger.warning(f"permission_callback: invalid option action={action}")
            await callback.answer("Invalid option")
