# Avatar Emoji Pack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create emoji pack from group members' avatars when topics are enabled, with automatic maintenance on join/leave.

**Architecture:** StickerAdapter isolates Telegram Sticker API from business logic (layered architecture). EmojiPackService uses adapter for all API calls. Migration handler triggers pack creation. Member events handler updates pack. `/exp_avatar_pack` command for manual control.

**Tech Stack:** aiogram 3.x, Pillow for image processing, Telegram Bot API sticker methods.

---

### Task 1: Add Pillow dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add Pillow to dependencies**

In `pyproject.toml`, add to `[project] dependencies`:
```toml
"Pillow>=10.0.0",
```

**Step 2: Install dependency**

Run: `cd /home/superbereza/dev/codogram && pip install Pillow>=10.0.0`
Expected: Successfully installed Pillow

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add Pillow for image processing"
```

---

### Task 2: Add bot_owner_id to config

**Files:**
- Modify: `src/codogram/config.py:24-27`

**Step 1: Add bot_owner_id property**

After `get_admin_ids()` method, add:
```python
    def get_bot_owner_id(self) -> int:
        """First admin is considered bot owner for sticker pack ownership."""
        admin_ids = self.get_admin_ids()
        if not admin_ids:
            raise ValueError("No admin IDs configured")
        return min(admin_ids)  # First by ID for consistency
```

**Step 2: Test manually**

Run: `cd /home/superbereza/dev/codogram/.worktrees/ava-in-topic && python -c "from src.codogram.config import settings; print(settings.get_bot_owner_id())"`
Expected: prints first admin ID (e.g., 34185809)

**Step 3: Commit**

```bash
git add src/codogram/config.py
git commit -m "feat: add bot_owner_id config property"
```

---

### Task 3: Add emoji pack fields to ProjectState

**Files:**
- Modify: `src/codogram/session_manager.py:156-175`

**Step 1: Add fields to ProjectState dataclass**

In `ProjectState` class, after `feat_suggestions: bool = False`, add:
```python
    # Avatar emoji pack:
    feat_avatar_pack: bool = False
    emoji_pack_name: str | None = None
    emoji_map: dict[int, str] = field(default_factory=dict)  # {user_id: custom_emoji_id}
```

**Step 2: Update `_load_projects()` to load new fields**

In `_load_projects()`, after `project.feat_suggestions = data.get(...)` (~line 227), add:
```python
                project.feat_avatar_pack = data.get("feat_avatar_pack", False)
                project.emoji_pack_name = data.get("emoji_pack_name")
                # Convert string keys back to int (JSON serialization converts int keys to strings)
                emoji_map_raw = data.get("emoji_map", {})
                project.emoji_map = {int(k): v for k, v in emoji_map_raw.items()}
```

**Step 3: Update `_save()` to persist new fields**

In `_save()`, after `"feat_suggestions": p.feat_suggestions,` (~line 296), add:
```python
                        "feat_avatar_pack": p.feat_avatar_pack,
                        "emoji_pack_name": p.emoji_pack_name,
                        "emoji_map": p.emoji_map,
```

**Step 4: Test config load/save**

Run: `python -c "from src.codogram.session_manager import ProjectState; p = ProjectState('test'); print(p.feat_avatar_pack, p.emoji_pack_name, p.emoji_map)"`
Expected: `False None {}`

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat: add emoji pack fields to ProjectState with persistence"
```

---

### Task 4: Add emoji pack strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add emoji pack strings**

