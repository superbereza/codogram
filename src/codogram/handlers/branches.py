"""Branch management: git worktrees + threads."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group, require_claude_ready, clear_flow_state, set_flow_state
from ..services.branch import do_branch_create
from ..services.create_flow import create_flow_service
from ..domain.create_flow import CreateType
from ..domain.worktree_state import WorktreeState, get_worktree_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..git_utils import (
    is_git_repo,
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
)
from ..tmux import TmuxSession

router = Router(name="branches")


@router.message(Command("branch", ignore_case=True))
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /branch_create."""
    await cmd_branch_create(message, telegram_queue)


# ===== /branch_create =====

@router.message(Command("branch_create", ignore_case=True))
async def cmd_branch_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return
    if not await require_claude_ready(message, telegram_queue):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, strings.BRANCH_PROJECT_NOT_REGISTERED)
        return

    # Check git repo
    if not is_git_repo(Path(project.cwd)):
        await telegram_queue.reply(message, strings.BRANCH_GIT_REQUIRED)
        return

    # Check for stale worktree early (before name prompt)
    current_thread = project.threads.get(message.message_thread_id)
    stale_worktree = False
    if current_thread and current_thread.worktree_path:
        state = get_worktree_state(current_thread, Path(project.cwd))
        if state != WorktreeState.OK:
            stale_worktree = True

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # Get default branch for messages
    default_branch = get_default_branch(Path(project.cwd))

    # Show name prompt if not provided
    if create_flow_service.should_show_prompt(branch_name):
        if stale_worktree:
            # Show warning with name prompt
            prompt_ids = await telegram_queue.reply(
                message,
                strings.BRANCH_WORKTREE_NOT_FOUND_BASE.format(default_branch=default_branch),
                reply_markup=build_name_prompt_keyboard(CreateType.BRANCH),
            )
        else:
            prompt_ids = await telegram_queue.reply(
                message,
                "Branch name?\n\nSend name or pick random",
                reply_markup=build_name_prompt_keyboard(CreateType.BRANCH),
            )
        # Save state with prompt message_id for cleanup
        set_flow_state(message.chat.id, message.message_thread_id, {
            "type": "awaiting_create_name",
            "create_type": "branch",
            "prompt_message_id": prompt_ids[0] if prompt_ids else None,
        })
        return

    # Validate and sanitize name
    branch_name, error = create_flow_service.validate_name(branch_name, project)
    if error:
        await telegram_queue.reply(message, error)
        return

    # Check if branch already exists
    if branch_exists(Path(project.cwd), branch_name):
        await telegram_queue.reply(message, strings.BRANCH_ALREADY_EXISTS.format(name=branch_name))
        return

    # Check if worktree directory already exists
    main_repo = Path(project.cwd)
    worktree_dir = main_repo.parent / f"{main_repo.name}-{branch_name}"
    if worktree_dir.exists():
        await telegram_queue.reply(message, strings.BRANCH_DIR_EXISTS.format(path=worktree_dir))
        return

    # Check if creating from worktree topic or main
    if current_thread and current_thread.worktree_path and not stale_worktree:
        # From healthy worktree topic - show base branch selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"From {default_branch}", callback_data=f"bc_base:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text=f"From {current_thread.name}", callback_data=f"bc_base:{branch_name}:{current_thread.name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, strings.BRANCH_CREATE_FROM_PROMPT, reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, strings.BRANCH_UNCOMMITTED_CHANGES, reply_markup=keyboard)
        return

    # No uncommitted changes - create directly
    await do_branch_create(message.bot, message.chat.id, project, branch_name, default_branch)


@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle base branch selection for branch_create."""
    _, branch_name, base_branch = callback.data.split(":")
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    # Check uncommitted in selected base
    base_path = project.cwd
    if base_branch != get_default_branch(Path(project.cwd)):
        # Find worktree path for this branch
        for t in project.threads.values():
            if t.name == base_branch and t.worktree_path:
                base_path = t.worktree_path
                break

    if has_uncommitted_changes(Path(base_path)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create from last commit", callback_data=f"bc_create:{branch_name}:{base_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.edit(
            callback.message,
            strings.BRANCH_UNCOMMITTED_IN_BASE.format(base_branch=base_branch),
            reply_markup=keyboard,
        )
        return

    # 1. Remove buttons (edit)
    await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
    await callback.answer()

    # 2. Create branch
    await do_branch_create(callback.bot, chat_id, project, branch_name, base_branch)

    # 3. Final status (send)
    await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)


@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create branch from last commit."""
    _, branch_name, base_branch = callback.data.split(":")
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    # 1. Remove buttons (edit)
    await telegram_queue.edit(callback.message, strings.BRANCH_CREATING.format(name=branch_name))
    await callback.answer()

    # 2. Create branch
    await do_branch_create(callback.bot, chat_id, project, branch_name, base_branch)

    # 3. Final status (send)
    await telegram_queue.send(chat_id, strings.BRANCH_CREATED.format(name=branch_name), thread_id=thread_id)


@router.callback_query(F.data.startswith("bc_commit:"))
async def on_branch_commit_request(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Send commit request to Claude."""
    _, branch_name = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer(strings.BRANCH_PROJECT_NOT_FOUND_TOAST)
        return

    thread = project.threads.get(callback.message.message_thread_id)

    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        strings.BRANCH_COMMIT_SENT.format(branch_name=branch_name),
    )
    await callback.answer()


@router.callback_query(F.data == "branch_create_redirect")
async def on_branch_redirect(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle redirect to /branch_create."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    await telegram_queue.edit(
        callback.message,
        "Use `/branch_create` or `/branch_create <name>` to create isolated worktree branch.",
    )
    await callback.answer()


@router.message(Command("branch_finish", ignore_case=True))
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, strings.BRANCH_FINISH_USE_FINISH)
