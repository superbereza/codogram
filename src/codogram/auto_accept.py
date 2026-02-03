"""Auto-accept mode for permission prompts."""
import re
from typing import TYPE_CHECKING

from .claude.screen import PromptType
from .telegram.queue import OutgoingBatch, EditBatch
from .tmux.session import TmuxSession
from .logging_config import logger
from .utils.truncate import truncate_body
from .core.session_manager import ThreadInfo, get_thread_setting
from .config import get_global_defaults
from . import strings

if TYPE_CHECKING:
    from .telegram.queue import TelegramQueue

AUTO_ACCEPT_PHRASES = ["yes", "allow"]

# Only auto-accept regular prompts (not MCP trust prompts for security)
AUTO_ACCEPT_TYPES = {PromptType.REGULAR}


def _extract_tool_name(body: str | None) -> str | None:
    """Extract tool name from permission body.

    Examples:
        "Bash command..." -> "Bash"
        "Edit file..." -> "Edit"
        "Read /path/to/file" -> "Read"
    """
    if not body:
        return None
    first_word = body.split()[0] if body.split() else None
    return first_word


def _get_tool_key_from_body(body: str | None) -> str | None:
    """Extract unique tool key from permission body text.

    Must produce same key as history_watcher.get_tool_key().

    Body formats:
        "Read /path/to/file"
        "Bash command\\n\\n   ls -la"
        "Edit file\\n /path/to/file"
        "Grep pattern in path"
    """
    if not body:
        return None

    tool_name = _extract_tool_name(body)
    if not tool_name:
        return None

    # Get everything after tool name
    rest = body[len(tool_name):].strip()

    # Debug: log body parsing
    logger.debug(f"_get_tool_key_from_body: tool={tool_name} rest={rest[:100]!r}")

    primary_arg = None

    if tool_name == "Read":
        # Body formats:
        #   "file\n\n  Read(/path/to/file)\n\n Do you want..."
        #   "/path/to/file"
        # Try to extract path from Read(...) or find bare path
        import re
        # Try Read(path) format first
        match = re.search(r'Read\(([^)]+)\)', rest)
        if match:
            primary_arg = match.group(1)
        else:
            # Find first path-like string
            for word in rest.split():
                if word.startswith("/") or word.startswith("."):
                    primary_arg = word
                    break

    elif tool_name == "Bash":
        # Body format: "command\n\n   actual_command\n   Description\n\n Do you want..."
        # Long commands are wrapped across multiple lines in Claude's display
        # Skip "command" prefix
        if rest.lower().startswith("command"):
            rest = rest[7:]

        # Collect command lines (stop at description or prompt)
        command_parts = []
        for line in rest.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower().startswith("do you want"):
                break
            # Description lines usually start with capital letter and are short sentences
            # Command lines have special chars: / | & - " ' ( ) $ = < >
            if len(command_parts) > 0:
                has_cmd_chars = any(c in stripped for c in ['/', '|', '&', '"', "'", '(', ')', '$', '=', '<', '>', '*'])
                is_short_sentence = len(stripped) < 40 and stripped[0].isupper()
                if is_short_sentence and not has_cmd_chars:
                    break  # Likely description
            command_parts.append(stripped)

        # Join parts and take first 100 chars (matching watcher's truncation)
        if command_parts:
            full_command = ' '.join(command_parts)
            primary_arg = full_command[:100]

    elif tool_name in ("Edit", "Write"):
        # Body: "Edit file\n src/codogram/..." or "Edit file\n /path/to/file"
        # Skip "file" prefix
        if rest.lower().startswith("file"):
            rest = rest[4:].strip()
        # Find path - first word on first line (before separator line "- - - -")
        first_line = rest.split('\n')[0].strip() if rest else ""
        if first_line and not first_line.startswith("-"):
            primary_arg = first_line.split()[0] if first_line.split() else None

    elif tool_name == "Grep":
        # Body: "Grep pattern..." - first word/quoted string is pattern
        primary_arg = rest.split()[0] if rest.split() else None

    elif tool_name == "Glob":
        # Body: "Glob pattern..." - first word is pattern
        primary_arg = rest.split()[0] if rest.split() else None

    elif tool_name == "Task":
        # Body: "Task prompt..." - first ~50 chars
        primary_arg = rest[:50] if rest else None

    if primary_arg:
        return f"{tool_name}:{primary_arg}"
    return tool_name


def select_option(options: list[str]) -> str | None:
    """Select safe option for auto-accept.

    Returns option number ("1", "2") or None if no safe option.
    Skips session-wide permissions ("all", "session").
    """
    if not options:
        logger.debug("select_option: no options provided")
        return None

    for option in options:
        option_lower = option.lower()

        # Skip session-wide (too permissive)
        # Match "all" as a word boundary (not as part of "allow")
        if "session" in option_lower or re.search(r'\ball\b', option_lower):
            logger.debug(f"select_option: skipping session-wide option: {option!r}")
            continue

        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            match = re.match(r'^(\d+)\.', option.strip())
            if match:
                logger.debug(f"select_option: matched option {match.group(1)!r} from {option!r}")
                return match.group(1)
            else:
                logger.warning(f"select_option: phrase matched but no number in: {option!r}")
                return None

    logger.debug(f"select_option: no matching option in {options!r}")
    return None


