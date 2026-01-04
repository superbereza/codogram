"""Settings and info commands."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager

router = Router(name="settings")


@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message):
    """Show debug IDs - admin only (protected by middleware)."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await message.answer(
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}",
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show available commands."""
    text = """**Commands**

`/start` — Start Claude / show status
`/new` — Start new Claude session
`/restart` — Kill and restart Claude tmux

**Threads**
`/thread_create [name]` — Create new Claude thread
`/thread_delete` — Delete thread (in topic)

**Git worktrees**
`/branch_create [name]` — Create worktree + thread
`/branch_finish` — Merge and cleanup

**Settings**
`/settings` — Show current settings
`/auto_accept` — Toggle auto-accept
`/auto_accept reset all` — Reset all to off

**Other**
`/esc` — Send Escape to Claude
`/get_debug_ids` — Show debug IDs"""

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show current settings."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    if thread:
        auto_status = "⚡ ON" if thread.auto_accept else "OFF"
        text = (
            f"**Settings** (thread `{thread.name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )
    else:
        auto_status = "⚡ ON" if project.auto_accept else "OFF"
        text = (
            f"**Settings** (`{project.project_name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept or reset all."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await message.answer("Auto-accept reset to **OFF** for project and all threads.", parse_mode="Markdown")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "⚡ ON" if thread.auto_accept else "OFF"
        await message.answer(f"Auto-accept for `{thread.name}`: **{status}**", parse_mode="Markdown")
    else:
        project.auto_accept = not project.auto_accept
        status = "⚡ ON" if project.auto_accept else "OFF"
        await message.answer(f"Auto-accept: **{status}**", parse_mode="Markdown")
    project_manager._save()
