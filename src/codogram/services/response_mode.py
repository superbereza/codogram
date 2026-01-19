"""Response mode filtering service."""

from dataclasses import dataclass


@dataclass
class FilterResult:
    """Result of response mode filtering."""
    should_respond: bool
    reason: str


class ResponseModeService:
    """Service to determine if bot should respond based on response mode."""

    VALID_MODES = ("all", "polite", "mentions")

    def __init__(self, bot_id: int, bot_username: str):
        self.bot_id = bot_id
        self.bot_username = bot_username.lower().lstrip("@")

    def should_respond(
        self,
        mode: str,
        text: str | None,
        entities: list | None,
        reply_to_user_id: int | None,
    ) -> FilterResult:
        """Check if bot should respond based on response mode."""
        text = text or ""
        entities = entities or []

        # Fallback for invalid mode
        if mode not in self.VALID_MODES:
            return FilterResult(True, "invalid mode, default allow")

        if mode == "all":
            return FilterResult(True, "mode=all")

        # Media-only messages (no text, no entities) - always respond
        # Can't contain mentions, so bypass filter
        if not text and not entities:
            return FilterResult(True, "media-only message")

        has_bot_mention = self._has_bot_mention(text, entities)
        is_reply_to_bot = reply_to_user_id == self.bot_id if reply_to_user_id else False

        if mode == "mentions":
            if has_bot_mention or is_reply_to_bot:
                return FilterResult(True, "mentioned or replied to bot")
            return FilterResult(False, "not mentioned")

        if mode == "polite":
            has_other_mention = self._has_other_mention(text, entities)
            is_reply_to_other = reply_to_user_id is not None and reply_to_user_id != self.bot_id

            if (has_other_mention or is_reply_to_other) and not has_bot_mention:
                return FilterResult(False, "directed at others")
            return FilterResult(True, "general message")

        return FilterResult(True, "unknown mode")

    def _has_bot_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions the bot."""
        from aiogram.enums import MessageEntityType

        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip("@")
                if mention == self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id == self.bot_id:
                    return True
        return False

    def _has_other_mention(self, text: str, entities: list) -> bool:
        """Check if message mentions someone other than the bot."""
        from aiogram.enums import MessageEntityType

        for entity in entities:
            if entity.type == MessageEntityType.MENTION:
                mention = text[entity.offset:entity.offset + entity.length].lower().lstrip("@")
                if mention != self.bot_username:
                    return True
            elif entity.type == MessageEntityType.TEXT_MENTION:
                if entity.user and entity.user.id != self.bot_id:
                    return True
        return False
