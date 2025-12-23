from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_token: str
    chat_id: int  # Single chat for R1
    project_dir: str  # e.g. /home/user/dev/my-project
    tmux_session: str = "claude-bridge"

    class Config:
        env_file = ".env"

settings = Settings()
