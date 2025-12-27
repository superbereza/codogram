# src/codogram/state.py
"""Shared state between modules to avoid circular imports."""

# Track permission messages for deletion: {keyboard_msg_id: [content_msg_ids]}
permission_messages: dict[int, list[int]] = {}
