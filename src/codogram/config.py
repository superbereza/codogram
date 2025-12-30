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

    def get_admin_ids(self) -> set[int]:
        """Parse admin_ids string into set of ints."""
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}

settings = Settings()

# Config file path
CONFIG_PATH = Path(__file__).parent.parent.parent / ".config.json"

def load_config() -> dict:
    """Load .config.json or return default."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"projects": {}}

def save_config(config: dict) -> None:
    """Save config to .config.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
