# src/codogram/config.py
import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        return json.loads(CONFIG_PATH.read_text())
    return {"projects": {}}

def save_config(config: dict) -> None:
    """Save config to ~/.codogram/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
