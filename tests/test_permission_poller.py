# tests/test_permission_poller.py
from telegram_bridge.permission_poller import PollerState, format_permission_content
from telegram_bridge.screen import PermissionPrompt

def test_poller_state_enum():
    assert PollerState.IDLE.value == "idle"
    assert PollerState.DEBOUNCING.value == "debouncing"
    assert PollerState.SHOWING.value == "showing"

def test_format_permission_content_full():
    perm = PermissionPrompt(
        options=["1. Yes"],
        description="Create file test.txt",
        content="+ new content",
        question="Allow?"
    )
    result = format_permission_content(perm)
    assert "Create file test.txt" in result
    assert "+ new content" in result
    assert "Allow?" in result

def test_format_permission_content_minimal():
    perm = PermissionPrompt(options=["1. Yes"])
    result = format_permission_content(perm)
    assert result == ""
