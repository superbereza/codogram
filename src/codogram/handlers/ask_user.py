"""AskUserQuestion callback handlers."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..core.session_manager import project_manager
from ..tmux.session import TmuxSession
from ..state import permission_messages, ask_options_state, active_ask_prompts
from ..logging_config import logger

router = Router(name="ask_user")


@router.callback_query(F.data.startswith("ask:"))
async def on_ask_callback(callback: CallbackQuery):
    """Handle AskUserQuestion button press.

    Formats:
    - ask:{num}:{tmux} - single-select
    - ask:{num}:{total}:{tmux} - multi-select toggle
    - ask:submit:{tmux} - submit
    - ask:esc:{tmux} - cancel
    """
    data = callback.data
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid")
        return

    action = parts[1]

    # Handle submit/esc
    if action == "submit":
        tmux_name = parts[2]
        return await _handle_submit(callback, tmux_name)
    if action == "esc":
        tmux_name = parts[2]
        return await _handle_esc(callback, tmux_name)
    if action == "other":
        # ask:other:{num}:{tmux} - "type something" option
        num = parts[2]
        tmux_name = parts[3]
        return await _handle_other_select(callback, num, tmux_name)

    # Handle option selection
    num = action
    if len(parts) == 4:
        # Multi-select: ask:{num}:{total}:{tmux}
        total = int(parts[2])
        tmux_name = parts[3]
        return await _handle_multi_toggle(callback, num, total, tmux_name)
    else:
        # Single-select: ask:{num}:{tmux}
        tmux_name = parts[2]
        return await _handle_single_select(callback, num, tmux_name)


async def _handle_single_select(callback: CallbackQuery, num: str, tmux_name: str):
    """Single-select: send number, finish."""
    logger.info(f"ask: single {num} → {tmux_name}")

    tmux = _get_tmux(tmux_name)
    if not tmux:
        await callback.answer("Session not found")
        return

    tmux.send_key(num)
    await _finish(callback, f"✓ Selected: {num}")


async def _handle_other_select(callback: CallbackQuery, num: str, tmux_name: str):
    """Handle 'Type something' option: send number, prompt for text input."""
    logger.info(f"ask: other {num} → {tmux_name}")

    tmux = _get_tmux(tmux_name)
    if not tmux:
        await callback.answer("Session not found")
        return

    tmux.send_key(num)
    await _finish(callback, "✏️ Type your answer")


async def _handle_multi_toggle(callback: CallbackQuery, num: str, total: int, tmux_name: str):
    """Multi-select toggle: update checkboxes in Telegram only (no tmux until Submit)."""
    logger.info(f"ask: multi toggle {num} (total={total}) → {tmux_name}")

    kb_msg_id = callback.message.message_id
    state = ask_options_state.get(kb_msg_id)
    related_ids = permission_messages.get(kb_msg_id, [])

    if not state or not related_ids:
        await callback.answer("State not found")
        return

    # Toggle the checked state in memory
    state["checked"][num] = not state["checked"].get(num, False)

    # Rebuild options text
    lines = []
    for opt in state["options"]:
        mark = "✓" if state["checked"].get(opt["num"], False) else "☐"
        lines.append(f"{mark} {opt['num']}. {opt['label']}")
    new_text = "\n".join(lines)

    # Edit the options message (last in related_ids)
    options_msg_id = related_ids[-1]
    try:
        await callback.bot.edit_message_text(
            text=new_text,
            chat_id=callback.message.chat.id,
            message_id=options_msg_id,
        )
    except Exception as e:
        logger.warning(f"ask: edit options failed: {e}")

    await callback.answer(f"✓ {num}" if state["checked"][num] else f"☐ {num}")


async def _handle_submit(callback: CallbackQuery, tmux_name: str):
    """Submit: send toggles for changed options, then Enter."""
    logger.info(f"ask: submit → {tmux_name}")

    tmux = _get_tmux(tmux_name)
    if not tmux:
        await callback.answer("Session not found")
        return

    kb_msg_id = callback.message.message_id
    state = ask_options_state.get(kb_msg_id)

    selected_labels = []
    if state and "initial" in state:
        # Find options that changed from initial state
        total = state.get("total", len(state["options"]))
        changed = []
        for opt in state["options"]:
            num = opt["num"]
            if state["checked"].get(num) != state["initial"].get(num):
                changed.append(int(num))
            # Collect selected labels for finish message
            if state["checked"].get(num):
                selected_labels.append(opt["label"])

        logger.info(f"ask: submit changed={changed} total={total}")

        # Cursor starts at option 1
        # Toggle each changed option (sorted so we go down sequentially)
        current_pos = 1
        for option_num in sorted(changed):
            # Go down to target option
            downs = option_num - current_pos
            for _ in range(downs):
                tmux.send_key("Down")
            # Toggle
            tmux.send_key("Enter")
            current_pos = option_num

        # Go to Submit (after last option)
        downs_to_submit = total + 1 - current_pos
        for _ in range(downs_to_submit):
            tmux.send_key("Down")

    # Submit
    tmux.send_key("Enter")

    # Build finish message with selected options
    if selected_labels:
        finish_text = "✓ Submitted:\n• " + "\n• ".join(selected_labels)
    else:
        finish_text = "✓ Submitted (none selected)"
    await _finish(callback, finish_text)


async def _handle_esc(callback: CallbackQuery, tmux_name: str):
    """Cancel: send Escape, delete all messages."""
    logger.info(f"ask: esc → {tmux_name}")

    tmux = _get_tmux(tmux_name)
    if not tmux:
        await callback.answer("Session not found")
        return

    tmux.send_key("Escape")
    await _finish_delete(callback)


def _get_tmux(tmux_name: str) -> TmuxSession | None:
    """Get TmuxSession if exists."""
    project = project_manager.get_by_tmux(tmux_name)
    if not project or not project.cwd:
        return None
    tmux = TmuxSession(tmux_name, project.cwd)
    if not tmux.exists():
        return None
    return tmux


async def _finish(callback: CallbackQuery, text: str):
    """Finish interaction - edit message, remove from tracking."""
    kb_msg_id = callback.message.message_id
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    permission_messages.pop(kb_msg_id, None)
    ask_options_state.pop(kb_msg_id, None)
    active_ask_prompts.pop((chat_id, thread_id), None)

    try:
        await callback.message.edit_text(text, reply_markup=None)
    except Exception as e:
        logger.warning(f"ask: edit failed: {e}")

    await callback.answer()


async def _finish_delete(callback: CallbackQuery):
    """Finish interaction - delete all messages, remove from tracking."""
    kb_msg_id = callback.message.message_id
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    # Get related message IDs and clean up state
    related_ids = permission_messages.pop(kb_msg_id, [])
    ask_options_state.pop(kb_msg_id, None)
    active_ask_prompts.pop((chat_id, thread_id), None)

    # Delete all related messages
    for msg_id in related_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"ask: delete failed: {e}")

    await callback.answer()
