"""Branch management: git worktrees + threads."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_forum_group, clear_flow_state
from ..services.branch import do_branch_create
from ..magic_names import get_random_magic_name
from ..git_utils import (
    is_git_repo,
    sanitize_branch_name,
    max_branch_name_length,
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
)
from ..tmux import TmuxSession

router = Router(name="branches")


@router.message(Command("branch"))
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /branch_create."""
    await cmd_branch_create(message, telegram_queue)


# ===== /branch_create =====

@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    # Check git repo
    if not is_git_repo(Path(project.cwd)):
        await telegram_queue.reply(message, "`[x]` Git repository required for /branch_create")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # Generate magic name if not provided
    if not branch_name:
        existing_names = {t.name for t in project.threads.values()}
        branch_name = get_random_magic_name(existing_names)

    # Sanitize branch name
    branch_name = sanitize_branch_name(branch_name)

    # Check length
    max_len = max_branch_name_length(project.project_name)
    if len(branch_name) > max_len:
        await telegram_queue.reply(message, f"`[x]` Name too long (max {max_len} chars for this project)")
        return

    # Check if branch already exists
    if branch_exists(Path(project.cwd), branch_name):
        await telegram_queue.reply(message, f"`[x]` Branch `{branch_name}` already exists")
        return

    # Check if worktree directory already exists
    main_repo = Path(project.cwd)
    worktree_dir = main_repo.parent / f"{main_repo.name}-{branch_name}"
    if worktree_dir.exists():
        await telegram_queue.reply(message, f"`[x]` Directory already exists: `{worktree_dir}`")
        return

    # Get default branch
    default_branch = get_default_branch(Path(project.cwd))

    # Check if creating from worktree topic or main
    current_thread = project.threads.get(message.message_thread_id)
    if current_thread and current_thread.worktree_path:
        # From worktree topic - show base branch selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"From {default_branch}", callback_data=f"bc_base:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text=f"From {current_thread.name}", callback_data=f"bc_base:{branch_name}:{current_thread.name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, "Create branch from:", reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, "`[!]` Uncommitted changes detected", reply_markup=keyboard)
        return

    # No uncommitted changes - create directly
    await do_branch_create(message.bot, message.chat.id, project, branch_name, default_branch)


@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle base branch selection for branch_create."""
    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
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
        await telegram_queue.edit(callback.message, f"`[!]` Uncommitted changes in {base_branch}", reply_markup=keyboard)
        return

    await callback.message.delete()
    await do_branch_create(callback.bot, callback.message.chat.id, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create branch from last commit."""
    _, branch_name, base_branch = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    await callback.message.delete()
    await do_branch_create(callback.bot, callback.message.chat.id, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_commit:"))
async def on_branch_commit_request(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Send commit request to Claude."""
    _, branch_name = callback.data.split(":")
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(callback.message.message_thread_id)

    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        "`[~]` Sent: \"Commit current changes in logical chunks with descriptive messages.\"\n\n"
        f"Run `/branch_create {branch_name}` again after commit.",
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


@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish."""
    await telegram_queue.reply(message, "`[i]` Use /finish to complete branches")
