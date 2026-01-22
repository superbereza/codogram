# src/codogram/claude/poller/processors/ask_user.py
"""AskUserQuestion prompt processor - simple version."""
import asyncio
from dataclasses import dataclass

from ..base import BaseProcessor
from ...screen import parse_screen, AskUserQuestion
from ....telegram.queue import OutgoingBatch
from ....telegram.keyboards import ask_user_keyboard
from ....state import permission_messages, ask_options_state, active_ask_prompts
from ....config import settings
from ....core.session_manager import project_manager


SEPARATOR = "────────────"


@dataclass
class QuestionHeader:
    """Parsed question header with title and progress."""
    title: str
    current: int
    total: int


@dataclass
class ParsedOption:
    """Parsed option from AskUserQuestion."""
    num: str
    label: str


def _parse_option(opt: str) -> ParsedOption:
    """Parse option string like '1. PostgreSQL' into num and label."""
    num = opt.split(".")[0].strip()
    label = opt.split(".", 1)[1].strip() if "." in opt else opt
    return ParsedOption(num=num, label=label)


def _parse_question_header(body: str) -> tuple[QuestionHeader | None, str]:
    """Parse question header and return cleaned body.

    From: '←  ☒ Done  ☐ Current  ✔ Submit  →'
    Extracts: title='Current', current=2, total=2

    Returns (header, cleaned_body) where cleaned_body has navigation line removed.
    """
    import re
    lines = body.split("\n")
    cleaned_lines = []
    header = None

    for line in lines:
        if "←" in line and "→" in line:
            # Parse navigation line
            completed = line.count("☒")
            pending = line.count("☐")

            if completed + pending > 0:
                # Extract current question title (the ☐ item)
                # Pattern: ☐ Title or ☐ Title ✔
                match = re.search(r'☐\s+([^☐☒✔→]+)', line)
                title = match.group(1).strip() if match else ""
                header = QuestionHeader(
                    title=title,
                    current=completed + 1,
                    total=completed + pending,
                )
            # Skip this line in output
        else:
            cleaned_lines.append(line)

    cleaned_body = "\n".join(cleaned_lines).strip()
    return header, cleaned_body


class AskUserQuestionProcessor(BaseProcessor):
    """Send AskUserQuestion to Telegram once, don't update."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.debounce_start: float = 0.0
        self.last_body: str | None = None

        # Restore state from persisted last_ask_msg_id (survives restart)
        thread = ctx.thread if ctx.thread else ctx.project.threads.get(None)
        if thread and thread.last_ask_msg_id:
            self.showing = True
            self.kb_msg_id = thread.last_ask_msg_id
            self.log_debug(f"ask: restored from restart, kb_msg={self.kb_msg_id}")
        else:
            self.showing = False
            self.kb_msg_id = None

    async def process(self, screen: str) -> None:
        parsed = parse_screen(screen)
        is_ask = isinstance(parsed, AskUserQuestion)

        # Already showing - check if question changed or disappeared
        if self.showing:
            if not is_ask:
                self.log_debug("ask: gone from tmux, reset")
                self._reset()
                return
            # Check if it's a DIFFERENT question (Claude asked next question)
            if parsed.body != self.last_body:
                self.log_debug("ask: new question detected, reset")
                self._reset()
                # Fall through to debounce the new question
            else:
                # Same question still on screen
                return

        # Not showing yet
        if not is_ask:
            self.debounce_start = 0.0
            self.last_body = None
            return

        # Debounce
        now = asyncio.get_event_loop().time()
        if parsed.body != self.last_body:
            self.debounce_start = now
            self.last_body = parsed.body
            return

        if now - self.debounce_start < settings.permission_poller_debounce:
            return

        # Send to Telegram
        await self._send(parsed)

    async def _send(self, parsed: AskUserQuestion) -> None:
        try:
            messages = []
            if parsed.body:
                # Parse header and clean body (remove navigation line)
                header_info, clean_body = _parse_question_header(parsed.body)
                if header_info and header_info.title:
                    # Format: "☐ Title (N/M)" or "☐ Title" if single question
                    if header_info.total > 1:
                        header = f"☐ {header_info.title} ({header_info.current}/{header_info.total})"
                    else:
                        header = f"☐ {header_info.title}"
                    messages.append({"text": f"{SEPARATOR}\n{header}\n\n{clean_body}"})
                elif header_info:
                    # Has progress but no title
                    if header_info.total > 1:
                        header = f"({header_info.current}/{header_info.total})"
                        messages.append({"text": f"{SEPARATOR}\n{header}\n\n{clean_body}"})
                    else:
                        messages.append({"text": f"{SEPARATOR}\n{clean_body}"})
                else:
                    messages.append({"text": f"{SEPARATOR}\n{parsed.body}"})

            is_multi = parsed.checked is not None
            if is_multi:
                # Multi-select: show options with checkboxes
                lines = []
                for opt in parsed.options:
                    p = _parse_option(opt)
                    checked = parsed.checked.get(p.num, False)
                    mark = "✓" if checked else "☐"
                    lines.append(f"{mark} {p.num}. {p.label}")
                messages.append({"text": "\n".join(lines)})
            else:
                # Single-select: just options
                messages.append({"text": "\n".join(parsed.options)})

            messages.append({"text": "👆 select or type"})

            total = len(parsed.options)
            kb = ask_user_keyboard(parsed.options, self.ctx.tmux_name, is_multi, total)

            batch = OutgoingBatch(
                chat_id=self.ctx.chat_id,
                thread_id=self.ctx.thread_id,
                messages=messages,
                reply_markup=kb,
            )
            msg_ids = await self.ctx.queue.enqueue(batch)

            self.kb_msg_id = msg_ids[-1] if msg_ids else None
            if self.kb_msg_id:
                permission_messages[self.kb_msg_id] = msg_ids[:-1]

                # Store options state for multi-select
                if is_multi:
                    options_list = []
                    initial_checked = {}
                    for opt in parsed.options:
                        p = _parse_option(opt)
                        options_list.append({"num": p.num, "label": p.label})
                        initial_checked[p.num] = parsed.checked.get(p.num, False)
                    ask_options_state[self.kb_msg_id] = {
                        "options": options_list,
                        "checked": dict(initial_checked),  # Current state (will be modified)
                        "initial": initial_checked,        # Initial state (for diff on Submit)
                        "total": total,
                    }

                # Register active prompt for this chat/thread
                active_ask_prompts[(self.ctx.chat_id, self.ctx.thread_id)] = self.kb_msg_id

                # Persist for restart survival
                thread = self.ctx.thread if self.ctx.thread else self.ctx.project.threads.get(None)
                if thread:
                    thread.last_ask_msg_id = self.kb_msg_id
                    project_manager._save()

            self.showing = True
            self.log_debug(f"ask: sent, kb_msg={self.kb_msg_id}")
        except Exception as e:
            self.log_warning(f"ask: send error: {e}")

    def _reset(self) -> None:
        self.showing = False
        self.debounce_start = 0.0
        self.last_body = None
        self.kb_msg_id = None

        # Clear persisted state
        thread = self.ctx.thread if self.ctx.thread else self.ctx.project.threads.get(None)
        if thread and thread.last_ask_msg_id:
            thread.last_ask_msg_id = None
            project_manager._save()
