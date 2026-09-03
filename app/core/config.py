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
    # This API's own public origin (e.g. https://api.julha.com.br) — distinct
    # from AUTH_REDIRECT_ALLOWLIST, which lists allowed *frontend* origins.
    # Used only to build the redirect_to sent to Supabase for signup/password
    # recovery links, so Supabase redirects the browser back to this API's
    # own GET /api/auth/callback (not the frontend, which has no such route)
    # after it confirms the email/verifies the recovery code. Optional so a
    # missing value degrades to Supabase's own default Site URL instead of
    # crashing the app on startup.
    API_PUBLIC_URL: Optional[str] = None

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
    # Same "no default" rule as the monthly price above: each plan only shows
    # up in GET /api/billing/plans once its price is explicitly configured.
    ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS: Optional[int] = None
    ASAAS_SELF_MONITORING_ANNUAL_PRICE_CENTS: Optional[int] = None
    ASAAS_SELF_MONITORING_TRIAL_DAYS: int = 30

    # SMTP for backend-originated transactional email (e.g. patient link
    # request notifications) — separate from Supabase Auth's own SMTP
    # settings (which only cover Supabase's own auth emails), even though in
    # practice both point at the same mailbox. Same Hostinger account, port
    # 465 (implicit SSL), matching what's already verified working there.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 465
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SUPPORT_CONTACT_EMAIL: str = "contato@julha.com.br"

    # Asaas billing for PROFESSIONAL accounts — a separate catalog/pricing
    # from the patient self-service plans above. Same "no default" rule: a
    # plan only shows up once its price is explicitly configured. Existing
    # professional accounts (as of this feature's rollout) are grandfathered
    # with free access via ProfessionalProfile.free_until; new signups have
    # no trial and must subscribe to keep full platform access.
    # Base tier (up to 10 simultaneously active patients).
    ASAAS_PROFESSIONAL_MONTHLY_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_SEMIANNUAL_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_ANNUAL_PRICE_CENTS: Optional[int] = None
    # Up to 25 simultaneously active patients.
    ASAAS_PROFESSIONAL_TIER25_MONTHLY_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_TIER25_SEMIANNUAL_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_TIER25_ANNUAL_PRICE_CENTS: Optional[int] = None
    # Up to 50 simultaneously active patients.
    ASAAS_PROFESSIONAL_TIER50_MONTHLY_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_TIER50_SEMIANNUAL_PRICE_CENTS: Optional[int] = None
    ASAAS_PROFESSIONAL_TIER50_ANNUAL_PRICE_CENTS: Optional[int] = None

    # No default on purpose (same rule as the Asaas prices above): Meta's
    # actual per-message WhatsApp charge isn't available anywhere in this
    # app, so the admin cost dashboard only estimates it once this is set
    # explicitly — it never guesses a rate. float (not int): most of Julha's
    # WhatsApp traffic falls inside Meta's free service-conversation window,
    # so the real blended cost per message sent is well under one cent
    # (e.g. R$0,0007) — an integer-cents field would always round that to 0.
    WHATSAPP_COST_PER_MESSAGE_CENTS: Optional[float] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