async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
    thread: "ThreadInfo | None" = None,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.

    Args:
        thread: Thread info containing settings for display_mode/line_limit
    """
    # Extract settings from thread
    global_defaults = get_global_defaults()
    thread_id = thread.thread_id if thread else None
    display_mode = get_thread_setting(thread, "display_mode", global_defaults) if thread else "lines"
    line_limit = get_thread_setting(thread, "line_limit", global_defaults) if thread else 5

    logger.debug(
        f"try_auto_accept ENTER: context={context_name} type={prompt_type.value} "
        f"options={options!r} body_len={len(body) if body else 0} display_mode={display_mode}"
    )

    # Security: only auto-accept whitelisted prompt types
    if prompt_type not in AUTO_ACCEPT_TYPES:
        logger.info(f"try_auto_accept SKIP: {prompt_type.value} not in AUTO_ACCEPT_TYPES")
        return False

    selected = select_option(options)
    if selected is None:
        logger.info(f"try_auto_accept SKIP: no matching option for {options!r}")
        return False

    logger.info(f"try_auto_accept OK: {context_name} sending key={selected!r}")

    # Send notification based on display_mode
    if display_mode in ("silence", "current"):
        # No notification in silence/current mode
        pass
    elif display_mode == "headers":
        # Headers mode: inline edit (append suffix to last tool message)
        edited = False
        tool_key = _get_tool_key_from_body(body)
        tool_messages = getattr(thread, 'last_tool_messages', {}) if thread else {}
        last_msg_text = tool_messages.get(tool_key) if tool_key else None

        logger.debug(f"try_auto_accept headers: tool_key={tool_key}, found={last_msg_text is not None}")

        # Build suffix with optional hint
        thread.auto_accept_count += 1
        suffix = "\n" + strings.AUTO_ACCEPT_SUFFIX
        if thread.auto_accept_count % 10 == 0:
            suffix += strings.AUTO_ACCEPT_HINT
        # TEST: verbose mode - show what's being auto-accepted
        if getattr(thread, 'test_verbose_auto_accept', False):
            body_preview = (body or "")[:60].replace('\n', ' ')
            suffix += f" [{body_preview}]"

        # If message not found, poll briefly (watcher might be about to send)
        # Watcher interval is ~0.5s, so we poll for up to 1s to catch it
        if not last_msg_text and tool_key:
            import asyncio
            for _ in range(10):  # Poll up to 1s
                await asyncio.sleep(0.1)
                tool_messages = getattr(thread, 'last_tool_messages', {})
                last_msg_text = tool_messages.get(tool_key)
                if last_msg_text:
                    logger.debug(f"try_auto_accept: found message after polling for {tool_key}")
                    break

        if last_msg_text:
            # Message already sent by watcher - edit it
            replace_key = f"tool:{chat_id}:{thread.thread_id}:{tool_key}"
            new_text = last_msg_text + suffix

            # Check length limit (Telegram max 4096)
            if len(new_text) <= 4096:
                try:
                    batch = EditBatch(
                        chat_id=chat_id,
                        message_id=0,  # Lookup from sent_statuses via replace_key
                        text=new_text,
                        parse_mode="MarkdownV2",
                        replace_key=replace_key,
                    )
                    await telegram_queue.enqueue(batch)
                    # Update stored text for potential next edit
                    thread.last_tool_messages[tool_key] = new_text
                    edited = True
                    logger.debug(f"try_auto_accept: edited {tool_key} message with suffix")
                except Exception as e:
                    logger.debug(f"try_auto_accept: edit failed, falling back: {e}")
            else:
                logger.debug(f"try_auto_accept: message too long ({len(new_text)} chars), sending new message")

        # Deferred suffix: watcher hasn't sent yet, store for later
        if not edited and tool_key:
            if not hasattr(thread, 'pending_auto_accept_suffixes'):
                thread.pending_auto_accept_suffixes = {}
            thread.pending_auto_accept_suffixes[tool_key] = suffix
            logger.debug(f"try_auto_accept: deferred suffix for {tool_key}")
            # Don't send fallback - watcher will add suffix when it sends
    else:
        # lines/show_all: send separate message with body
        if display_mode == "show_all":
            body_text = body if body else "[no details]"
        else:
            body_text = truncate_body(body, verbose=False, max_lines=line_limit) if body else "[no details]"

        batch = OutgoingBatch(
            chat_id=chat_id,
            thread_id=thread_id,
            messages=[{"text": f"🤖 Auto: {body_text}", "parse_mode": "MarkdownV2"}],
        )
        await telegram_queue.enqueue_nowait(batch)

    try:
        tmux.send_key(selected)
        logger.debug(f"try_auto_accept: tmux.send_key({selected!r}) completed")
    except Exception as e:
        logger.error(f"try_auto_accept: tmux.send_key failed: {e}")
        return False

    return True
