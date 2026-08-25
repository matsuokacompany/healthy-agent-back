from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_RUNTIME_ROLE: str = "healthy_agent_api"

    OPENAI_API_KEY: Optional[str] = None
    AI_REPORT_PREVIEW_SECRET: Optional[str] = None
    AI_REPORT_MODEL: str = "gpt-4o-mini"
    AI_REPORT_MAX_INPUT_TOKENS: int = 2000
    AI_REPORT_MAX_OUTPUT_TOKENS: int = 500
    AI_REPORT_MAX_COST_USD: float = 0.05
    AI_REPORT_INPUT_COST_PER_MILLION_USD: Optional[float] = None
    AI_REPORT_OUTPUT_COST_PER_MILLION_USD: Optional[float] = None

    # Clinical field encryption. The AWS credentials must come from the EC2
    # instance role; never configure long-lived AWS access keys here.
    CLINICAL_ENCRYPTION_PROVIDER: str = "disabled"
    CLINICAL_ENCRYPTION_KMS_KEY_ID: Optional[str] = None
    CLINICAL_ENCRYPTION_AWS_REGION: Optional[str] = None
    CLINICAL_ENCRYPTION_ACTIVE_KEY_VERSION: str = "v1"
    CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED: bool = True

    USER_ID: int = 1
    ENV: str = "dev"
    DEBUG: bool = False

    # Supabase Auth JWT validation. Prefer JWKS/asymmetric signing keys in production.
    SUPABASE_PROJECT_URL: Optional[str] = None
    SUPABASE_JWKS_URL: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ISSUER: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "clinical-images"
    CLINICAL_IMAGES_ENABLED: bool = False
    WHATSAPP_CLINICAL_IMAGES_ENABLED: bool = False
    PORTAL_CLINICAL_IMAGES_ENABLED: bool = False
    CLINICAL_IMAGE_MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    CLINICAL_IMAGE_MAX_STORED_PER_PATIENT: int = 30
    CLINICAL_IMAGE_MAX_PORTAL_BATCH: int = 3
    CLINICAL_IMAGE_MAX_DIMENSION: int = 1600
    CLINICAL_IMAGE_MAX_PIXELS: int = 25_000_000
    CLINICAL_IMAGE_JPEG_QUALITY: int = 80
    CLINICAL_IMAGE_SIGNED_URL_TTL_SECONDS: int = 300
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_ACCESS_COOKIE_NAME: str = "__Host-ha_access"
    AUTH_REFRESH_COOKIE_NAME: str = "__Host-ha_refresh"
    AUTH_CSRF_COOKIE_NAME: str = "ha_csrf"
    AUTH_CSRF_HEADER_NAME: str = "X-CSRF-Token"
    AUTH_REDIRECT_ALLOWLIST: str = "http://localhost:3000,https://app.julha.com.br"

    SCHEDULER_TIMEZONE: str = "UTC"

    SCHEDULER_MORNING_HOUR: int = 8
    SCHEDULER_MORNING_MINUTE: int = 0

    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_ACCESS_TOKEN: str
    WHATSAPP_DAILY_TEMPLATE_NAME: str
    APP_SECRET: Optional[str] = None

    # Asaas billing for the self-service (B2C) monitoring subscription.
    # ASAAS_ENV selects the API base URL; use "sandbox" until the integration
    # is verified end-to-end. ASAAS_WEBHOOK_TOKEN is the value you set when
    # registering the webhook URL in the Asaas dashboard (Configurações >
    # Integrações > Webhooks) — Asaas echoes it back on every webhook call for
    # verification. ASAAS_SELF_MONITORING_PRICE_CENTS has no default on
    # purpose: pricing must be an explicit decision, not a guessed default.
    ASAAS_API_KEY: Optional[str] = None
    ASAAS_ENV: str = "sandbox"
    ASAAS_WEBHOOK_TOKEN: Optional[str] = None
    ASAAS_SELF_MONITORING_PRICE_CENTS: Optional[int] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
