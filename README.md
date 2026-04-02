# Nome do Projeto

**Julha Backend API** é o backend principal da plataforma **julha.com.br**, construído com FastAPI e integrado ao ecossistema de automações com LangChain, bots e scheduler. A aplicação centraliza autenticação, fluxos conversacionais, persistência de respostas e geração de dados analíticos para operação em escala. O projeto foi desenhado para suportar ambientes de desenvolvimento e produção com deploy em AWS EC2 e banco PostgreSQL em AWS RDS.

# Arquitetura

A arquitetura segue um modelo orientado a serviços com API HTTP como ponto central de orquestração:

- **Frontend / clientes**: consumidores HTTP (web, integrações externas, WhatsApp e Telegram) que interagem com endpoints REST.
- **API FastAPI**: camada principal de negócio, autenticação, autorização, validações e roteamento.
- **LangChain**: processamento de fluxos inteligentes, enriquecimento de respostas e automações de conversa.
- **Banco RDS (PostgreSQL)**: persistência de usuários, relatórios, respostas e estados de fluxos.
- **EC2**: ambiente de execução da aplicação em produção.
- **Scheduler**: execução periódica de jobs (ex.: lembretes, rotinas de processamento e disparos automatizados).
- **Bots / integrações**: canais de entrada e saída (Telegram, WhatsApp e serviços de terceiros).

**Fluxo resumido da aplicação**
1. O usuário envia mensagem/requisição via cliente HTTP, WhatsApp ou Telegram.
2. A API FastAPI recebe e valida a requisição.
3. O serviço pode acionar LangChain para compor ou interpretar respostas.
4. Dados de estado e histórico são persistidos no PostgreSQL (RDS).
5. Scheduler e bots consomem/geram eventos para automações contínuas.
6. A resposta é devolvida ao canal de origem.

```mermaid
flowchart TD
    U[Usuário / WhatsApp / Telegram] --> API[FastAPI API]
    API --> LC[LangChain]
    API --> DB[(AWS RDS)]
    API --> SCH[Scheduler]
    API --> BOT[Bots e Integrações]
    API --> EC2[AWS EC2]
```

# Estrutura do Projeto

```text
.
├── app/
│   ├── main.py
│   ├── routes/
│   ├── services/
│   ├── models/
│   ├── db/
│   ├── core/
│   └── bot/
│       ├── telegram/          # organização lógica para integrações Telegram
│       ├── whatsapp/          # organização lógica para integrações WhatsApp
│       └── scheduler/         # organização lógica para tarefas agendadas
├── tests/
├── Dockerfile
├── docker-compose.yml
└── alembic/
```

> Observação: neste repositório, testes também podem estar em `app/tests` e módulos de bot podem estar estruturados em subpastas como `app/bot/channels` e arquivos dedicados por canal.

# Requisitos

- Python 3.11+
- Docker
- Docker Compose (plugin `docker compose`)
- AWS CLI (opcional, para operações de infraestrutura)
- PostgreSQL local (opcional, para desenvolvimento sem RDS)

# Variáveis de Ambiente

| Variável | Exemplo | Descrição |
| -------- | ------- | --------- |
| `ENV` | `production` | Ambiente de execução (`development` ou `production`). |
| `APP_HOST` | `0.0.0.0` | Host de bind da aplicação FastAPI. |
| `APP_PORT` | `8000` | Porta da aplicação FastAPI. |
| `DATABASE_URL` | `postgresql+psycopg2://julha_user:StrongPass123@julha-rds.xxxxxx.us-east-1.rds.amazonaws.com:5432/julha_db` | URL completa de conexão com PostgreSQL. |
| `AWS_REGION` | `us-east-1` | Região AWS usada por serviços integrados. |
| `AWS_ACCESS_KEY_ID` | `AKIAXXXXXXXXXXXXXXXX` | Chave de acesso AWS (evite uso fixo em produção). |
| `AWS_SECRET_ACCESS_KEY` | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYXXXXXXXX` | Segredo AWS (armazenar com segurança). |
| `OPENAI_API_KEY` | `sk-proj-xxxxxxxxxxxxxxxxxxxx` | Chave para recursos de IA/LangChain. |
| `DOMAIN` | `https://julha.com.br` | Domínio base da aplicação. |
| `JWT_SECRET` | `ultra_strong_jwt_secret_256_bits` | Segredo para assinatura de tokens JWT. |
| `TELEGRAM_TOKEN` | `1234567890:AAEXAMPLEtelegramToken` | Token do bot de Telegram. |
| `WHATSAPP_TOKEN` | `EAAaWhatsAppBusinessTokenExample` | Token de integração WhatsApp API. |
| `RDS_HOST` | `julha-rds.xxxxxx.us-east-1.rds.amazonaws.com` | Endpoint do banco RDS. |
| `RDS_PORT` | `5432` | Porta do PostgreSQL no RDS. |
| `RDS_DB` | `julha_db` | Nome do banco no RDS. |
| `RDS_USER` | `julha_user` | Usuário do banco RDS. |
| `RDS_PASSWORD` | `StrongPass123` | Senha do banco RDS. |

# Instalação para Desenvolvimento

