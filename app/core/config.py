from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    OPENAI_API_KEY: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    USER_ID: int = 1
    ENV: str = "dev"
    DEBUG: bool = False

    SECRET_KEY: str

    SCHEDULER_TIMEZONE: str = "UTC"

    SCHEDULER_MORNING_HOUR: int = 8
    SCHEDULER_MORNING_MINUTE: int = 0


    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_ACCESS_TOKEN: str
    WHATSAPP_DAILY_TEMPLATE_NAME: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # <- IMPORTANTE
    )


settings = Settings()