"""Branch management: git worktrees + threads."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from .common import require_forum_group, _flow_state
from ..services.branch import do_branch_create, do_branch_cleanup
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
from ..worktree import merge_branch, push_branch

router = Router(name="branches")


# ===== /branch_create =====

@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("`[!]` Project not registered. Use /start first.", parse_mode="Markdown")
        return

    # Check git repo
    if not is_git_repo(Path(project.cwd)):
        await message.answer("`[x]` Git repository required for /branch_create", parse_mode="Markdown")
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
        await message.answer(f"`[x]` Name too long (max {max_len} chars for this project)", parse_mode="Markdown")
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
        await message.answer("Create branch from:", reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await message.answer("`[!]` Uncommitted changes detected", reply_markup=keyboard, parse_mode="Markdown")
        return

    # No uncommitted changes - create directly
    await do_branch_create(message.bot, message.chat.id, project, branch_name, default_branch)


@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery):
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
        await callback.message.edit_text(f"`[!]` Uncommitted changes in {base_branch}", reply_markup=keyboard, parse_mode="Markdown")
        return

    await callback.message.delete()
    await do_branch_create(callback.bot, callback.message.chat.id, project, branch_name, base_branch)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery):
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
async def on_branch_commit_request(callback: CallbackQuery):
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

    await callback.message.edit_text(
        "`[~]` Sent: \"Commit current changes in logical chunks with descriptive messages.\"\n\n"
        f"Run `/branch_create {branch_name}` again after commit.",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "branch_create_redirect")
async def on_branch_redirect(callback: CallbackQuery):
    """Handle redirect to /branch_create."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)

    await callback.message.edit_text(
        "Use `/branch_create` or `/branch_create <name>` to create isolated worktree branch.",
        parse_mode="Markdown"
    )
    await callback.answer()


# ===== /branch_finish =====

@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message):
    """Finish branch: merge and cleanup worktree."""
    if not await require_forum_group(message):
        return

    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(message.chat.id)

    if not project:
        await message.answer("`[!]` Project not registered.", parse_mode="Markdown")
        return

    thread = project.get_thread(thread_id)
    if not thread or not thread.worktree_path:
        await message.answer("`[!]` /branch_finish only works in worktree topics. Use /thread_delete for this topic.", parse_mode="Markdown")
        return

    # Check uncommitted changes
    worktree_path = Path(thread.worktree_path)

    if worktree_path.exists() and has_uncommitted_changes(worktree_path):
        await message.answer("`[!]` Uncommitted changes. Commit or stash first.", parse_mode="Markdown")
        return

    # Build keyboard
    default_branch = get_default_branch(Path(project.cwd))
    buttons = [[InlineKeyboardButton(text=f"Merge -> {default_branch}", callback_data=f"bf_merge:{thread_id}:{default_branch}")]]

    # Add base_branch option if it exists and is different
    if thread.base_branch and thread.base_branch != default_branch:
        if branch_exists(Path(project.cwd), thread.base_branch):
            buttons.append([InlineKeyboardButton(text=f"Merge -> {thread.base_branch}", callback_data=f"bf_merge:{thread_id}:{thread.base_branch}")])

    buttons.append([InlineKeyboardButton(text="[!!] Delete without merge", callback_data=f"bf_delete:{thread_id}")])
    buttons.append([InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(f"Finish `{thread.name}` branch:", reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("bf_merge:"))
async def on_branch_merge_selected(callback: CallbackQuery):
    """Show merge confirmation."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Check target has no uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        await callback.message.edit_text("`[!]` Uncommitted changes in target directory. Commit or stash first.", parse_mode="Markdown")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, finish", callback_data=f"bf_do_merge:{thread_id}:{target_branch}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"Merge `{thread.name}` -> `{target_branch}` will:\n"
        "- Merge branch and push\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        "- Archive topic\n\n"
        "Continue?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_merge:"))
async def on_branch_do_merge(callback: CallbackQuery):
    """Execute merge and cleanup."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Merging {thread.name} -> {target_branch}...", parse_mode="Markdown")
    await callback.answer()

    main_repo = Path(project.cwd)
    branch_name = thread.name

    # Merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        if "conflicts" in result.error.lower():
            await callback.message.edit_text("`[!]` Merge conflicts. Resolve and run /branch_finish again.", parse_mode="Markdown")
        else:
            await callback.message.edit_text(f"`[x]` Merge failed: {result.error}", parse_mode="Markdown")
        return

    # Push (optional, don't fail on error)
    push_result = push_branch(main_repo, target_branch)
    push_warning = "" if push_result.success else "\n`[!]` Push failed. Run `git push` manually."

    # Cleanup
    await do_branch_cleanup(callback.bot, callback.message.chat.id, project, thread, force=False)

    await callback.message.edit_text(f"`[v]` Branch {branch_name} merged and cleaned up{push_warning}", parse_mode="Markdown")


@router.callback_query(F.data.startswith("bf_delete:"))
async def on_branch_delete_selected(callback: CallbackQuery):
    """Show delete confirmation."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, delete", callback_data=f"bf_do_delete:{thread_id}")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])

    await callback.message.edit_text(
        f"`[!!]` Delete `{thread.name}` WITHOUT merging?\n\n"
        "This will:\n"
        "- Close tmux session\n"
        f"- Delete {thread.worktree_path}\n"
        "- Delete local branch\n"
        "- Archive topic\n\n"
        "WARNING: Changes will be LOST!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bf_do_delete:"))
async def on_branch_do_delete(callback: CallbackQuery):
    """Execute delete without merge."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await callback.message.edit_text(f"`[~]` Deleting {thread.name}...", parse_mode="Markdown")
    await callback.answer()

    # Cleanup with force=True to delete branch
    await do_branch_cleanup(callback.bot, callback.message.chat.id, project, thread, force=True)

    await callback.message.edit_text(f"`[v]` Branch {thread.name} deleted", parse_mode="Markdown")
