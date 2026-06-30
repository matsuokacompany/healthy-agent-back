# Julha Backend API

Backend FastAPI para um MVP SaaS de monitoramento clínico com Supabase PostgreSQL, WhatsApp Cloud API, APScheduler, autenticação JWT/refresh tokens, anamneses, daily reports e geração de insights com OpenAI/LangChain.

## Arquitetura

```text
Clientes/Web/App
   |
FastAPI API
   |-- Auth/JWT/Refresh Tokens
   |-- Users/Anamnese
   |-- Monitoring Plans/Professionals
   |-- Daily Reports
   |-- Insights OpenAI
   |-- WhatsApp Webhook
   |
Supabase PostgreSQL

APScheduler -> cria DailyReport pendente -> WhatsApp Cloud API -> paciente responde -> DailyReport é concluído
```

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Supabase PostgreSQL via `DATABASE_URL`
- WhatsApp Cloud API
- APScheduler
- OpenAI/LangChain
- Docker / Docker Compose

## Entidades principais

```text
User
├── 1:1 Anamnese
├── 1:N MonitoringPlan
├── 1:N DailyReport
├── 1:1 ProfessionalProfile
└── 1:N RefreshToken

MonitoringPlan
├── N:1 User (patient)
├── 1:N DailyReport
└── N:N ProfessionalProfile via MonitoringProfessional

ProfessionalProfile
└── N:N MonitoringPlan via MonitoringProfessional

DailyReport
├── N:1 User
└── N:1 MonitoringPlan
```

## Variáveis de ambiente

Crie `.env` em produção e `.env.dev` em desenvolvimento.

| Variável | Obrigatória | Exemplo | Descrição |
| --- | --- | --- | --- |
| `ENV` | não | `production` | Ambiente da aplicação. |
| `DATABASE_URL` | sim | `postgresql+psycopg2://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require` | URL do Supabase PostgreSQL. |
| `SECRET_KEY` | sim | `change-me` | Segredo JWT legado. |
| `SUPABASE_PROJECT_URL` | sim | `https://<PROJECT_REF>.supabase.co` | URL do projeto Supabase usada para validar o issuer `https://<PROJECT_REF>.supabase.co/auth/v1`. |
| `SUPABASE_JWT_SECRET` | sim | `<supabase-jwt-secret>` | JWT secret do Supabase usado para validar access tokens `HS256`. |
| `SUPABASE_JWT_AUDIENCE` | não | `authenticated` | Audience exigida nos access tokens do Supabase. |
| `SUPABASE_JWT_ISSUER` | não | `https://<PROJECT_REF>.supabase.co/auth/v1` | Issuer customizado; por padrão é derivado de `SUPABASE_PROJECT_URL`. |
| `OPENAI_API_KEY` | não | `sk-...` | Chave OpenAI para insights. |
| `CORS_ORIGINS` | não | `http://localhost:3000,https://app.julha.com.br` | Origens permitidas no CORS, separadas por vírgula. O padrão já inclui `http://localhost:3000` e `https://app.julha.com.br`. |
| `WHATSAPP_VERIFY_TOKEN` | sim | `verify-token` | Token de verificação do webhook Meta. |
| `WHATSAPP_PHONE_NUMBER_ID` | sim | `123456789` | Phone Number ID da Meta. |
| `WHATSAPP_ACCESS_TOKEN` | sim | `EAA...` | Token WhatsApp Cloud API. |
| `WHATSAPP_DAILY_TEMPLATE_NAME` | sim | `daily_symptom_checkin` | Template de check-in aprovado na Meta. |
| `APP_SECRET` | sim | `abc123...` | App Secret da Meta usado para validar `X-Hub-Signature-256` nos webhooks do WhatsApp. |
| `SCHEDULER_TIMEZONE` | não | `America/Sao_Paulo` | Timezone dos jobs. |
| `SCHEDULER_MORNING_HOUR` | não | `8` | Hora do check-in diário da manhã. |
| `SCHEDULER_MORNING_MINUTE` | não | `0` | Minuto do check-in diário da manhã. |

## Desenvolvimento local

O desenvolvimento pode usar PostgreSQL local pelo `docker-compose.dev.yml`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.dev.example .env.dev  # se existir; caso contrário crie manualmente
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Com Docker Compose de desenvolvimento:

```bash
docker compose -f docker-compose.dev.yml up --build
```

`DATABASE_URL` local típica:

```text
postgresql+psycopg2://postgres:postgres@db:5432/app_dev
```

## Produção com Supabase + EC2

Produção não sobe PostgreSQL local. O `docker-compose.yml` contém somente a API.

1. Criar projeto Supabase e copiar a connection string PostgreSQL.
2. Configurar `.env` na EC2 com `DATABASE_URL` do Supabase e demais variáveis.
3. Instalar Docker e Docker Compose plugin.
4. Aplicar migrations.
5. Subir a API.

Comandos sugeridos na EC2:

```bash
git pull
nano .env

docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
docker compose logs -f api
```

## Alembic

O projeto usa baseline única em `alembic/versions/0001_base_schema.py`. Um banco Supabase vazio deve ser inicializado com:

```bash
alembic upgrade head
```

Em produção via Docker:

```bash
docker compose run --rm api alembic upgrade head
```

## Fluxo clínico

1. Um paciente é cadastrado em `/api/users/`.
2. Um plano é criado em `/api/monitoring/plans`.
3. Profissionais são cadastrados em `/api/monitoring/professional-profiles` e associados ao plano.
4. O scheduler seleciona apenas planos ativos, dentro de `start_date` e `end_date`, com paciente que possui telefone.
5. O scheduler cria/reutiliza um `DailyReport` pendente por plano/data/tipo.
6. O WhatsApp envia o template de check-in.
7. O webhook recebe resposta do paciente.
8. O `BotService` localiza o usuário pelo telefone e o `DailyReportService` atualiza o relatório pendente.
9. Relatórios ficam disponíveis em `/api/daily-reports/`.

## Testes

```bash
pytest -q
```

Testes principais:

- `app/tests/test_daily_report_service.py`
- `app/tests/test_bot_flow.py`

## Observações de produção

- Use `sslmode=require` na `DATABASE_URL` do Supabase quando aplicável.
- Rode somente uma instância efetiva do scheduler para evitar disparos duplicados.
- Configure Nginx/HTTPS na EC2 apontando para a porta `8000` da API.
- Não versione `.env`.
