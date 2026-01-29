# Group Authorization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow bot usage in groups where at least one group admin is in ADMIN_IDS.

**Architecture:** Event-driven approach with persistence. GroupAuthService manages allowed_groups in config.json. AdminMiddleware delegates group checks to service. Handler for chat_member events tracks admin changes.

**Tech Stack:** aiogram 3.x, pytest, unittest.mock

---

### Task 1: Config functions for allowed_groups

**Files:**
- Modify: `src/codogram/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
class TestAllowedGroups:
    """Tests for allowed_groups config functions."""

    def test_get_allowed_groups_empty_default(self, tmp_path, monkeypatch):
        """Returns empty set when no allowed_groups in config."""
        monkeypatch.setattr("codogram.config.CONFIG_PATH", tmp_path / "config.json")
        from codogram.config import get_allowed_groups
        assert get_allowed_groups() == set()

    def test_get_allowed_groups_returns_set(self, tmp_path, monkeypatch):
        """Returns set of group IDs from config."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123, 456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        from codogram.config import get_allowed_groups
        assert get_allowed_groups() == {123, 456}

    def test_add_allowed_group(self, tmp_path, monkeypatch):
        """Adds group to allowed list."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"projects": {}}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import add_allowed_group, get_allowed_groups
        add_allowed_group(123)
        assert 123 in get_allowed_groups()

    def test_add_allowed_group_idempotent(self, tmp_path, monkeypatch):
        """Adding same group twice doesn't duplicate."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import add_allowed_group, get_allowed_groups
        add_allowed_group(123)
        assert get_allowed_groups() == {123}

    def test_remove_allowed_group(self, tmp_path, monkeypatch):
        """Removes group from allowed list."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [123, 456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import remove_allowed_group, get_allowed_groups
        remove_allowed_group(123)
        assert get_allowed_groups() == {456}

    def test_remove_allowed_group_not_exists(self, tmp_path, monkeypatch):
        """Removing non-existent group is no-op."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"allowed_groups": [456]}')
        monkeypatch.setattr("codogram.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("codogram.config.CONFIG_DIR", tmp_path)
        from codogram.config import remove_allowed_group, get_allowed_groups
        remove_allowed_group(123)  # Should not raise
        assert get_allowed_groups() == {456}
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::TestAllowedGroups -v`
Expected: FAIL with "cannot import name 'get_allowed_groups'"

**Step 3: Write minimal implementation**

Add to `src/codogram/config.py`:

```python
def get_allowed_groups() -> set[int]:
    """Get set of allowed group IDs."""
    config = load_config()
    return set(config.get("allowed_groups", []))


def add_allowed_group(group_id: int) -> None:
    """Add group to allowed list."""
    config = load_config()
    groups = set(config.get("allowed_groups", []))
    groups.add(group_id)
    config["allowed_groups"] = list(groups)
    save_config(config)


def remove_allowed_group(group_id: int) -> None:
    """Remove group from allowed list."""
    config = load_config()
    groups = set(config.get("allowed_groups", []))
    groups.discard(group_id)
    config["allowed_groups"] = list(groups)
    save_config(config)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py::TestAllowedGroups -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/codogram/config.py tests/test_config.py
git commit -m "feat(config): add allowed_groups functions"
```

---

### Task 2: GroupAuthService

**Files:**
- Create: `src/codogram/services/group_auth.py`
- Create: `tests/services/test_group_auth.py`

**Step 1: Write the failing tests**

Create `tests/services/test_group_auth.py`:

