"""Unified /new_chat command for creating topics with Claude sessions.

Complete flow:
1. Show context (directory/branch) + choice (here/isolated)
2. If isolated + uncommitted: show uncommitted options
3. Show name prompt
4. Create thread or branch
"""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..config import settings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import (
    require_forum_group,
    require_claude_ready,
    set_flow_state,
    get_flow_state,
    clear_flow_state,
)
from ..domain.worktree_state import WorktreeState, get_worktree_state
from ..services.create_flow import create_flow_service
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..git_utils import (
    is_git_repo,
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
)
from ..tmux import TmuxSession

router = Router(name="new_chat")


def _relative_to_base(path: str) -> str:
    """Make path relative to base_dir for display."""
    try:
        base = Path(settings.base_dir).resolve()
        full = Path(path).resolve()
        if full.is_relative_to(base):
            return "./" + str(full.relative_to(base))
    except (ValueError, RuntimeError):
        pass
    return path


# ===== Keyboards =====

def _context_keyboard(has_git: bool) -> InlineKeyboardMarkup:
    """Build keyboard for context step."""
    if has_git:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=strings.BTN_CREATE_ISOLATED, callback_data="nc_isolated")],
            [InlineKeyboardButton(text=strings.BTN_CREATE_HERE, callback_data="nc_here")],
            [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="nc_cancel")],
        ])
    else:
        # No git - only "create here" option, go straight to name
        return None


def _name_keyboard(create_type: str) -> InlineKeyboardMarkup:
    """Build keyboard for name prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_MY_NAME, callback_data=f"nc_myname:{create_type}")],
        [InlineKeyboardButton(text=strings.BTN_MAGIC_NAME, callback_data="nc_magic")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data=f"nc_back:{create_type}")],
    ])


def _name_fallback_keyboard(create_type: str) -> InlineKeyboardMarkup:
    """Build keyboard for when name couldn't be retrieved."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_MAGIC_NAME, callback_data="nc_magic")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data=f"nc_back:{create_type}")],
    ])


def _uncommitted_keyboard(name: str) -> InlineKeyboardMarkup:
    """Build keyboard for uncommitted changes."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.NC_UNCOMMITTED_CLEAN,
            callback_data=f"nc_uncommitted_clean:{name}"
        )],
        [InlineKeyboardButton(
            text=strings.NC_UNCOMMITTED_COMMIT,
            callback_data=f"nc_uncommitted_commit:{name}"
        )],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="nc_cancel")],
    ])


# ===== Main command =====

@router.message(Command("new_chat", "nc", ignore_case=True))
async def cmd_new_chat(message: Message, telegram_queue: TelegramQueue):
    """Create a new chat (topic + Claude session)."""
    if not await require_forum_group(message, telegram_queue):
        return
    if not await require_claude_ready(message, telegram_queue):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    # Determine current context (directory and branch)
    current_thread = project.threads.get(thread_id)
    directory = project.cwd
    branch = get_default_branch(Path(project.cwd)) if is_git_repo(Path(project.cwd)) else "main"

    if current_thread and current_thread.worktree_path:
        state = get_worktree_state(current_thread, Path(project.cwd))
        if state == WorktreeState.OK:
            directory = current_thread.worktree_path
            branch = current_thread.name

    # Check if git repo exists (for isolated option)
    has_git = is_git_repo(Path(project.cwd))

    if not has_git:
        # No git - skip to name prompt directly
        prompt_ids = await telegram_queue.reply(
            message,
            strings.NEW_CHAT_NAME_PROMPT,
            reply_markup=_name_keyboard("thread"),
        )
        set_flow_state(chat_id, thread_id, {
            "type": "nc_awaiting_name",
            "create_type": "thread",
            "prompt_message_id": prompt_ids[0] if prompt_ids else None,
        })
        return

    # Show context + choice
    display_dir = _relative_to_base(directory)
    if branch == get_default_branch(Path(project.cwd)):
        context_text = strings.NEW_CHAT_CONTEXT_MAIN.format(directory=display_dir, branch=branch)
    else:
        context_text = strings.NEW_CHAT_CONTEXT.format(directory=display_dir, branch=branch)

    set_flow_state(chat_id, thread_id, {
        "type": "nc_context",
        "directory": directory,
        "branch": branch,
    })

    await telegram_queue.reply(
        message,
        f"{context_text}\n\n{strings.NEW_CHAT_CHOOSE}",
        reply_markup=_context_keyboard(has_git),
    )


# ===== Step 1 callbacks: Create here vs Isolated =====

@router.callback_query(F.data == "nc_here")
async def on_nc_here(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create chat in current directory (thread)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    # Show name prompt
    await telegram_queue.edit(
        callback.message,
        strings.NEW_CHAT_NAME_PROMPT,
        reply_markup=_name_keyboard("thread"),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "nc_awaiting_name",
        "create_type": "thread",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_isolated")
async def on_nc_isolated(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create isolated branch."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    # Show name prompt for branch
    await telegram_queue.edit(
        callback.message,
        strings.NEW_CHAT_NAME_PROMPT,
        reply_markup=_name_keyboard("branch"),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "nc_awaiting_name",
        "create_type": "branch",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_cancel")
async def on_nc_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Cancel new chat creation."""
    clear_flow_state(callback.message.chat.id, callback.message.message_thread_id)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("nc_back:"))
