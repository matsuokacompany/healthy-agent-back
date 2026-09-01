# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

FastAPI backend for a clinical monitoring SaaS MVP ("Julha"). Patients receive daily WhatsApp check-ins via WhatsApp Cloud API; an APScheduler job creates pending `DailyReport`s, the WhatsApp webhook collects the patient's response through a bot conversation flow, and professionals/admins review reports and OpenAI/LangChain-generated insights. Auth is Supabase Auth (JWT), with Postgres Row Level Security as defense-in-depth. Database is Supabase PostgreSQL in production; tests use in-memory SQLite.

Most substantive docs live in `docs/`: `docs/security.md` (RLS, runtime DB role, clinical field encryption/rotation), `docs/auth_supabase.md`, `docs/clinical-images-mvp.md`, `docs/custom-ai-reports.md`. Read the relevant one before touching auth, encryption, or clinical images.

## Commands

```bash
# install
pip install -r requirements.txt

# run dev server (needs .env or .env.dev with DATABASE_URL etc. — see README for the full variable table)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# local Postgres via docker compose
docker compose -f docker-compose.dev.yml up --build

# migrations (single baseline at alembic/versions/0001_base_schema.py)
alembic upgrade head
alembic revision -m "description"          # new migration

# tests (SQLite in-memory, no external services needed for most tests)
pytest -q
pytest app/tests/test_daily_report_service.py -q      # single file
pytest app/tests/test_daily_report_service.py::test_daily_report_expired -q   # single test
```

There is no configured lint/format command in this repo (no ruff/flake8/black config present) — don't assume one.

## Architecture

**Layering**: `routes/` (FastAPI routers, one per resource) → `services/` (business logic, static-method style classes, e.g. `DailyReportService`) → `models/models.py` (SQLAlchemy ORM) + `models/schemas.py` (Pydantic). `db/repositories/` holds a couple of query-only repository classes for anamnese/daily-report lookups. Routes are mounted in `app/main.py` under `/api/<resource>` (patient dashboard is the exception, mounted at `/patient`).