```python
"""Tests for GroupAuthService."""
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123,456")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestGroupAuthService:
    """Tests for GroupAuthService."""

    def test_is_allowed_true(self):
        """Returns True for allowed group."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        with patch("codogram.services.group_auth.get_allowed_groups", return_value={123}):
            assert service.is_allowed(123) is True

    def test_is_allowed_false(self):
        """Returns False for unknown group."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        with patch("codogram.services.group_auth.get_allowed_groups", return_value={123}):
            assert service.is_allowed(999) is False

    def test_needs_revalidation_true(self):
        """Returns True for group in allowed but not validated this run."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        with patch("codogram.services.group_auth.get_allowed_groups", return_value={123}):
            assert service.needs_revalidation(123) is True

    def test_needs_revalidation_false_after_validation(self):
        """Returns False after group has been validated."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        service._validated_this_run.add(123)
        with patch("codogram.services.group_auth.get_allowed_groups", return_value={123}):
            assert service.needs_revalidation(123) is False

    def test_needs_revalidation_false_unknown_group(self):
        """Returns False for group not in allowed_groups."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        with patch("codogram.services.group_auth.get_allowed_groups", return_value={123}):
            assert service.needs_revalidation(999) is False

    @pytest.mark.asyncio
    async def test_check_and_register_success(self):
        """Registers group when admin from ADMIN_IDS found."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        admin = Mock(user=Mock(id=123), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.add_allowed_group") as mock_add, \
             patch("codogram.services.group_auth.get_allowed_groups", return_value=set()):
            result = await service.check_and_register(bot, 999)

        assert result is True
        mock_add.assert_called_once_with(999)
        assert 999 in service._validated_this_run

    @pytest.mark.asyncio
    async def test_check_and_register_no_admin(self):
        """Returns False when no admin from ADMIN_IDS."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        admin = Mock(user=Mock(id=777), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.add_allowed_group") as mock_add, \
             patch("codogram.services.group_auth.get_allowed_groups", return_value=set()):
            result = await service.check_and_register(bot, 999)

        assert result is False
        mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_register_race_condition(self):
        """Returns False if already checking same group."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        service._checking.add(999)

        bot = AsyncMock()
        result = await service.check_and_register(bot, 999)

        assert result is False
        bot.get_chat_administrators.assert_not_called()

    @pytest.mark.asyncio
    async def test_revalidate_still_valid(self):
        """Returns True if group still has admin from ADMIN_IDS."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        admin = Mock(user=Mock(id=123), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.remove_allowed_group"):
            result = await service.revalidate(bot, 999)

        assert result is True
        assert 999 in service._validated_this_run

    @pytest.mark.asyncio
    async def test_revalidate_invalid(self):
        """Returns False and removes group if no admin from ADMIN_IDS."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        admin = Mock(user=Mock(id=777), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.remove_allowed_group") as mock_remove:
            result = await service.revalidate(bot, 999)

        assert result is False
        mock_remove.assert_called_once_with(999)

    @pytest.mark.asyncio
    async def test_on_admin_left_not_our_admin(self):
        """Returns False if leaving user not in ADMIN_IDS."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}):
            result = await service.on_admin_left(bot, 999, 777)

        assert result is False
        bot.get_chat_administrators.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_admin_left_still_valid(self):
        """Returns False if another admin from ADMIN_IDS remains."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        remaining_admin = Mock(user=Mock(id=456), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[remaining_admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123, 456}), \
             patch("codogram.services.group_auth.remove_allowed_group"):
            result = await service.on_admin_left(bot, 999, 123)

        assert result is False

    @pytest.mark.asyncio
    async def test_on_admin_left_deactivated(self):
        """Returns True and removes group if last admin from ADMIN_IDS left."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        other_admin = Mock(user=Mock(id=777), status="administrator")
        bot.get_chat_administrators = AsyncMock(return_value=[other_admin])

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.remove_allowed_group") as mock_remove:
            result = await service.on_admin_left(bot, 999, 123)

        assert result is True
        mock_remove.assert_called_once_with(999)

    def test_on_bot_removed(self):
        """Removes group from allowed and validated sets."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()
        service._validated_this_run.add(999)

        with patch("codogram.services.group_auth.remove_allowed_group") as mock_remove:
            service.on_bot_removed(999)

        mock_remove.assert_called_once_with(999)
        assert 999 not in service._validated_this_run

    @pytest.mark.asyncio
    async def test_check_and_register_handles_api_error(self):
        """Returns False when API call fails."""
        from codogram.services.group_auth import GroupAuthService
        service = GroupAuthService()

        bot = AsyncMock()
        bot.get_chat_administrators = AsyncMock(side_effect=Exception("Forbidden"))

        with patch("codogram.services.group_auth.get_admin_ids", return_value={123}), \
             patch("codogram.services.group_auth.add_allowed_group") as mock_add, \
             patch("codogram.services.group_auth.get_allowed_groups", return_value=set()):
            result = await service.check_and_register(bot, 999)

        assert result is False
        mock_add.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_group_auth.py -v`
