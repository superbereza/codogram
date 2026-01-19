# src/codogram/config.py
import json
from datetime import datetime
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Telegram limits
TELEGRAM_MESSAGE_MAX_LENGTH = 4000

# Screen parsing
SCREEN_SEPARATOR_MIN_DASHES = 10

# Tmux capture
TMUX_CAPTURE_LINES_DEFAULT = 30

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    telegram_token: str
    admin_ids: str  # Comma-separated list of admin user IDs
    base_dir: str  # e.g. /home/user/dev
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Timing constants (seconds)
    permission_poller_debounce: float = 0.5
    permission_poller_interval: float = 0.5
    history_watcher_interval: int = 15
    session_binding_timeout: int = 300
    session_binding_interval: float = 0.5
    jsonl_watcher_interval: float = 0.5
    claude_launch_timeout: int = 120
    project_cleanup_days: int = 30

    # OpenAI / Whisper
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    whisper_timeout: int = 60  # seconds

    def get_admin_ids(self) -> set[int]:
        """Parse admin_ids string into set of ints."""
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}

    def get_bot_owner_id(self) -> int:
        """First admin is considered bot owner for sticker pack ownership."""
        admin_ids = self.get_admin_ids()
        if not admin_ids:
            raise ValueError("No admin IDs configured")
        return min(admin_ids)  # First by ID for consistency

settings = Settings()

# Config file path - in ~/.codogram/ to avoid worktree issues
CONFIG_DIR = Path.home() / ".codogram"
CONFIG_PATH = CONFIG_DIR / "config.json"

def get_config_path() -> Path:
    """Return the config file path, ensuring parent directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_PATH

def load_config() -> dict:
    """Load config.json or return default."""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
        # Ensure users key exists for backward compatibility
        if "users" not in config:
            config["users"] = {}
        return config
    return {"projects": {}, "users": {}}

def save_config(config: dict) -> None:
    """Save config to ~/.codogram/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


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


def get_user_onboarded(user_id: int) -> bool:
    """Check if user has completed onboarding."""
    config = load_config()
    user_data = config.get("users", {}).get(str(user_id), {})
    return user_data.get("onboarded", False)


def set_user_onboarded(user_id: int) -> None:
    """Mark user as onboarded."""
    config = load_config()
    if "users" not in config:
        config["users"] = {}
    config["users"][str(user_id)] = {
        "onboarded": True,
        "onboarded_at": datetime.now().isoformat()
    }
    save_config(config)
