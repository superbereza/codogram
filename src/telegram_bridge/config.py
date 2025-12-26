# src/telegram_bridge/config.py
import json
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_token: str
    admin_ids: str  # Comma-separated list of admin user IDs
    base_dir: str  # e.g. /home/user/dev

    class Config:
        env_file = ".env"

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