Expected: FAIL with "No module named 'codogram.services.group_auth'"

**Step 3: Write minimal implementation**

Create `src/codogram/services/group_auth.py`:

```python
"""Group authorization service."""
from aiogram import Bot

from ..config import (
    get_allowed_groups,
    add_allowed_group,
    remove_allowed_group,
)
from ..middleware.admin import get_admin_ids
from ..logging_config import logger


class GroupAuthService:
    """Manages group authorization based on admin membership."""

    def __init__(self):
        self._checking: set[int] = set()  # Groups being checked (race condition protection)
        self._validated_this_run: set[int] = set()  # Groups re-validated after restart

    def is_allowed(self, chat_id: int) -> bool:
        """Check if group is in allowed_groups."""
        return chat_id in get_allowed_groups()

    def needs_revalidation(self, chat_id: int) -> bool:
        """Check if group needs re-validation (first message after restart)."""
        return chat_id in get_allowed_groups() and chat_id not in self._validated_this_run

    async def check_and_register(self, bot: Bot, chat_id: int) -> bool:
        """Check group admins, register if valid.

        Returns True if group was registered (or already was).
        Returns False if no admin from ADMIN_IDS found.

        Race condition protection: if already checking this group, returns False.
        """
        if chat_id in self._checking:
            return False

        self._checking.add(chat_id)
        try:
            if await self._has_our_admin(bot, chat_id):
                add_allowed_group(chat_id)
                self._validated_this_run.add(chat_id)
                logger.info(f"group_registered: chat_id={chat_id}")
                return True
            return False
        finally:
            self._checking.discard(chat_id)

    async def revalidate(self, bot: Bot, chat_id: int) -> bool:
        """Re-validate group after restart.

        Returns True if still valid, False if deactivated.
        """
        self._validated_this_run.add(chat_id)

        if await self._has_our_admin(bot, chat_id):
            return True

        remove_allowed_group(chat_id)
        logger.info(f"group_invalidated_on_revalidation: chat_id={chat_id}")
        return False

    async def on_admin_left(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """Handle admin leaving or being demoted.

        If user_id in ADMIN_IDS, re-check group.
        Returns True if group was deactivated.
        """
        if user_id not in get_admin_ids():
            return False

        if await self._has_our_admin(bot, chat_id):
            return False

        remove_allowed_group(chat_id)
        logger.info(f"group_deactivated: chat_id={chat_id}")
        return True

    def on_bot_removed(self, chat_id: int) -> None:
        """Handle bot being removed from group."""
        remove_allowed_group(chat_id)
        self._validated_this_run.discard(chat_id)
        logger.info(f"bot_removed_from_group: chat_id={chat_id}")

    async def _has_our_admin(self, bot: Bot, chat_id: int) -> bool:
        """Check if group has at least one admin from ADMIN_IDS."""
        try:
            admins = await bot.get_chat_administrators(chat_id)
            admin_ids = get_admin_ids()
            for admin in admins:
                if admin.user.id in admin_ids:
                    return True
            return False
        except Exception as e:
            logger.warning(f"failed_to_get_admins: chat_id={chat_id} error={e}")
            return False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_group_auth.py -v`
Expected: PASS (15 tests)

