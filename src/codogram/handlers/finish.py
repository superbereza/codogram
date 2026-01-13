"""Unified /finish command for completing threads and branches."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..services.branch import archive_thread
from ..git_utils import has_uncommitted_changes, get_default_branch, branch_exists
from ..worktree import merge_branch, push_branch, remove_worktree
from ..tmux import TmuxSession

router = Router(name="finish")


# ===== /finish command =====

@router.message(Command("finish"))
async def cmd_finish(message: Message, telegram_queue: TelegramQueue):
    """Unified finish command: archive topic or merge branch."""
    thread_id = message.message_thread_id

    # In General topic - nothing to finish
    if thread_id is None:
        await telegram_queue.reply(
            message,
            "`[i]` Nothing to finish in General. Use /clear to reset session."
        )
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await telegram_queue.reply(message, "`[!]` Thread not found.")
        return

    # Branch topic (has worktree) - show merge options
    if thread.worktree_path:
        await _show_branch_finish_options(message, telegram_queue, project, thread)
        return

    # Regular topic - show archive confirmation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Archive topic", callback_data=f"finish_archive:{thread_id}")],
        [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
    ])
    await telegram_queue.reply(
        message,
        f"`[?]` Archive topic `{thread.name}`?\n\n"
        "This will close the topic and stop Claude session.",
        reply_markup=keyboard
    )


async def _show_branch_finish_options(
    message: Message,
    telegram_queue: TelegramQueue,
    project,
    thread
):
    """Show merge/archive options for branch topic."""
    worktree_path = Path(thread.worktree_path)
    main_repo = Path(project.cwd)

    # Check for stale worktree (deleted externally)
    if not worktree_path.exists():
        # Try to compute relative path for display, fallback to absolute
        try:
            display_path = worktree_path.relative_to(main_repo)
        except ValueError:
            display_path = worktree_path

        await telegram_queue.reply(
            message,
            f"`[!]` Worktree not found: `{display_path}`\n\n"
            "Archiving topic without git cleanup.",
        )
        await archive_thread(message.bot, message.chat.id, project, thread)
        return

    # Check for uncommitted changes
    if has_uncommitted_changes(worktree_path):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Commit changes first", callback_data=f"finish_commit:{thread.thread_id}")],
            [InlineKeyboardButton(text="Discard and archive", callback_data=f"finish_archive_branch:{thread.thread_id}:discard")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(
            message,
            f"`[!]` Branch `{thread.name}` has uncommitted changes",
            reply_markup=keyboard
        )
        return

    # Build merge options
    default_branch = get_default_branch(main_repo)
    buttons = []

    # Option 1: Merge to default branch (main/master)
    buttons.append([
        InlineKeyboardButton(
            text=f"Merge to {default_branch}",
            callback_data=f"finish_merge:{thread.thread_id}:{default_branch}"
        )
    ])

    # Option 2: Merge to base branch (if different from default)
    if thread.base_branch and thread.base_branch != default_branch:
        if branch_exists(main_repo, thread.base_branch):
            buttons.append([
                InlineKeyboardButton(
                    text=f"Merge to {thread.base_branch}",
                    callback_data=f"finish_merge:{thread.thread_id}:{thread.base_branch}"
                )
            ])

    # Option 3: Archive without merge
    buttons.append([
        InlineKeyboardButton(
            text="Archive without merge",
            callback_data=f"finish_archive_branch:{thread.thread_id}:keep"
        )
    ])

    # Cancel
    buttons.append([InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await telegram_queue.reply(
        message,
        f"Finish branch `{thread.name}`:\n\n"
        f"Base: `{thread.base_branch or default_branch}`",
        reply_markup=keyboard
    )


# ===== Callbacks =====

@router.callback_query(F.data.startswith("finish_archive:"))
async def on_finish_archive(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive regular topic (non-worktree)."""
    _, thread_id_str = callback.data.split(":")
    thread_id = int(thread_id_str)

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Archiving `{thread.name}`...")

    await archive_thread(callback.bot, callback.message.chat.id, project, thread)

    await telegram_queue.edit(callback.message, f"`[v]` Topic `{thread.name}` archived.")
    await callback.answer()