At the end of file, add:
```python

# --- Emoji Pack ---

EMOJI_PACK_CREATED = """`[v]` Gift unlocked

Avatar pack — set members as topic icons: {pack_link}

*(requires Premium)*"""

EMOJI_PACK_DISABLE_PROMPT = """`[?]` Disable avatar pack?

Pack will be deleted."""
EMOJI_PACK_BTN_DISABLE = "Yes, disable"
EMOJI_PACK_BTN_KEEP = "Keep it"

EMOJI_PACK_CREATE_PROMPT = """`[?]` Create avatar pack?

Will generate emoji from member avatars."""
EMOJI_PACK_BTN_CREATE = "Yes, create"
EMOJI_PACK_BTN_NOT_NOW = "Not now"

EMOJI_PACK_DELETED = "`[v]` Avatar pack disabled"
EMOJI_PACK_CREATING = "`[~]` Creating avatar pack..."
EMOJI_PACK_ERROR = "`[x]` Failed to create avatar pack: {error}"

# Hint in topic launch message (if feat_avatar_pack ON)
EMOJI_PACK_TOPIC_HINT = "→ Check this [pack]({pack_link}) to personalize your topic"
```

**Step 2: Test import**

Run: `python -c "from src.codogram.strings import EMOJI_PACK_CREATED; print(EMOJI_PACK_CREATED[:20])"`
Expected: prints first 20 chars of string

**Step 3: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat: add emoji pack strings"
```

---

### Task 5: Create avatar pack keyboard

**Files:**
- Create: `src/codogram/keyboards/avatar_pack.py`
- Modify: `src/codogram/keyboards/__init__.py`

**Step 1: Create keyboard file**

Create `src/codogram/keyboards/avatar_pack.py`:
```python
"""Keyboards for avatar pack prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def avatar_pack_create_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for 'Create avatar pack?' prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_CREATE,
                callback_data="avatar_pack:create"
            ),
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_NOT_NOW,
                callback_data="avatar_pack:cancel"
            ),
        ]
    ])


def avatar_pack_disable_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for 'Disable avatar pack?' prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_DISABLE,
                callback_data="avatar_pack:disable"
            ),
            InlineKeyboardButton(
                text=strings.EMOJI_PACK_BTN_KEEP,
                callback_data="avatar_pack:cancel"
            ),
        ]
    ])
```

**Step 2: Export from keyboards/__init__.py**

Add to `src/codogram/keyboards/__init__.py`:
```python
from .avatar_pack import avatar_pack_create_keyboard, avatar_pack_disable_keyboard
```

**Step 3: Test import**

Run: `python -c "from src.codogram.keyboards import avatar_pack_create_keyboard; print(avatar_pack_create_keyboard())"`
Expected: prints InlineKeyboardMarkup object

**Step 4: Commit**

```bash
git add src/codogram/keyboards/avatar_pack.py src/codogram/keyboards/__init__.py
git commit -m "feat: add avatar pack keyboards"
```

---

### Task 6: Create StickerAdapter

**Files:**
- Create: `src/codogram/adapters/sticker.py`
- Modify: `src/codogram/adapters/__init__.py`

**Step 1: Create StickerAdapter**

Create `src/codogram/adapters/sticker.py`:
```python
"""Adapter for Telegram Sticker API.