**Step 5: Commit**

```bash
git add src/codogram/services/group_auth.py tests/services/test_group_auth.py
git commit -m "feat(services): add GroupAuthService"
```

---

### Task 3: New strings for group authorization

**Files:**
- Modify: `src/codogram/strings.py`
- Test: `tests/test_strings.py`

**Step 1: Write the failing tests**

Add to `tests/test_strings.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strings.py::test_group_authorization_strings_exist -v`
Expected: FAIL with "AttributeError: module 'codogram.strings' has no attribute 'ERR_GROUP_NOT_ALLOWED'"

**Step 3: Write minimal implementation**

Add to `src/codogram/strings.py` in the `# --- Errors ---` section:

```python
# --- Group Authorization ---

ERR_GROUP_NOT_ALLOWED = f"{STATUS_ERR} Bot not active in this group"
ERR_GROUP_NOT_ALLOWED_POPUP = "[x] Bot not active in this group"  # Plain text for callback popup
GROUP_REGISTERED = f"{STATUS_OK} Group registered"
GROUP_DEACTIVATED = f"{STATUS_WARN} Admin left\\. Bot deactivated"
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strings.py::test_group_authorization_strings_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/strings.py tests/test_strings.py
git commit -m "feat(strings): add group authorization messages"
```

---

### Task 4: Extend members handler for group authorization

**Files:**
- Modify: `src/codogram/handlers/members.py` (extend existing emoji pack handler)
- Create: `tests/test_handlers_members.py`

**Note:** `handlers/members.py` already exists for emoji pack functionality. We extend it with group authorization logic.

**Step 1: Write the failing tests**

Create `tests/test_handlers_members.py`:

```python
"""Tests for members handler."""
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestIsLeaveOrDemotion:
    """Tests for _is_leave_or_demotion helper."""

    def test_left_status(self):
        """Returns True for 'left' status."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "left"
        assert _is_leave_or_demotion(event) is True

    def test_kicked_status(self):
        """Returns True for 'kicked' status."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "kicked"
        assert _is_leave_or_demotion(event) is True

    def test_demoted_from_admin(self):
        """Returns True when demoted from admin to member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is True

    def test_demoted_from_creator(self):
        """Returns True when demoted from creator to member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "creator"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is True

    def test_member_still_member(self):
        """Returns False when member stays member."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "member"
        assert _is_leave_or_demotion(event) is False

    def test_promoted_to_admin(self):
        """Returns False when promoted to admin."""
        from codogram.handlers.members import _is_leave_or_demotion
        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "administrator"
        assert _is_leave_or_demotion(event) is False


class TestOnBotStatusChanged:
    """Tests for on_bot_status_changed handler."""

    @pytest.mark.asyncio
    async def test_ignores_private_chat(self):
        """Ignores events from private chats."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "private"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_added_registers_group(self):
        """Calls check_and_register when bot added as member."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 123
        event.new_chat_member.status = "member"
        event.bot = Mock()
        group_auth = AsyncMock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_called_once_with(event.bot, 123)

    @pytest.mark.asyncio
    async def test_bot_added_as_admin_registers_group(self):
        """Calls check_and_register when bot added as administrator."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "group"
        event.chat.id = 456
        event.new_chat_member.status = "administrator"
        event.bot = Mock()
        group_auth = AsyncMock()

        await on_bot_status_changed(event, group_auth)

        group_auth.check_and_register.assert_called_once_with(event.bot, 456)

    @pytest.mark.asyncio
    async def test_bot_removed_calls_on_bot_removed(self):
        """Calls on_bot_removed when bot leaves."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 789
        event.new_chat_member.status = "left"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.on_bot_removed.assert_called_once_with(789)

    @pytest.mark.asyncio
    async def test_bot_kicked_calls_on_bot_removed(self):
        """Calls on_bot_removed when bot is kicked."""
        from codogram.handlers.members import on_bot_status_changed

        event = Mock()
        event.chat.type = "supergroup"
        event.chat.id = 789
        event.new_chat_member.status = "kicked"
        group_auth = Mock()

        await on_bot_status_changed(event, group_auth)

        group_auth.on_bot_removed.assert_called_once_with(789)


class TestOnMemberUpdate:
    """Tests for on_member_update handler."""

    @pytest.mark.asyncio
    async def test_ignores_non_leave_events(self):
        """Ignores member joins and promotions."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "administrator"
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()

        await on_member_update(event, telegram_queue, group_auth)

        group_auth.on_admin_left.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_on_admin_left_for_leave(self):
        """Calls on_admin_left when member leaves."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=False)

        await on_member_update(event, telegram_queue, group_auth)

        group_auth.on_admin_left.assert_called_once_with(event.bot, 123, 456)

    @pytest.mark.asyncio
    async def test_sends_message_when_deactivated(self):
        """Sends GROUP_DEACTIVATED message when group deactivated."""
        from codogram.handlers.members import on_member_update
        from codogram import strings

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=True)

        await on_member_update(event, telegram_queue, group_auth)

        telegram_queue.send.assert_called_once_with(123, strings.GROUP_DEACTIVATED)

    @pytest.mark.asyncio
    async def test_no_message_when_still_valid(self):
        """No message when group still valid after admin leaves."""
        from codogram.handlers.members import on_member_update

        event = Mock()
        event.chat.id = 123
        event.bot = Mock()
        event.old_chat_member.status = "administrator"
        event.new_chat_member = Mock(status="left", user=Mock(id=456))
        telegram_queue = AsyncMock()
        group_auth = AsyncMock()
        group_auth.on_admin_left = AsyncMock(return_value=False)

        await on_member_update(event, telegram_queue, group_auth)

        telegram_queue.send.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_members.py -v`
