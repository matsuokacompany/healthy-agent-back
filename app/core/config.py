from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    OPENAI_API_KEY: Optional[str] = None
    AI_REPORT_PREVIEW_SECRET: Optional[str] = None
    AI_REPORT_MODEL: str = "gpt-4o-mini"
    AI_REPORT_MAX_INPUT_TOKENS: int = 2000
    AI_REPORT_MAX_OUTPUT_TOKENS: int = 500
    AI_REPORT_MAX_COST_USD: float = 0.05
    AI_REPORT_INPUT_COST_PER_MILLION_USD: Optional[float] = None
    AI_REPORT_OUTPUT_COST_PER_MILLION_USD: Optional[float] = None

    USER_ID: int = 1
    ENV: str = "dev"
    DEBUG: bool = False

    # Supabase Auth JWT validation. Prefer JWKS/asymmetric signing keys in production.
    SUPABASE_PROJECT_URL: Optional[str] = None
    SUPABASE_JWKS_URL: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ISSUER: Optional[str] = None

    SCHEDULER_TIMEZONE: str = "UTC"

    SCHEDULER_MORNING_HOUR: int = 8
    SCHEDULER_MORNING_MINUTE: int = 0

    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_ACCESS_TOKEN: str
    WHATSAPP_DAILY_TEMPLATE_NAME: str
    APP_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
