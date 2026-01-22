# src/codogram/state.py
"""Shared state between modules to avoid circular imports."""

# Track permission messages for deletion: {keyboard_msg_id: [content_msg_ids]}
permission_messages: dict[int, list[int]] = {}

# Track multi-select options state: {kb_msg_id: {"options": [...], "checked": {"1": False, ...}}}
ask_options_state: dict[int, dict] = {}

# Track active AskUserQuestion prompts by chat/thread: {(chat_id, thread_id): kb_msg_id}
active_ask_prompts: dict[tuple[int, int | None], int] = {}
