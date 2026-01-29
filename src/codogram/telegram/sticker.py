"""Adapter for Telegram Sticker API.

Isolates Bot API from business logic for testability.
"""
import io
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker

from ..logging_config import logger


@dataclass
class StickerInfo:
    """Info about a sticker in a pack."""
    file_id: str
    custom_emoji_id: str


class StickerAdapter:
    """Adapter for Telegram Sticker API."""

    def __init__(self, bot: Bot):
        self._bot = bot

    async def get_bot_username(self) -> str:
        """Get bot username for pack naming."""
        bot_me = await self._bot.get_me()
        return bot_me.username

    async def download_user_avatar(self, user_id: int) -> bytes | None:
        """Download user's avatar. Returns None if no avatar."""
        try:
            photos = await self._bot.get_user_profile_photos(user_id, limit=1)
            if not photos.photos:
                logger.debug(f"No photos available for user {user_id} (privacy or no avatar)")
                return None

            photo = photos.photos[0][-1]  # Largest size
            file = await self._bot.get_file(photo.file_id)

            buf = io.BytesIO()
            await self._bot.download_file(file.file_path, buf)
            return buf.getvalue()
        except Exception as e:
            logger.warning(f"Failed to download avatar for user {user_id}: {e}")
            return None

    async def create_emoji_pack(
        self, owner_id: int, name: str, title: str, sticker_bytes: bytes, emoji: str
    ) -> None:
        """Create new emoji pack with first sticker."""
        sticker = InputSticker(
            sticker=BufferedInputFile(sticker_bytes, filename="sticker.png"),
            emoji_list=[emoji],
            format="static"
        )
        await self._bot.create_new_sticker_set(
            user_id=owner_id,
            name=name,
            title=title,
            stickers=[sticker],
            sticker_type="custom_emoji",
        )

    async def add_sticker(
        self, owner_id: int, pack_name: str, sticker_bytes: bytes, emoji: str
    ) -> str:
        """Add sticker to pack. Returns custom_emoji_id."""
        sticker = InputSticker(
            sticker=BufferedInputFile(sticker_bytes, filename="sticker.png"),
            emoji_list=[emoji],
            format="static"
        )
        await self._bot.add_sticker_to_set(
            user_id=owner_id,
            name=pack_name,
            sticker=sticker,
        )
        # Get the new sticker's emoji_id (last in pack)
        sticker_set = await self._bot.get_sticker_set(pack_name)
        return sticker_set.stickers[-1].custom_emoji_id

    async def remove_sticker(self, pack_name: str, custom_emoji_id: str) -> None:
        """Remove sticker from pack by custom_emoji_id."""
        sticker_set = await self._bot.get_sticker_set(pack_name)
        for sticker in sticker_set.stickers:
            if sticker.custom_emoji_id == custom_emoji_id:
                await self._bot.delete_sticker_from_set(sticker.file_id)
                return
        logger.warning(f"Sticker {custom_emoji_id} not found in pack {pack_name}")

    async def delete_pack(self, pack_name: str) -> None:
        """Delete entire pack."""
        await self._bot.delete_sticker_set(pack_name)

    async def get_pack_stickers(self, pack_name: str) -> list[StickerInfo]:
        """Get list of stickers in pack."""
        sticker_set = await self._bot.get_sticker_set(pack_name)
        return [
            StickerInfo(file_id=s.file_id, custom_emoji_id=s.custom_emoji_id)
            for s in sticker_set.stickers
        ]