Isolates Bot API from business logic for testability.
"""
import io
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker

from ..config import settings
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
```

**Step 2: Export from adapters/__init__.py**

Add to `src/codogram/adapters/__init__.py`:
```python
from .sticker import StickerAdapter, StickerInfo
```

**Step 3: Test import**

Run: `python -c "from src.codogram.adapters import StickerAdapter; print(StickerAdapter)"`
Expected: prints class

**Step 4: Commit**

```bash
git add src/codogram/adapters/sticker.py src/codogram/adapters/__init__.py
git commit -m "feat: add StickerAdapter for Telegram Sticker API"
```

---

### Task 7: Create EmojiPackService - image processing

**Files:**
- Create: `src/codogram/services/emoji_pack.py`

**Step 1: Create service with image processing methods**

Create `src/codogram/services/emoji_pack.py`:
```python
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
```

**Step 2: Test image processing**

Run: `python -c "
from src.codogram.services.emoji_pack import EmojiPackService
from aiogram.types import User

class FakeUser:
    id = 12345
    first_name = 'Test'

class FakeAdapter:
    async def download_user_avatar(self, user_id):
        return None

import asyncio
service = EmojiPackService(FakeAdapter())
result = service._generate_placeholder(FakeUser())
print(f'Generated {len(result)} bytes')
"`
Expected: `Generated XXXX bytes`

**Step 3: Commit**

```bash
git add src/codogram/services/emoji_pack.py
git commit -m "feat: add EmojiPackService with image processing"
```

---

### Task 8: Add pack creation methods to EmojiPackService

**Files:**
- Modify: `src/codogram/services/emoji_pack.py`

**Step 1: Add pack name generation and create_pack method**

Add to `EmojiPackService` class:
```python
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
```

**Step 2: Commit**

```bash
git add src/codogram/services/emoji_pack.py
git commit -m "feat: add pack creation methods to EmojiPackService"
```

---

### Task 9: Add pack management methods to EmojiPackService

**Files:**
- Modify: `src/codogram/services/emoji_pack.py`

**Step 1: Add add_member, remove_member, delete_pack methods**

Add to `EmojiPackService` class:
```python
    async def add_member(self, chat_id: int, user: User) -> str | None:
        """Add member's avatar to existing pack."""
        project = project_manager.get_by_chat(chat_id)
        if not project or not project.emoji_pack_name:
            return None

        # Check if already in pack
        if user.id in project.emoji_map:
            return project.emoji_map[user.id]

        emoji_id = await self._add_user_to_pack(project.emoji_pack_name, user, project)
        if emoji_id:
            project_manager._save()
        return emoji_id

    async def remove_member(self, chat_id: int, user_id: int) -> None:
        """Remove member's avatar from pack."""
        project = project_manager.get_by_chat(chat_id)
        if not project or not project.emoji_pack_name:
            return

        emoji_id = project.emoji_map.get(user_id)
        if not emoji_id:
            logger.debug(f"User {user_id} not in emoji_map for chat {chat_id}")
            return

        try:
            await self.adapter.remove_sticker(project.emoji_pack_name, emoji_id)
            del project.emoji_map[user_id]
            project_manager._save()
            logger.info(f"Removed user {user_id} from emoji pack")
        except Exception as e:
            logger.warning(f"Failed to remove user {user_id} from pack: {e}")

    async def delete_pack(self, chat_id: int) -> bool:
        """Delete entire pack and clear state."""
        project = project_manager.get_by_chat(chat_id)
        if not project or not project.emoji_pack_name:
            return False

        try:
            await self.adapter.delete_pack(project.emoji_pack_name)
            logger.info(f"Deleted emoji pack: {project.emoji_pack_name}")
        except Exception as e:
            logger.warning(f"Failed to delete pack (may not exist): {e}")

        # Clear state regardless
        project.emoji_pack_name = None
        project.emoji_map = {}
        project.feat_avatar_pack = False
        project_manager._save()
        return True

    def get_emoji_id(self, chat_id: int, user_id: int) -> str | None:
        """Get custom_emoji_id for user."""
        project = project_manager.get_by_chat(chat_id)
        if not project:
            return None
        return project.emoji_map.get(user_id)
```

**Step 2: Commit**

```bash
git add src/codogram/services/emoji_pack.py
git commit -m "feat: add pack management methods to EmojiPackService"
```

---

### Task 10: Add /exp_avatar_pack command handler

**Files:**
- Modify: `src/codogram/handlers/settings.py`

**Step 1: Add command handler and callback handlers**

Add imports at top:
```python
from ..adapters.sticker import StickerAdapter
from ..services.emoji_pack import EmojiPackService
from ..keyboards import avatar_pack_create_keyboard, avatar_pack_disable_keyboard
from .. import strings
```

Add handlers:
```python
@router.message(Command("exp_avatar_pack"))
async def cmd_exp_avatar_pack(message: Message, telegram_queue: TelegramQueue):
    """Toggle avatar pack feature."""
    chat_id = message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    if project.feat_avatar_pack:
        kb = avatar_pack_disable_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_DISABLE_PROMPT, reply_markup=kb)
    else:
        kb = avatar_pack_create_keyboard()
        await telegram_queue.reply(message, strings.EMOJI_PACK_CREATE_PROMPT, reply_markup=kb)


