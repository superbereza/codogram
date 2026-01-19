"""Unified /finish command for completing threads and branches."""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import require_claude_ready
from ..services.branch import archive_thread
from ..git_utils import has_uncommitted_changes, get_default_branch, branch_exists
from ..worktree import merge_branch, push_branch, remove_worktree
from ..tmux import TmuxSession

router = Router(name="finish_chat")


# ===== /finish command =====

@router.message(Command("finish_chat", "finish", "archive", "fc", ignore_case=True))
async def cmd_finish_chat(message: Message, telegram_queue: TelegramQueue):
    """Unified finish command: archive topic or merge branch."""
    # Note: We don't require Claude running - archive/merge works without it
    from .common import normalize_thread_id
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    # In General topic - nothing to finish
    if thread_id is None:
        await telegram_queue.reply(message, strings.FINISH_NOTHING_IN_GENERAL)
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, strings.FINISH_PROJECT_NOT_REGISTERED)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await telegram_queue.reply(message, strings.FINISH_THREAD_NOT_FOUND)
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
        strings.FINISH_ARCHIVE_CONFIRM.format(name=thread.name),
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
            strings.FINISH_WORKTREE_NOT_FOUND.format(path=display_path),
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
            strings.FINISH_UNCOMMITTED_CHANGES.format(branch=thread.name),
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
        strings.FINISH_BRANCH_OPTIONS.format(
            name=thread.name,
            base=thread.base_branch or default_branch
        ),
        reply_markup=keyboard
    )


# ===== Callbacks =====

@router.callback_query(F.data.startswith("finish_archive:"))
async def on_finish_archive(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive regular topic (non-worktree)."""
    _, thread_id_str = callback.data.split(":")
    thread_id = int(thread_id_str)
    chat_id = callback.message.chat.id
    msg_thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # 1. Remove buttons (edit)
    await telegram_queue.edit(callback.message, strings.FINISH_ARCHIVING.format(name=thread.name))
    await callback.answer()

    await archive_thread(callback.bot, chat_id, project, thread)

    # 2. Final status (send)
    await telegram_queue.send(chat_id, strings.FINISH_ARCHIVED.format(name=thread.name), thread_id=msg_thread_id)


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
        strings.FINISH_MERGE_CONFIRM.format(branch=thread.name, target=target_branch),
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
    chat_id = callback.message.chat.id
    msg_thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
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

    # 1. Remove buttons (edit)
    await telegram_queue.edit(
        callback.message,
        strings.FINISH_MERGING.format(branch=branch_name, target=target_branch)
    )
    await callback.answer()

    # Perform merge
    result = merge_branch(main_repo, branch_name, target_branch)
    if not result.success:
        await telegram_queue.send(
            chat_id,
            strings.FINISH_MERGE_FAILED.format(error=result.error),
            thread_id=msg_thread_id
        )
        return

    # Push if requested
    if push_mode == "push":
        await telegram_queue.send(
            chat_id, strings.FINISH_PUSHING.format(target=target_branch), thread_id=msg_thread_id
        )
        push_result = push_branch(main_repo, target_branch)
        if not push_result.success:
            await telegram_queue.send(
                chat_id,
                strings.FINISH_PUSH_FAILED.format(error=push_result.error, target=target_branch),
                thread_id=msg_thread_id
            )
            return

    # Archive thread
    await telegram_queue.send(chat_id, strings.FINISH_ARCHIVING_TOPIC, thread_id=msg_thread_id)
    await archive_thread(callback.bot, chat_id, project, thread)

    # Remove worktree and branch
    await telegram_queue.send(chat_id, strings.FINISH_CLEANING_WORKTREE, thread_id=msg_thread_id)
    remove_result = remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True)

    if push_mode == "push":
        status = strings.FINISH_MERGED_PUSHED.format(branch=branch_name, target=target_branch)
    else:
        status = strings.FINISH_MERGED_LOCAL.format(branch=branch_name, target=target_branch)

    if not remove_result.success:
        status += strings.FINISH_WORKTREE_CLEANUP_FAILED.format(error=remove_result.error)

    # Final status (send)
    await telegram_queue.send(chat_id, status, thread_id=msg_thread_id)


@router.callback_query(F.data.startswith("finish_archive_branch:"))
async def on_finish_archive_branch(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Archive branch without merging."""
    parts = callback.data.split(":")
    thread_id = int(parts[1])
    mode = parts[2]  # "keep" or "discard"
    chat_id = callback.message.chat.id
    msg_thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    # 1. Remove buttons (edit)
    await telegram_queue.edit(callback.message, strings.FINISH_ARCHIVING.format(name=thread.name))
    await callback.answer()

    # Archive topic (closes topic, kills tmux)
    await archive_thread(callback.bot, chat_id, project, thread)

    # If discard mode, remove worktree with force
    if mode == "discard" and thread.worktree_path:
        main_repo = Path(project.cwd)
        worktree_path = Path(thread.worktree_path)
        remove_worktree(main_repo, worktree_path, thread.name, delete_branch=True, force=True)
        # 2. Final status (send)
        await telegram_queue.send(
            chat_id,
            strings.FINISH_DISCARDED_ARCHIVED.format(branch=thread.name),
            thread_id=msg_thread_id
        )
    else:
        # Keep mode - worktree stays for potential resume
        # 2. Final status (send)
        await telegram_queue.send(
            chat_id,
            strings.FINISH_ARCHIVED_KEPT.format(branch=thread.name),
            thread_id=msg_thread_id
        )


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

    await telegram_queue.edit(callback.message, strings.FINISH_COMMIT_SENT)
    await callback.answer()
