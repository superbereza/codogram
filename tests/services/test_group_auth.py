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