@router.callback_query(F.data.startswith("avatar_pack:"))
async def callback_avatar_pack(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle avatar pack button presses."""
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    if action == "cancel":
        await telegram_queue.edit(callback.message, strings.CANCELLED)
        await callback.answer()
        return

    # Create service with adapter (layered architecture)
    adapter = StickerAdapter(callback.bot)
    service = EmojiPackService(adapter)

    if action == "create":
        await telegram_queue.edit(callback.message, strings.EMOJI_PACK_CREATING)
        await callback.answer()

        thread_id = callback.message.message_thread_id

        # Get participants (admins for now, members added on join)
        try:
            admins = await callback.bot.get_chat_administrators(chat_id)
            participants = [admin.user for admin in admins if not admin.user.is_bot]
        except Exception as e:
            await telegram_queue.send(
                chat_id, strings.EMOJI_PACK_ERROR.format(error=str(e)), thread_id=thread_id
            )
            return

        # Create pack
        pack_name = await service.create_pack(chat_id, participants)
        if pack_name:
            pack_link = f"t.me/addemoji/{pack_name}"
            await telegram_queue.send(
                chat_id,
                strings.EMOJI_PACK_CREATED.format(pack_link=pack_link),
                thread_id=thread_id,
            )
        else:
            await telegram_queue.send(
                chat_id, strings.EMOJI_PACK_ERROR.format(error="Unknown error"), thread_id=thread_id
            )

    elif action == "disable":
        await telegram_queue.edit(callback.message, strings.EMOJI_PACK_DELETED)
        await callback.answer()
        await service.delete_pack(chat_id)
```

**Step 2: Test command is registered**

Run bot: `./dev-run.sh`
Send: `/exp_avatar_pack` in test chat
Expected: shows create/disable prompt based on state

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: add /exp_avatar_pack command and callbacks"
```

---

### Task 11: Add emoji pack creation on migration

**Files:**
- Modify: `src/codogram/handlers/migration.py`

**Step 1: Add async pack creation on migration**

Add imports at top of file:
```python
import asyncio

from aiogram import Bot

from ..adapters.sticker import StickerAdapter
from ..logging_config import logger
from ..services.emoji_pack import EmojiPackService
from ..telegram_queue import TelegramQueue, OutgoingBatch
from .. import strings
```

Add background task function and modify handler:
```python
async def _create_emoji_pack_background(bot: Bot, chat_id: int, telegram_queue: TelegramQueue) -> None:
    """Create emoji pack in background after migration."""
    try:
        # Wait a bit for migration to complete
        await asyncio.sleep(2)

        # Get participants (admins for now)
        admins = await bot.get_chat_administrators(chat_id)
        participants = [admin.user for admin in admins if not admin.user.is_bot]

        if not participants:
            logger.warning(f"No participants for emoji pack in chat {chat_id}")
            return

        # Create service with adapter (layered architecture)
        adapter = StickerAdapter(bot)
        service = EmojiPackService(adapter)
        pack_name = await service.create_pack(chat_id, participants)

        if pack_name:
            pack_link = f"t.me/addemoji/{pack_name}"
            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=None,
                messages=[{"text": strings.EMOJI_PACK_CREATED.format(pack_link=pack_link)}],
            )
            await telegram_queue.enqueue(batch)
            logger.info(f"Emoji pack created on migration: {pack_name}")
    except Exception as e:
        logger.error(f"Failed to create emoji pack on migration: {e}")
```

In `on_chat_migration`, after sending MIGRATION_MESSAGE, add:
```python
    # Create emoji pack asynchronously
    asyncio.create_task(
        _create_emoji_pack_background(message.bot, new_chat_id, telegram_queue)
    )
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/migration.py
git commit -m "feat: auto-create emoji pack on migration"
```

---

### Task 12: Add member join/leave handlers

**Files:**
- Create: `src/codogram/handlers/members.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create members handler**

Create `src/codogram/handlers/members.py`:
```python
"""Handler for member join/leave events."""
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..adapters.sticker import StickerAdapter
from ..session_manager import project_manager
from ..services.emoji_pack import EmojiPackService
from ..logging_config import logger

router = Router(name="members")


def _is_join(event: ChatMemberUpdated) -> bool:
    """Check if event is a member join."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    return old in ("left", "kicked", "restricted") and new in ("member", "administrator", "creator")


def _is_leave(event: ChatMemberUpdated) -> bool:
    """Check if event is a member leave."""
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    return old in ("member", "administrator", "creator") and new in ("left", "kicked")


@router.chat_member()
async def on_member_update(event: ChatMemberUpdated) -> None:
    """Handle member join/leave for emoji pack updates."""
    project = project_manager.get_by_chat(event.chat.id)
    if not project or not project.feat_avatar_pack:
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    # Create service with adapter (layered architecture)
    adapter = StickerAdapter(event.bot)
    service = EmojiPackService(adapter)

    if _is_join(event):
        logger.info(f"Member joined, adding to emoji pack: {user.id}")
        await service.add_member(event.chat.id, user)

    elif _is_leave(event):
        logger.info(f"Member left, removing from emoji pack: {user.id}")
        await service.remove_member(event.chat.id, user.id)
```

**Step 2: Register router in handlers/__init__.py**

Add import and include router:
```python
from . import members
# In register_handlers function:
dp.include_router(members.router)
```

**Step 3: Enable chat_member updates in main.py**

In `main.py:88`, update `start_polling` to include `chat_member` updates:
```python
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])
```

Without this, aiogram won't receive `ChatMemberUpdated` events and the handlers won't fire.

**Step 4: Commit**

```bash
git add src/codogram/handlers/members.py src/codogram/handlers/__init__.py src/codogram/main.py
git commit -m "feat: add member join/leave handlers for emoji pack"
```

---

### Task 13: Update /settings to show feat_avatar_pack

**Files:**
- Modify: `src/codogram/handlers/settings.py`

**Step 1: Update _build_settings_text function**

Find the experimental features section and add avatar_pack:
```python
    # Experimental features
    feat_thinking = thread.feat_thinking_status if thread else project.feat_thinking_status
    feat_suggestions = thread.feat_suggestions if thread else project.feat_suggestions
    feat_avatar_pack = project.feat_avatar_pack  # Project-level only
    thinking_status = "● on" if feat_thinking else "○ off"
    suggestions_status = "● on" if feat_suggestions else "○ off"
    avatar_pack_status = "● on" if feat_avatar_pack else "○ off"

    # ... later in the function:
    lines.append("experimental features")
    lines.append(f"• /exp\\_thinking\\_status: {thinking_status}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")
    lines.append(f"• /exp\\_avatar\\_pack: {avatar_pack_status}")