@router.callback_query(F.data.startswith("finish_merge:"))
async def on_finish_merge(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show merge confirmation with push option."""
    _, thread_id_str, target_branch = callback.data.split(":")
    thread_id = int(thread_id_str)

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Merge + Push to {target_branch}",
            callback_data=f"finish_do_merge:{thread_id}:{target_branch}:push"
        )],
        [InlineKeyboardButton(
            text=f"Merge only (no push)",
            callback_data=f"finish_do_merge:{thread_id}:{target_branch}:local"
        )],
        [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
    ])

    await telegram_queue.edit(
        callback.message,
        f"`[?]` Merge `{thread.name}` -> `{target_branch}`?\n\n"
        "Choose push option:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("finish_do_merge:"))
async def on_finish_do_merge(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Execute merge and optionally push."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    target_branch = parts[2]
    push_mode = parts[3]  # "push" or "local"

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread or not thread.worktree_path:
        await callback.answer("Thread not found")
        return

    main_repo = Path(project.cwd)
    worktree_path = Path(thread.worktree_path)
    branch_name = thread.name

    await telegram_queue.edit(callback.message, f"`[~]` Merging `{branch_name}` -> `{target_branch}`...")

    # Perform merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        await telegram_queue.edit(
            callback.message,
            f"`[x]` Merge failed: {result.error}\n\n"
            "Resolve conflicts manually and try again."
        )
        await callback.answer()
        return

    # Push if requested
    if push_mode == "push":
        await telegram_queue.edit(callback.message, f"`[~]` Pushing `{target_branch}`...")
        push_result = push_branch(main_repo, target_branch)
        if not push_result.success:
            await telegram_queue.edit(
                callback.message,
                f"`[!]` Merged but push failed: {push_result.error}\n\n"
                "Push manually: `git push origin {target_branch}`"
            )
            await callback.answer()
            return

    # Archive thread
    await telegram_queue.edit(callback.message, f"`[~]` Archiving topic...")
    await archive_thread(callback.bot, callback.message.chat.id, project, thread)

    # Remove worktree and branch
    await telegram_queue.edit(callback.message, f"`[~]` Cleaning up worktree...")
    remove_result = remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True)

    if push_mode == "push":
        status = f"`[v]` Merged and pushed `{branch_name}` -> `{target_branch}`"
    else:
        status = f"`[v]` Merged `{branch_name}` -> `{target_branch}` (local only)"

    if not remove_result.success:
        status += f"\n`[!]` Worktree cleanup failed: {remove_result.error}"

    await telegram_queue.edit(callback.message, status)
    await callback.answer()


@router.callback_query(F.data.startswith("finish_archive_branch:"))
async def on_finish_archive_branch(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive branch without merging."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    mode = parts[2]  # "keep" or "discard"

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    await telegram_queue.edit(callback.message, f"`[~]` Archiving `{thread.name}`...")

    # Archive topic (closes topic, kills tmux)
    await archive_thread(callback.bot, callback.message.chat.id, project, thread)

    # If discard mode, remove worktree with force
    if mode == "discard" and thread.worktree_path:
        main_repo = Path(project.cwd)
        worktree_path = Path(thread.worktree_path)
        remove_worktree(main_repo, worktree_path, thread.name, delete_branch=True, force=True)
        await telegram_queue.edit(
            callback.message,
            f"`[v]` Branch `{thread.name}` discarded and archived."
        )
    else:
        # Keep mode - worktree stays for potential resume
        await telegram_queue.edit(
            callback.message,
            f"`[v]` Branch `{thread.name}` archived.\n"
            "Worktree kept for potential resume."
        )

    await callback.answer()


@router.callback_query(F.data.startswith("finish_commit:"))
async def on_finish_commit(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Send commit request to Claude."""
    _, thread_id_str = callback.data.split(":")
    thread_id = int(thread_id_str)

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # Send commit message to tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    cwd = thread.worktree_path or project.cwd
    tmux = TmuxSession(tmux_name, cwd)
    if tmux.exists():
        tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        '`[~]` Sent: "Commit current changes in logical chunks with descriptive messages."\n\n'
        "Run /finish again after commit."
    )
    await callback.answer()
