"""Service for creating and managing avatar emoji packs."""
import asyncio
import io
from pathlib import Path

from aiogram.types import User
from PIL import Image, ImageDraw, ImageFont

from ..adapters.sticker import StickerAdapter
from ..config import settings
from ..session_manager import project_manager
from ..logging_config import logger

# Telegram-style colors for placeholder avatars
TELEGRAM_COLORS = [
    "#FF5733", "#33A1FF", "#8E44AD", "#27AE60",
    "#F39C12", "#E74C3C", "#1ABC9C"
]

# Font paths to try
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


class EmojiPackService:
    """Service for creating and managing avatar emoji packs.

    Uses StickerAdapter for all Telegram API calls (layered architecture).
    """

    def __init__(self, adapter: StickerAdapter):
        self.adapter = adapter

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get font for placeholder text, with fallback."""
        for path in FONT_PATHS:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _get_color_for_user(self, user_id: int) -> str:
        """Get Telegram-style color for user ID."""
        return TELEGRAM_COLORS[user_id % len(TELEGRAM_COLORS)]

    def _generate_placeholder(self, user: User) -> bytes:
        """Generate placeholder avatar (circle with first letter)."""
        color = self._get_color_for_user(user.id)
        letter = (user.first_name or "?")[0].upper()

        # Create transparent image
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw circle
        draw.ellipse([0, 0, 99, 99], fill=color)

        # Draw letter
        font = self._get_font(48)
        draw.text((50, 50), letter, fill="white", anchor="mm", font=font)

        # Save to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _process_image(self, image_bytes: bytes) -> bytes:
        """Process avatar: resize to 100x100 and apply circular mask."""
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        img = img.resize((100, 100), Image.LANCZOS)

        # Create circular mask
        mask = Image.new("L", (100, 100), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([0, 0, 99, 99], fill=255)

        # Apply mask
        result = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        result.paste(img, mask=mask)

        # Save to bytes
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()

    async def _get_avatar_bytes(self, user: User) -> bytes:
        """Get avatar bytes: download via adapter or generate placeholder."""
        avatar = await self.adapter.download_user_avatar(user.id)
        if avatar:
            return self._process_image(avatar)
        return self._generate_placeholder(user)

    async def _generate_pack_name(self, chat_id: int) -> str:
        """Generate sticker pack name."""
        chat_id_str = str(abs(chat_id))
        bot_username = await self.adapter.get_bot_username()
        return f"chat_{chat_id_str}_avatars_by_{bot_username}"

    async def create_pack(self, chat_id: int, participants: list[User]) -> str | None:
        """Create emoji pack with all participants' avatars.

        Returns pack name on success, None on failure.
        """
        if not participants:
            logger.warning(f"No participants to create pack for chat {chat_id}")
            return None

        project = project_manager.get_by_chat(chat_id)
        if not project:
            logger.warning(f"Project not found for chat {chat_id}")
            return None

        pack_name = await self._generate_pack_name(chat_id)
        owner_id = settings.get_bot_owner_id()

        try:
            # Create pack with first participant
            first_user = participants[0]
            avatar_bytes = await self._get_avatar_bytes(first_user)

            await self.adapter.create_emoji_pack(
                owner_id=owner_id,
                name=pack_name,
                title="Avatars",
                sticker_bytes=avatar_bytes,
                emoji="👤",
            )
            logger.info(f"Created emoji pack: {pack_name}")

            # Get emoji_id from created sticker
            stickers = await self.adapter.get_pack_stickers(pack_name)
            if stickers:
                project.emoji_map[first_user.id] = stickers[0].custom_emoji_id

            # Add remaining participants
            for user in participants[1:]:
                await asyncio.sleep(0.5)  # Rate limit
                await self._add_user_to_pack(pack_name, user, project)

            # Save state
            project.emoji_pack_name = pack_name
            project.feat_avatar_pack = True
            project_manager._save()

            return pack_name

        except Exception as e:
            logger.error(f"Failed to create emoji pack: {e}")
            return None

    async def _add_user_to_pack(self, pack_name: str, user: User, project) -> str | None:
        """Add single user's avatar to existing pack."""
        try:
            avatar_bytes = await self._get_avatar_bytes(user)

            emoji_id = await self.adapter.add_sticker(
                owner_id=settings.get_bot_owner_id(),
                pack_name=pack_name,
                sticker_bytes=avatar_bytes,
                emoji="👤",
            )
            project.emoji_map[user.id] = emoji_id
            return emoji_id

        except Exception as e:
            logger.warning(f"Failed to add user {user.id} to pack: {e}")
            return None