```

**Step 2: Test settings display**

Run bot, send `/settings`
Expected: shows `• /exp_avatar_pack: ○ off` in experimental features

**Step 3: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: show feat_avatar_pack in /settings"
```

---

### Task 14: Add emoji pack hint to topic launch message

**Prerequisite:** Сообщения /start унифицированы. Структура сообщений:

| Сценарий | Сообщение |
|----------|-----------|
| /start в General (первый запуск) | Полное: проект + команды + tmux |
| /start в General (уже запущен) | Короткое: "Already running" + tmux |
| Миграция в супергруппу | Полное |
| Создание нового топика | **Короткое + emoji hint** ← сюда добавляем |
| /start в топике (resume) | Короткое |
| /start в топике (уже активен) | Короткое |

**Files:**
- Modify: `src/codogram/strings.py`
- Modify: `src/codogram/launch_animation.py` (или где формируется сообщение для топика)

**Step 1: Add emoji pack hint string**

In `strings.py`, строка уже добавлена в Task 4:
```python
EMOJI_PACK_TOPIC_HINT = "→ Check this [pack]({pack_link}) to personalize your topic"
```

**Step 2: Append hint to topic launch message**

In `launch_animation.py:189-191`, after `build_thread_announcement()`:

```python
        else:
            # Topic - short announcement
            announcement = build_thread_announcement(thread.name, tmux_name)
            # Add emoji pack hint if feature enabled
            if project.feat_avatar_pack and project.emoji_pack_name:
                pack_link = f"https://t.me/addemoji/{project.emoji_pack_name}"
                announcement += f"\n\n{strings.EMOJI_PACK_TOPIC_HINT.format(pack_link=pack_link)}"
```

