"""Tests for strings module."""
from codogram import strings


def test_url_validation_strings_exist():
    assert hasattr(strings, 'GIT_URL_INVALID_WIKI')
    assert hasattr(strings, 'GIT_URL_INVALID_BLOB')
    assert hasattr(strings, 'GIT_URL_INVALID_GIST')
    assert hasattr(strings, 'GIT_URL_INVALID_FORMAT')
    assert hasattr(strings, 'GIT_URL_RETRY_PROMPT')
    assert "[x]" in strings.GIT_URL_INVALID_WIKI  # Uses STATUS_ERR


def test_project_state_strings_exist():
    from codogram import strings

    # Project state
    assert hasattr(strings, 'PROJECT_NOT_READY')
    assert hasattr(strings, 'CLAUDE_STARTING')

    # Clone progress
    assert hasattr(strings, 'CLONE_IN_PROGRESS')

    # Reset flow
    assert hasattr(strings, 'RESET_NO_PROJECT')
    assert hasattr(strings, 'RESET_FLOW_IN_PROGRESS')
    assert hasattr(strings, 'RESET_CLEANUP_FAILED')
    assert hasattr(strings, 'RESET_COMPLETE')
    assert hasattr(strings, 'RESET_CONFIRM')
    assert hasattr(strings, 'RESET_CONFIRM_TOPIC')
    assert hasattr(strings, 'RESET_UNCOMMITTED')
    assert hasattr(strings, 'RESET_DIR_CHOICE')
    assert hasattr(strings, 'RESET_DONE')

    # Buttons
    assert hasattr(strings, 'BTN_CONTINUE')
    assert hasattr(strings, 'BTN_KEEP_DIR')
    assert hasattr(strings, 'BTN_DELETE_DIR')
    assert hasattr(strings, 'BTN_DELETE_ANYWAY')
    assert hasattr(strings, 'BTN_GO_BACK')


def test_group_authorization_strings_exist():
    """Group authorization strings are defined."""
    from codogram import strings
    assert hasattr(strings, "ERR_GROUP_NOT_ALLOWED")
    assert hasattr(strings, "ERR_GROUP_NOT_ALLOWED_POPUP")
    assert hasattr(strings, "GROUP_REGISTERED")
    assert hasattr(strings, "GROUP_DEACTIVATED")
    # Check tone-of-voice: status prefix
    assert "`[x]`" in strings.ERR_GROUP_NOT_ALLOWED
    assert "[x]" in strings.ERR_GROUP_NOT_ALLOWED_POPUP
    assert "`[v]`" in strings.GROUP_REGISTERED
    assert "`[!]`" in strings.GROUP_DEACTIVATED