**Auth flow** (`app/core/auth.py`): Supabase issues the JWT; the API verifies it (HS256 via `SUPABASE_JWT_SECRET` or RS/ES256 via Supabase's JWKS endpoint, cached with `lru_cache`) and lazily creates/links a local `User` row keyed by `supabase_user_id`. Access/refresh/CSRF tokens are set as cookies (`AUTH_ACCESS_COOKIE_NAME`, `AUTH_REFRESH_COOKIE_NAME`, `AUTH_CSRF_COOKIE_NAME`); a global CSRF+origin-check middleware in `app/main.py` guards unsafe methods under `/api`, with `/api/auth/login`, `/api/auth/forgot-password`, `/api/auth/callback` exempted. `get_current_user` accepts either the access cookie or a bearer token. Route-level authorization on top of authentication goes through `app/core/permissions.py` (role checks) and `app/core/access_policy.py` (`AccessPolicy` — patient-scoped resource authorization, e.g. `require_patient_read` walks the `MonitoringPlan`/`MonitoringProfessional` link to authorize a professional against a specific patient).

**Database identity & RLS** (`app/db/security_context.py`, `docs/security.md`): every authenticated request calls `set_database_identity_context(db, supabase_user_id, email)`, which does a transactional `SET LOCAL app.supabase_user_id`/`app.user_email` — Postgres RLS policies key off these. Because `SET LOCAL` doesn't survive a commit, an `after_begin` SQLAlchemy event re-applies the context on the next transaction of the same pooled session; watch for this when a service does its own `db.commit()` mid-request. Background/system code (scheduler, WhatsApp webhook, maintenance scripts) uses `set_database_service_context(db, "...")` instead of impersonating a user — never fabricate a user identity for internal jobs. The app DB connection runs as the unprivileged `DATABASE_RUNTIME_ROLE` Postgres role (`SET ROLE` on connect, see `app/db/session.py`), not the migration owner.

**Clinical field encryption**: envelope encryption (AES-256-GCM, AWS KMS-wrapped data keys) for sensitive clinical columns, gated by `CLINICAL_ENCRYPTION_PROVIDER`/`CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED`. `app/core/clinical_encryption.py` is the primitive; `app/scripts/clinical_encryption_*.py` are the operational backfill/verify/rotate/cleanup scripts, each with a dry-run-by-default `--execute` flag. Full rollout/rotation runbook is in `docs/security.md` — follow it exactly (preflight → canary → full batch → verify) rather than improvising when touching this area; a bad rotation is not easily reversible.

**Bot channels**: `app/bot/channels/base.py` defines `BaseBotChannel`; `BotManager` registers named channels. Only `whatsapp` is registered in `app/main.py`'s lifespan — Telegram-shaped abstractions exist but have no live implementation. `app/bot/scheduler.py` (APScheduler) creates pending `DailyReport`s for active plans within `start_date`/`end_date` for patients with a phone number; `app/services/bot_service.py` resolves an inbound WhatsApp message to a `User` by phone and hands off to `DailyReportService` to advance the report's state machine (`DailyReportStatusEnum`). The positive-symptom flow was deliberately shortened to one question + confirmation to reduce paid WhatsApp messages — see README "Otimização de custo do WhatsApp" before adding new bot prompts.

**AI report generation** (`app/services/ai_report_*`, `app/services/custom_report_*`): calls OpenAI with hard caps (`AI_REPORT_MAX_INPUT_TOKENS`/`MAX_OUTPUT_TOKENS`/`MAX_COST_USD`) and truncates report input to 6000 chars to bound cost; the professional-facing generation path reuses the first AI report already produced that week per patient rather than regenerating. `AI_REPORT_PREVIEW_SECRET` signs short-lived (15 min) custom report preview links — it's a separate secret from `SECRET_KEY`/JWT signing, don't conflate them.

**Entity model**: `User` 1:1 `Anamnese`, 1:N `MonitoringPlan`, 1:N `DailyReport`, 1:1 `ProfessionalProfile`; `MonitoringPlan` N:N `ProfessionalProfile` via `MonitoringProfessional`. See `app/models/models.py` for enums (`CheckTypeEnum`, `DailyReportStatusEnum`, `RoleNameEnum`, etc.) — role-based authorization always goes through `RoleNameEnum`/`app/core/permissions.py`, not string comparison.

## Testing conventions

Tests build their own isolated SQLAlchemy engine per test — either a plain in-memory `create_engine("sqlite:///:memory:")` (service-level tests) or `create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)` plus a `TestClient` with `app.dependency_overrides[get_db]`/`app.dependency_overrides[get_current_user]` (route-level tests). There is no shared `conftest.py`; each test module defines its own `build_session()`/`build_client()` helper and fixtures inline (see `app/tests/test_daily_report_service.py` and `app/tests/test_daily_reports_routes.py`). Route tests mount only the router under test on a bare `FastAPI()` instance rather than importing the full `app.main.app`. When a test needs Postgres-only behavior (RLS, `SET ROLE`), check `test_model_dialect_compatibility.py` and the `clinical_encryption`/`security_context` test files for the pattern used to skip or dialect-guard on SQLite.

## Deployment

`main` auto-deploys to a single EC2 instance via `.github/workflows/deploy.yml` (no staging environment) — it checks out via `git archive`/API instead of Marketplace actions, **builds the Docker image on the GitHub Actions runner and pushes it to GHCR** (`ghcr.io/matsuokacompany/healthy-agent-back`), then the EC2 side only `docker compose pull`s that image and restarts — it never builds locally. This split exists because the production instance is small enough that building there (gcc, pip install, etc.) has previously exhausted its memory and taken it down; don't reintroduce `docker compose up --build` on the EC2 side. `alembic upgrade head` still runs on container start (in the image's `CMD`), and the workflow still verifies the container stayed up. Production Postgres is Supabase, not a container. Secrets live in the GitHub `production` environment (`PRODUCTION_ENV` is the full `.env` contents, `GHCR_PULL_TOKEN` is a PAT with `read:packages` the EC2 instance uses to pull the image) — see README for the exact variable list and where each secret comes from.