async def on_nc_back(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Go back from name prompt to context selection."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    # Check if git repo - if not, just cancel (no context to go back to)
    if not is_git_repo(Path(project.cwd)):
        await callback.message.delete()
        await callback.answer()
        return

    # Determine current context
    current_thread = project.threads.get(thread_id)
    directory = project.cwd
    branch = get_default_branch(Path(project.cwd))

    if current_thread and current_thread.worktree_path:
        state = get_worktree_state(current_thread, Path(project.cwd))
        if state == WorktreeState.OK:
            directory = current_thread.worktree_path
            branch = current_thread.name

    # Show context + choice
    display_dir = _relative_to_base(directory)
    if branch == get_default_branch(Path(project.cwd)):
        context_text = strings.NEW_CHAT_CONTEXT_MAIN.format(directory=display_dir, branch=branch)
    else:
        context_text = strings.NEW_CHAT_CONTEXT.format(directory=display_dir, branch=branch)

    set_flow_state(chat_id, thread_id, {
        "type": "nc_context",
        "directory": directory,
        "branch": branch,
    })

    await telegram_queue.edit(
        callback.message,
        f"{context_text}\n\n{strings.NEW_CHAT_CHOOSE}",
        reply_markup=_context_keyboard(True),
    )
    await callback.answer()


# ===== Step 2/3: Name handling =====

@router.callback_query(F.data.startswith("nc_myname:"))
async def on_nc_myname(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Use user's first name."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    create_type = callback.data.split(":", 1)[1]  # thread or branch

    # Get first_name
    first_name = callback.from_user.first_name if callback.from_user else None
    if not first_name:
        # Show fallback message
        await telegram_queue.edit(
            callback.message,
            strings.NEW_CHAT_NAME_NO_NAME,
            reply_markup=_name_fallback_keyboard(create_type),
        )
        await callback.answer()
        return

    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    name, error = create_flow_service.validate_name(first_name, project)
    if error:
        await telegram_queue.edit(callback.message, error)
        await callback.answer()
        return

    # For branch: check uncommitted first
    if create_type == "branch":
        if has_uncommitted_changes(Path(project.cwd)):
            await telegram_queue.edit(
                callback.message,
                strings.NC_UNCOMMITTED,
                reply_markup=_uncommitted_keyboard(name),
            )
            await callback.answer()
            return

    # Create directly
    await telegram_queue.edit(callback.message, strings.NEW_CHAT_CREATING.format(name=name))
    await callback.answer()

    await _do_create(callback.bot, chat_id, thread_id, project, name, create_type, telegram_queue)


@router.callback_query(F.data == "nc_magic")
async def on_nc_magic(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Generate magic name and create."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "nc_awaiting_name":
        await callback.answer(strings.SESSION_EXPIRED)
        return

    create_type = state.get("create_type")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    name = create_flow_service.get_magic_name(project)

    # For branch: check uncommitted first
    if create_type == "branch":
        if has_uncommitted_changes(Path(project.cwd)):
            await telegram_queue.edit(
                callback.message,
                strings.NC_UNCOMMITTED,
                reply_markup=_uncommitted_keyboard(name),
            )
            await callback.answer()
            return

    # Create directly
    await telegram_queue.edit(callback.message, strings.NEW_CHAT_CREATING.format(name=name))
    await callback.answer()

    await _do_create(callback.bot, chat_id, thread_id, project, name, create_type, telegram_queue)


async def handle_name_input(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Handle text message as name input. Returns True if handled."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "nc_awaiting_name":
        return False

    create_type = state.get("create_type")
    prompt_message_id = state.get("prompt_message_id")
    clear_flow_state(chat_id, thread_id)

    # Delete the prompt
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id, prompt_message_id)
        except Exception:
            pass

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_FOUND)
        return True

    name, error = create_flow_service.validate_name(message.text.strip(), project)
    if error:
        await telegram_queue.reply(message, error)
        return True

    # For branch: check preconditions
    if create_type == "branch":
        can_create, err, warning = create_flow_service.check_branch_preconditions(project, name)
        if err:
            await telegram_queue.reply(message, err)
            return True
        if warning:
            # Uncommitted changes
            await telegram_queue.reply(
                message,
                strings.NC_UNCOMMITTED,
                reply_markup=_uncommitted_keyboard(name),
            )
            return True

    # Create
    await telegram_queue.reply(message, strings.NEW_CHAT_CREATING.format(name=name))
    await _do_create(message.bot, chat_id, thread_id, project, name, create_type, telegram_queue)
    return True


# ===== Uncommitted changes callbacks =====

@router.callback_query(F.data.startswith("nc_uncommitted_clean:"))
async def on_nc_uncommitted_clean(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create from last commit (ignore uncommitted)."""
    name = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    await telegram_queue.edit(callback.message, strings.NEW_CHAT_CREATING.format(name=name))
    await callback.answer()

    await _do_create(callback.bot, chat_id, thread_id, project, name, "branch", telegram_queue)


@router.callback_query(F.data.startswith("nc_uncommitted_commit:"))
async def on_nc_uncommitted_commit(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Ask Claude to commit first."""
    name = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    # Find current thread's tmux
    current_thread = project.threads.get(thread_id)
    if current_thread:
        tmux_name = current_thread.get_tmux_session(project.project_name)
        cwd = current_thread.worktree_path or project.cwd
        tmux = TmuxSession(tmux_name, cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        strings.BRANCH_COMMIT_SENT.format(branch_name=name),
    )
    await callback.answer()


# ===== Creation logic =====

async def _do_create(bot, chat_id: int, thread_id: int | None, project, name: str, create_type: str, telegram_queue: TelegramQueue):
    """Actually create the thread or branch."""
    if create_type == "branch":
        default_branch = get_default_branch(Path(project.cwd))
        result = await do_branch_create(bot, chat_id, project, name, default_branch)
    else:
        result = await create_thread_with_session(
            bot=bot,
            chat_id=chat_id,
            project=project,
            name=name,
        )

    if result.success:
        await telegram_queue.send(chat_id, strings.NEW_CHAT_CREATED.format(name=name), thread_id=thread_id)
    else:
        error_msg = result.error or strings.NEW_CHAT_ERROR
        await telegram_queue.send(chat_id, error_msg, thread_id=thread_id, parse_mode="MarkdownV2")