Expected: FAIL with "cannot import name '_is_leave_or_demotion'" or "on_bot_status_changed"

**Step 3: Extend existing members.py**

The file already exists with emoji pack logic. Add group authorization handlers.

**Add imports** (at top of file, after existing imports):

```python
from ..services.group_auth import GroupAuthService
from ..telegram_queue import TelegramQueue
from .. import strings
```

**Add helper function** (after existing `_is_leave`):

```python
def _is_leave_or_demotion(event: ChatMemberUpdated) -> bool:
    """Check if user left, was kicked, or was demoted from admin."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Left or kicked
    if new_status in ("left", "kicked"):
        return True

    # Demoted from admin/creator to regular member
    old_is_admin = old_status in ("administrator", "creator")
    new_is_admin = new_status in ("administrator", "creator")
    if old_is_admin and not new_is_admin:
        return True

    return False
```

**Add bot status handler** (new handler for my_chat_member):

```python
@router.my_chat_member()
async def on_bot_status_changed(
    event: ChatMemberUpdated,
    group_auth: GroupAuthService,
) -> None:
    """Handle bot being added/removed from group."""
    chat_type = event.chat.type
    if chat_type not in ("group", "supergroup"):
        return

    new_status = event.new_chat_member.status

    if new_status in ("member", "administrator"):
        # Bot added to group — try to register
        logger.info(f"bot_added_to_group: chat_id={event.chat.id}")
        await group_auth.check_and_register(event.bot, event.chat.id)

    elif new_status in ("left", "kicked"):
        # Bot removed from group
        logger.info(f"bot_removed_from_group: chat_id={event.chat.id}")
        group_auth.on_bot_removed(event.chat.id)
```

**Extend existing on_member_update** — add group_auth parameters and logic:

```python
@router.chat_member()
async def on_member_update(
    event: ChatMemberUpdated,
    telegram_queue: TelegramQueue,
    group_auth: GroupAuthService,
) -> None:
    """Handle member join/leave for emoji pack and group authorization."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    # --- Group authorization: check if admin left/demoted ---
    if _is_leave_or_demotion(event):
        deactivated = await group_auth.on_admin_left(
            event.bot, event.chat.id, user.id
        )
        if deactivated:
            logger.info(f"group_deactivated: chat_id={event.chat.id}")
            await telegram_queue.send(event.chat.id, strings.GROUP_DEACTIVATED)

    # --- Emoji pack: update stickers ---
    project = project_manager.get_by_chat(event.chat.id)
    if not project or not project.feat_avatar_pack:
        return

    adapter = StickerAdapter(event.bot)
    service = EmojiPackService(adapter)

    if _is_join(event):
        logger.info(f"Member joined, adding to emoji pack: {user.id}")
        await service.add_member(event.chat.id, user)

    elif _is_leave(event):
        logger.info(f"Member left, removing from emoji pack: {user.id}")
        await service.remove_member(event.chat.id, user.id)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_members.py -v`
Expected: PASS (14 tests)

**Step 5: Commit**

```bash
git add src/codogram/handlers/members.py tests/test_handlers_members.py
git commit -m "feat(handlers): add members handler for chat_member events"
```

---

### Task 5: Update AdminMiddleware for group authorization

**Files:**
- Modify: `src/codogram/middleware/admin.py`
- Modify: `tests/test_admin_middleware.py`

**Step 1: Write the failing tests**

Add to `tests/test_admin_middleware.py`:

```python
from aiogram.types import Message, CallbackQuery


class TestAdminMiddlewareGroups:
    """Tests for group authorization in AdminMiddleware."""

    @pytest.mark.asyncio
    async def test_group_allowed_passes(self):
        """Allowed group members can access handlers."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=True)
        group_auth.needs_revalidation = Mock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_called_once()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_group_not_allowed_registers(self):
        """Unknown group triggers check_and_register."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=True)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        bot = Mock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": bot,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        group_auth.check_and_register.assert_called_once_with(bot, 123)
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_rejected_sends_message(self):
        """Unauthorized group gets rejection message."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        telegram_queue = AsyncMock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
            "telegram_queue": telegram_queue,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        telegram_queue.reply.assert_called_once()
        assert "not active" in telegram_queue.reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_group_media_ignored(self):
        """Non-text messages in groups are ignored."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = None  # Media message
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
        }

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_group_revalidation_triggered(self):
        """Re-validation is triggered after restart."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.needs_revalidation = Mock(return_value=True)
        group_auth.revalidate = AsyncMock(return_value=True)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock(return_value="result")
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        group_auth.revalidate.assert_called_once()
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_none_ignored(self):
        """Events with chat=None are ignored."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock()
        data = {
            "event_from_user": Mock(id=123, is_bot=False),
            "event_chat": None,
        }

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_group_revalidation_fails_sends_rejection(self):
        """Re-validation failure sends rejection message."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.needs_revalidation = Mock(return_value=True)
        group_auth.revalidate = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=Message)
        event.text = "hello"
        chat = Mock(type="supergroup", id=123)
        telegram_queue = AsyncMock()
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
            "telegram_queue": telegram_queue,
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        telegram_queue.reply.assert_called_once()
        assert "not active" in telegram_queue.reply.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_callback_query_rejected_in_group(self):
        """CallbackQuery in unauthorized group gets popup."""
        from codogram.middleware.admin import AdminMiddleware
        from codogram.services.group_auth import GroupAuthService

        group_auth = Mock(spec=GroupAuthService)
        group_auth.is_allowed = Mock(return_value=False)
        group_auth.needs_revalidation = Mock(return_value=False)
        group_auth.check_and_register = AsyncMock(return_value=False)

        middleware = AdminMiddleware(group_auth)
        handler = AsyncMock()
        event = Mock(spec=CallbackQuery)
        event.answer = AsyncMock()
        chat = Mock(type="supergroup", id=123)
        data = {
            "event_from_user": Mock(id=999, is_bot=False),
            "event_chat": chat,
            "bot": Mock(),
        }

        with patch("codogram.middleware.admin.is_admin", return_value=False):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        event.answer.assert_called_once()
        assert event.answer.call_args[1].get('show_alert') is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin_middleware.py::TestAdminMiddlewareGroups -v`
