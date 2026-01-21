# tests/unit/services/test_response_mode.py
"""Tests for ResponseModeService."""

import pytest


def test_thread_info_response_mode_default():
    """ThreadInfo has response_mode field with default 'all'."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    assert thread.response_mode == "all"


def test_project_state_response_mode_default():
    """ProjectState has response_mode field with default 'all'."""
    from codogram.core.session_manager import ProjectState

    project = ProjectState(project_name="test")
    assert project.response_mode == "all"


def test_load_response_mode_from_thread_data():
    """response_mode is loaded from thread data."""
    from codogram.core.session_manager import ThreadInfo

    thread_data = {
        "name": "test",
        "response_mode": "polite",
    }

    thread = ThreadInfo(
        thread_id=123,
        name=thread_data.get("name", "main"),
        response_mode=thread_data.get("response_mode", "all"),
    )

    assert thread.response_mode == "polite"


def test_response_mode_all_always_responds():
    """Mode 'all' responds to everything."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="all",
        text="Hello world",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "mode=all"


def test_response_mode_mentions_ignores_without_mention():
    """Mode 'mentions' ignores messages without bot mention."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="mentions",
        text="Hello @someone",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is False
    assert result.reason == "not mentioned"


def test_response_mode_mentions_responds_to_bot_mention():
    """Mode 'mentions' responds when bot is mentioned."""
    from unittest.mock import MagicMock
    from aiogram.enums import MessageEntityType
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    entity = MagicMock()
    entity.type = MessageEntityType.MENTION
    entity.offset = 0
    entity.length = 8

    result = service.should_respond(
        mode="mentions",
        text="@testbot hello",
        entities=[entity],
        reply_to_user_id=None,
    )

    assert result.should_respond is True


def test_response_mode_mentions_responds_to_reply():
    """Mode 'mentions' responds when replying to bot's message."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="mentions",
        text="thanks!",
        entities=[],
        reply_to_user_id=123,
    )

    assert result.should_respond is True


def test_response_mode_polite_ignores_other_mentions():
    """Mode 'polite' ignores messages with other mentions."""
    from unittest.mock import MagicMock
    from aiogram.enums import MessageEntityType
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    entity = MagicMock()
    entity.type = MessageEntityType.MENTION
    entity.offset = 0
    entity.length = 5

    result = service.should_respond(
        mode="polite",
        text="@john hello",
        entities=[entity],
        reply_to_user_id=None,
    )

    assert result.should_respond is False
    assert result.reason == "directed at others"


def test_response_mode_polite_responds_to_general():
    """Mode 'polite' responds to messages without mentions."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="polite",
        text="hello everyone",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "general message"


def test_response_mode_media_only_always_responds():
    """Media-only messages (no text) always get a response."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="mentions",
        text=None,
        entities=None,
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "media-only message"


def test_response_mode_invalid_mode_defaults_allow():
    """Invalid mode defaults to allowing response."""
    from codogram.services.response_mode import ResponseModeService

    service = ResponseModeService(bot_id=123, bot_username="testbot")

    result = service.should_respond(
        mode="invalid_mode",
        text="hello",
        entities=[],
        reply_to_user_id=None,
    )

    assert result.should_respond is True
    assert result.reason == "invalid mode, default allow"