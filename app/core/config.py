from pydantic import BaseSettings
from pathlib import Path
from typing import Optional

class Settings(BaseSettings):
    # default: sqlite local in project/data/ (production will override DATABASE_URL)
    DATABASE_URL: str
    OPENAI_API_KEY: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    USER_ID: int = 1
    ENV: str = "dev"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
