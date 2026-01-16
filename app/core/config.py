from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str
    OPENAI_API_KEY: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    USER_ID: int = 1
    ENV: str = "dev"
    SECRET_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()