Expected: FAIL with "TypeError: AdminMiddleware.__init__() takes 1 positional argument but 2 were given"

**Step 3: Write implementation**

Update `src/codogram/middleware/admin.py`:

```python
"""Admin middleware - global protection for all handlers."""
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, User

from .. import strings
from ..config import settings
from ..logging_config import logger

if TYPE_CHECKING:
    from ..telegram_queue import TelegramQueue
    from ..services.group_auth import GroupAuthService

# Cache admin IDs
_admin_ids: set[int] | None = None


def get_admin_ids() -> set[int]:
    """Get admin IDs (cached)."""
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in get_admin_ids()


class AdminMiddleware(BaseMiddleware):
    """Block non-admins globally. Supports group authorization.

    Register on Dispatcher level (protects ALL routers):
        dp.message.middleware(AdminMiddleware(group_auth))
        dp.callback_query.middleware(AdminMiddleware(group_auth))
    """

    def __init__(self, group_auth: "GroupAuthService | None" = None):
        self.group_auth = group_auth

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None:
            return None

        # Ignore messages from bots (including service messages from self)
        if user.is_bot:
            return None

        chat = data.get("event_chat")

        # Unknown chat — ignore
        if chat is None:
            logger.debug("middleware_skip: chat is None")
            return None

        # Private chat — only ADMIN_IDS
        if chat.type == "private":
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        # Group/supergroup — check allowed_groups (if group_auth configured)
        if chat.type in ("group", "supergroup") and self.group_auth:
            # Ignore non-text messages (files, media)
            if isinstance(event, Message) and not event.text:
                return None

            # Re-validate after restart if needed
            if self.group_auth.needs_revalidation(chat.id):
                logger.debug(f"revalidating_group: chat_id={chat.id}")
                valid = await self.group_auth.revalidate(data["bot"], chat.id)
                if not valid:
                    logger.info(f"group_invalidated_on_revalidation: chat_id={chat.id}")
                    await self._reject_group(event, data)
                    return None
                return await handler(event, data)

            # Check if group is allowed
            if self.group_auth.is_allowed(chat.id):
                return await handler(event, data)

            # First contact — try to register
            registered = await self.group_auth.check_and_register(
                data["bot"], chat.id
            )
            if registered:
                logger.info(f"group_registered: chat_id={chat.id}")
                return await handler(event, data)

            # No admin from ADMIN_IDS in group
            logger.debug(f"group_rejected: chat_id={chat.id}")
            await self._reject_group(event, data)
            return None

        # Fallback for groups without group_auth — use old behavior (admin only)
        if chat.type in ("group", "supergroup"):
            if is_admin(user.id):
                return await handler(event, data)
            await self._reject_non_admin(event, user.id, data)
            return None

        return None

    async def _reject_non_admin(
        self, event: TelegramObject, user_id: int, data: dict[str, Any]
    ):
        """Send rejection message with user's ID."""
        if isinstance(event, Message):
            telegram_queue: "TelegramQueue" = data["telegram_queue"]
            await telegram_queue.reply(
                event,
                strings.ERR_NOT_ADMIN.format(user_id=user_id),
            )
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.ERR_NOT_ADMIN_POPUP.format(user_id=user_id),
                show_alert=True
            )

    async def _reject_group(self, event: TelegramObject, data: dict[str, Any]):
        """Send rejection for unauthorized group."""
        if isinstance(event, Message):
            telegram_queue: "TelegramQueue" = data["telegram_queue"]
            await telegram_queue.reply(event, strings.ERR_GROUP_NOT_ALLOWED)
        elif isinstance(event, CallbackQuery):
            await event.answer(
                strings.ERR_GROUP_NOT_ALLOWED_POPUP,
                show_alert=True
            )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_admin_middleware.py -v`
