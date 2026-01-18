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