**Условия показа hint** (внутри `else` ветки, т.е. уже в топике):
- `project.feat_avatar_pack` — фича включена
- `project.emoji_pack_name` — pack существует

**Step 3: Test**

1. Enable: `/exp_avatar_pack` → "Yes, create"
2. Create topic: `/thread_create test`
3. Verify: message ends with "→ Check this pack..."
4. Test without pack: disable, create topic, verify no hint

**Step 4: Commit**

```bash
git add src/codogram/strings.py src/codogram/launch_animation.py
git commit -m "feat: show emoji pack hint in topic launch message"
```

---

### Task 15: E2E Testing

**Files:**
- Test specs: `docs/e2e/commands/avatar_pack.md`
- Suites: `docs/e2e/suites/critical.md` (TC-AVATAR-001..007)

**Step 1: Run critical avatar pack tests**

Follow `docs/e2e/CLAUDE.md` guide. Run tests TC-AVATAR-001 through TC-AVATAR-007:

| Test | Description |
|------|-------------|
| TC-AVATAR-001 | /exp_avatar_pack shows create prompt when OFF |
| TC-AVATAR-002 | Create avatar pack via button |
| TC-AVATAR-003 | /exp_avatar_pack shows disable prompt when ON |
| TC-AVATAR-005 | Disable avatar pack via button |
| TC-AVATAR-006 | /settings shows avatar_pack status |
| TC-AVATAR-007 | Topic launch shows emoji hint when pack enabled |

**Step 2: Run full suite tests (optional)**

Additional tests from `docs/e2e/suites/full.md`:
- TC-AVATAR-004: Cancel keeps pack enabled
- TC-AVATAR-008: Topic launch NO hint when disabled
- TC-AVATAR-009: Member join adds to pack (ASK USER)
- TC-AVATAR-010: Member leave removes from pack (ASK USER)
- TC-AVATAR-011: "Not now" cancels create
- TC-AVATAR-012: Pack link is valid (ASK USER)

**Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: avatar emoji pack feature complete"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add Pillow dependency | pyproject.toml |
| 2 | Add bot_owner_id config | config.py |
| 3 | Add emoji pack fields to ProjectState | session_manager.py |
| 4 | Add emoji pack strings | strings.py |
| 5 | Create avatar pack keyboards | keyboards/avatar_pack.py |
| 6 | Create StickerAdapter | adapters/sticker.py |
| 7 | Create EmojiPackService - image processing | services/emoji_pack.py |
| 8 | Add pack creation methods | services/emoji_pack.py |
| 9 | Add pack management methods | services/emoji_pack.py |
| 10 | Add /exp_avatar_pack command | handlers/settings.py |
| 11 | Add migration trigger | handlers/migration.py |
| 12 | Add member join/leave handlers | handlers/members.py |
| 13 | Update /settings display | handlers/settings.py |
| 14 | Add emoji pack hint to launch message | launch_animation.py, strings.py |
| 15 | E2E Testing | - |