1. **Clonar o repositório**
   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd healthy-agent-back
   ```

2. **Criar ambiente virtual**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Instalar dependências**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar `.env`**
   ```bash
   cp .env.example .env
   # editar as variáveis conforme seção "Variáveis de Ambiente"
   ```

5. **Executar migrations**
   ```bash
   alembic upgrade head
   ```

6. **Subir aplicação**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

# Execução com Docker

1. **Build das imagens**
   ```bash
   docker compose build
   ```

2. **Subir serviços**
   ```bash
   docker compose up -d
   ```

3. **Derrubar serviços**
   ```bash
   docker compose down
   ```

**Portas expostas (padrão):**
- `8000`: API FastAPI
- `5432`: PostgreSQL (quando exposto em ambiente local)

# URLs do Sistema

| Ambiente / Serviço | URL |
| ------------------ | --- |
| Produção | https://julha.com.br |
| Swagger | https://julha.com.br/docs |
| Redoc | https://julha.com.br/redoc |
| Healthcheck | https://julha.com.br/health |
| Desenvolvimento | http://localhost:8000 |

# Deploy em Produção

Passo a passo sugerido para EC2 (Ubuntu):

1. **Acessar EC2**
   ```bash
   ssh -i sua-chave.pem ubuntu@SEU_IP_EC2
   ```

2. **Clonar repositório**
   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd healthy-agent-back
   ```

3. **Configurar `.env`**
   ```bash
   nano .env
   ```

4. **Instalar Docker**
   ```bash
   sudo apt update
   sudo apt install -y docker.io
   sudo systemctl enable docker
   sudo systemctl start docker
   ```

5. **Instalar Docker Compose**
   ```bash
   sudo apt install -y docker-compose-plugin
   docker compose version
   ```

6. **Executar build**
   ```bash
   docker compose build
   ```

7. **Subir containers**
   ```bash
   docker compose up -d
   ```

8. **Configurar Nginx reverso para `julha.com.br`**
   ```bash
   sudo apt install -y nginx
   ```

   Exemplo de configuração:
   ```nginx
   server {
       server_name julha.com.br www.julha.com.br;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

9. **Configurar HTTPS com Certbot (Let's Encrypt)**
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d julha.com.br -d www.julha.com.br
   ```

# Banco de Dados

- **Uso do RDS**: o PostgreSQL gerenciado em AWS RDS é a fonte oficial de dados em produção.
- **Migrations com Alembic**: mudanças de schema devem ser versionadas e aplicadas com `alembic upgrade head`.
- **Backup**:
  - Snapshot automático no RDS (recomendado para produção).
  - Dump manual opcional:
    ```bash
    pg_dump -h julha-rds.xxxxxx.us-east-1.rds.amazonaws.com -U julha_user -d julha_db > backup_julha.sql
    ```
- **Restore**:
  ```bash
  psql -h julha-rds.xxxxxx.us-east-1.rds.amazonaws.com -U julha_user -d julha_db < backup_julha.sql
  ```
- **Conexão local e produção**:
  - Local: `DATABASE_URL` apontando para container/local PostgreSQL.
  - Produção: `DATABASE_URL` apontando para endpoint do RDS com credenciais restritas.

# Scheduler e Bots

- **Iniciar scheduler**:
  - Quando embutido no app: iniciar a API normalmente e validar logs do scheduler.
  - Quando isolado (se aplicável):
    ```bash
    python -m app.bot.scheduler
    ```
- **Funcionamento dos bots WhatsApp e Telegram**:
  - Webhooks/handlers recebem eventos dos canais.
  - Mensagens são processadas por serviços internos e persistidas no banco.
  - Respostas são enviadas de volta ao provedor do canal.
- **Registrar novos fluxos**:
  1. Criar handler/serviço em `app/services` ou `app/bot`.
  2. Registrar rota/webhook em `app/routes`.
  3. Persistir estado necessário no banco.
  4. Cobrir com testes automatizados.
- **Testar localmente**:
  - Executar API local + túnel HTTP (quando necessário para webhook).
  - Simular payloads com `curl`/Postman.
  - Verificar persistência no banco e logs de processamento.

# Testes

```bash
pytest
pytest -v
pytest tests/services
```

> Caso a suíte esteja em `app/tests`, adapte os comandos para `pytest app/tests` e subpastas correspondentes.

# Observabilidade e Logs

- **Logs da aplicação**: acompanhar stdout/stderr da API e formatar logs por contexto (request id, user id, canal).
- **Logs Docker**:
  ```bash
  docker compose logs -f
  ```
- **Healthcheck**: monitorar `https://julha.com.br/health` em intervalos regulares.
- **Monitoramento em produção**:
  - Métricas de CPU/memória/rede da instância EC2.
  - Alarmes para indisponibilidade do endpoint e falhas no scheduler.
  - Centralização de logs (ex.: CloudWatch/stack observável).

# Segurança

- Nunca commitar arquivo `.env` ou segredos no repositório.
- Usar AWS Secrets Manager ou variáveis protegidas no ambiente.
- Restringir Security Groups (acesso mínimo necessário a portas e origens).
- Rotacionar chaves e tokens periodicamente.
- HTTPS obrigatório para todo tráfego externo (incluindo webhooks).

# Troubleshooting

| Problema | Causa provável | Solução |
| -------- | -------------- | ------- |
| Aplicação não sobe | Variáveis obrigatórias ausentes | Validar `.env`, revisar logs e rodar `docker compose logs -f`. |
| Falha no banco | `DATABASE_URL` incorreta ou RDS indisponível | Testar conectividade, revisar credenciais e security groups. |
| Erro de credenciais AWS | Chaves inválidas/expiradas | Atualizar `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` com credenciais válidas. |
| Erro de porta ocupada | Porta `8000` já em uso | Alterar mapeamento no `docker-compose.yml` ou finalizar processo conflitante. |
| Erro 502 no Nginx | Upstream FastAPI fora do ar | Verificar container/API, `proxy_pass` e status do serviço Nginx. |

# Roadmap

- Expandir cobertura de testes de integração e carga.
- Adicionar filas assíncronas para workloads pesados de bots e IA.
- Implementar observabilidade avançada com tracing distribuído.
- Evoluir versionamento de API e contratos para integrações externas.
- Automatizar deploy com pipeline CI/CD e estratégia de rollback.