Expected: PASS (all tests including new group tests)

**Step 5: Commit**

```bash
git add src/codogram/middleware/admin.py tests/test_admin_middleware.py
git commit -m "feat(middleware): add group authorization to AdminMiddleware"
```

---

### Task 6: Integrate in main.py

**Files:**
- Modify: `src/codogram/main.py` (lines 14, 37, 40-41, 88)

**Note:** `handlers/__init__.py` already has `members.router` registered (from emoji pack feature). No changes needed there.

**Step 1: Update main.py imports**

At line 14 (after `from .middleware.admin import AdminMiddleware`), add:

```python
from .services.group_auth import GroupAuthService
```

**Step 2: Update main.py - GroupAuthService initialization**

After line 37 (`dp["telegram_queue"] = telegram_queue`), add:

```python
    # Group authorization service
    group_auth = GroupAuthService()
    dp["group_auth"] = group_auth  # Register for aiogram DI
```

**Step 3: Update main.py - middleware registration**

Change lines 40-41 from:

```python
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())
```

to:

```python
    dp.message.middleware(AdminMiddleware(group_auth))
    dp.callback_query.middleware(AdminMiddleware(group_auth))
```

**Step 4: Update main.py - start_polling**

Change line 88 from:

```python
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])
```

to:

```python
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
        )
```

**Note:** `my_chat_member` is required to receive events when bot is added/removed from groups.

**Step 5: Test manually**

Run: `./kill-instance-and-start-from-worktree.sh`
Test: Add bot to a test group where you are admin

**Step 6: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): integrate group authorization"
```

---

### Task 7: E2E Testing

**Files:**
- Update: `docs/e2e/commands/start.md` (or create new file)

**Step 1: Document E2E test cases**

Create `docs/e2e/commands/group-auth.md`:

```markdown
# Group Authorization E2E Tests

## Prerequisites
- Test group where MCP user is admin
- Test group where MCP user is NOT admin

## Test: Bot added to group with admin

1. Add bot to group where MCP user is admin
2. Send `/start` in group
3. Expected: Bot responds, group registered

## Test: Bot added to group without admin

1. Add bot to group where MCP user is NOT in ADMIN_IDS
2. Send `/help` in group
3. Expected: `[x] Bot not active in this group`

## Test: Admin leaves group

1. Have bot in group with MCP user as only ADMIN_IDS admin
2. Leave the group (or have another admin remove MCP user)
3. Expected: `[!] Admin left. Bot deactivated`

## Test: Private chat still works for admins

1. Send `/help` to bot in private chat as ADMIN_IDS user
2. Expected: Normal response

## Test: Private chat blocked for non-admins

1. Send `/help` to bot in private chat as non-admin
2. Expected: `[x] Not admin. Your ID: ...`
```

**Step 2: Run E2E tests with Telegram MCP**

Ask user for test chat ID, then test via MCP tools.

**Step 3: Commit**

```bash
git add docs/e2e/commands/group-auth.md
git commit -m "docs(e2e): add group authorization test cases"
```

---

## Summary

| Task | Description | Files | Tests |
|------|-------------|-------|-------|
| 1 | Config functions | config.py, test_config.py | 6 |
| 2 | GroupAuthService | services/group_auth.py, tests/services/test_group_auth.py | 15 |
| 3 | Strings | strings.py, test_strings.py | 1 |
| 4 | Extend members handler | handlers/members.py (modify), tests/test_handlers_members.py | 14 |
| 5 | AdminMiddleware | middleware/admin.py, test_admin_middleware.py | 8 |
| 6 | Integration | main.py only (handlers/__init__.py already done) | manual |
| 7 | E2E docs | docs/e2e/commands/group-auth.md | E2E |

**Total new tests:** 44

**Note:** Task 4 extends existing `handlers/members.py` from emoji pack feature rather than creating new file.
