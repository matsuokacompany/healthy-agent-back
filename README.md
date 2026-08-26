# Julha Backend API

Backend FastAPI para um MVP SaaS de monitoramento clínico com Supabase PostgreSQL, WhatsApp Cloud API, APScheduler, autenticação JWT/refresh tokens, anamneses, daily reports e geração de insights com OpenAI/LangChain.

As regras de isolamento entre paciente, profissional e serviços internos, além
da configuração de Row Level Security, estão em [`docs/security.md`](docs/security.md).

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
| `DATABASE_RUNTIME_ROLE` | não | `healthy_agent_api` | Papel sem login criado pela migration de RLS e assumido pelas conexões da API. |
| `SECRET_KEY` | sim | `change-me` | Segredo JWT legado. |
| `SUPABASE_PROJECT_URL` | sim | `https://<PROJECT_REF>.supabase.co` | URL do projeto Supabase usada para validar o issuer `https://<PROJECT_REF>.supabase.co/auth/v1`. |
| `API_PUBLIC_URL` | sim para cadastro/recuperação de senha/convite | `https://api.exemplo.com` | Origem pública **desta API** (não do front-end). Usada só para montar o `redirect_to` enviado ao Supabase em cadastro, recuperação de senha e convite, para que o link do e-mail volte para `GET /api/auth/callback` desta API em vez da origem do front (que não tem essa rota). Sem essa variável, o Supabase usa a Site URL padrão configurada no próprio projeto. |
| `SUPABASE_JWT_SECRET` | sim | `<supabase-jwt-secret>` | JWT secret do Supabase usado para validar access tokens `HS256`. |
| `SUPABASE_JWT_AUDIENCE` | não | `authenticated` | Audience exigida nos access tokens do Supabase. |
| `SUPABASE_JWT_ISSUER` | não | `https://<PROJECT_REF>.supabase.co/auth/v1` | Issuer customizado; por padrão é derivado de `SUPABASE_PROJECT_URL`. |
| `OPENAI_API_KEY` | não | `sk-...` | Chave OpenAI para insights. |
| `AI_REPORT_PREVIEW_SECRET` | sim para relatórios personalizados | `change-me-with-a-long-random-secret` | Segredo exclusivo usado para assinar previews de relatórios por 15 minutos. |
| `AI_REPORT_MODEL` | não | `gpt-4o-mini` | Modelo usado nos relatórios personalizados. |
| `AI_REPORT_MAX_INPUT_TOKENS` | não | `2000` | Limite estimado de tokens de entrada por relatório. |
| `AI_REPORT_MAX_OUTPUT_TOKENS` | não | `500` | Limite de tokens de saída por relatório. |
| `AI_REPORT_MAX_COST_USD` | não | `0.05` | Teto estimado em dólar para uma geração. |
| `AI_REPORT_INPUT_COST_PER_MILLION_USD` | sim para geração | consulte o provedor | Preço configurável de um milhão de tokens de entrada. |
| `AI_REPORT_OUTPUT_COST_PER_MILLION_USD` | sim para geração | consulte o provedor | Preço configurável de um milhão de tokens de saída. |
| `CLINICAL_IMAGES_ENABLED` | não | `false` | Chave geral do MVP de imagens clínicas. |
| `WHATSAPP_CLINICAL_IMAGES_ENABLED` | não | `false` | Aceita uma imagem na descrição de sintomas do WhatsApp. |
| `PORTAL_CLINICAL_IMAGES_ENABLED` | não | `false` | Aceita imagens de paciente/profissional pelo portal. |
| `SUPABASE_STORAGE_BUCKET` | não | `clinical-images` | Bucket privado para imagens clínicas. |
| `SUPABASE_SERVICE_ROLE_KEY` | sim para imagens | - | Segredo exclusivo do backend para operar o bucket privado; nunca exponha ao frontend. |
| `CLINICAL_ENCRYPTION_PROVIDER` | não nesta etapa | `aws_kms` | Provedor da fundação de criptografia clínica. Ainda não criptografa colunas até a integração dos modelos. |
| `CLINICAL_ENCRYPTION_KMS_KEY_ID` | não nesta etapa | `arn:aws:kms:sa-east-1:<ACCOUNT_ID>:key/<KEY_ID>` | ARN/ID da chave KMS clínica; a EC2 deve acessá-la por IAM Role. |
| `CLINICAL_ENCRYPTION_AWS_REGION` | não nesta etapa | `sa-east-1` | Região da chave AWS KMS. |
| `CLINICAL_ENCRYPTION_ACTIVE_KEY_VERSION` | não | `v1` | Versão lógica gravada no envelope para permitir rotação futura. |
| `CLINICAL_ENCRYPTION_PLAINTEXT_WRITES_ENABLED` | não | `true` | Flag de corte: defina `false` somente após concluir e verificar o backfill para persistir apenas envelopes. |
| `CORS_ORIGINS` | não | `http://localhost:3000,https://app.julha.com.br` | Origens permitidas no CORS, separadas por vírgula. O padrão já inclui `http://localhost:3000` e `https://app.julha.com.br`. |
| `WHATSAPP_VERIFY_TOKEN` | sim | `verify-token` | Token de verificação do webhook Meta. |
| `WHATSAPP_PHONE_NUMBER_ID` | sim | `123456789` | Phone Number ID da Meta. |
| `WHATSAPP_ACCESS_TOKEN` | sim | `EAA...` | Token WhatsApp Cloud API. |
| `WHATSAPP_DAILY_TEMPLATE_NAME` | sim | `daily_symptom_checkin` | Template de check-in aprovado na Meta. |
| `APP_SECRET` | sim | `abc123...` | App Secret da Meta usado para validar `X-Hub-Signature-256` nos webhooks do WhatsApp. |
| `SCHEDULER_TIMEZONE` | não | `America/Sao_Paulo` | Timezone dos jobs. |
| `SCHEDULER_MORNING_HOUR` | não | `8` | Hora do check-in diário da manhã. |
| `SCHEDULER_MORNING_MINUTE` | não | `0` | Minuto do check-in diário da manhã. |
| `ASAAS_API_KEY` | sim para cobrança B2C | `$aact_...` | Chave de API do Asaas (comece pela do ambiente sandbox). |
| `ASAAS_ENV` | não | `sandbox` | `sandbox` ou `production`; seleciona a base da API do Asaas. |
| `ASAAS_WEBHOOK_TOKEN` | sim para cobrança B2C | `<segredo escolhido por você>` | Token definido ao cadastrar o webhook no painel do Asaas; validado em `POST /webhook/asaas`. |
| `ASAAS_SELF_MONITORING_PRICE_CENTS` | sim para cobrança B2C | `1990` | Preço do plano **mensal** de automonitoramento, em centavos (sem valor padrão; precisa ser definido explicitamente). |
| `ASAAS_SELF_MONITORING_SEMIANNUAL_PRICE_CENTS` | não | `9990` | Preço do plano **semestral**, em centavos. Sem valor padrão — o plano só aparece em `GET /api/billing/plans` depois de configurado. |
| `ASAAS_SELF_MONITORING_ANNUAL_PRICE_CENTS` | não | `17990` | Preço do plano **anual**, em centavos. Sem valor padrão — mesma regra do semestral. |
| `ASAAS_SELF_MONITORING_TRIAL_DAYS` | não | `30` | Duração do período de teste grátis do automonitoramento self-service, em dias. |
| `SMTP_HOST` | sim para notificação por e-mail de pedido de vínculo | `smtp.hostinger.com` | Servidor SMTP usado pelo backend para e-mails próprios (separado do SMTP configurado no Supabase Auth, mesmo que aponte pra mesma caixa). |
| `SMTP_PORT` | não | `465` | Porta SMTP; `465` usa SSL implícito (é o que o backend espera — não use `587`/STARTTLS sem também trocar o código). |
| `SMTP_USER` | sim para notificação por e-mail de pedido de vínculo | `contato@julha.com.br` | Usuário de login SMTP. |
| `SMTP_PASSWORD` | sim para notificação por e-mail de pedido de vínculo | `<senha da caixa>` | Senha de login SMTP. |
| `SMTP_FROM_EMAIL` | sim para notificação por e-mail de pedido de vínculo | `contato@julha.com.br` | Endereço que aparece como remetente. |

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
2. Configurar os secrets do ambiente `production` no GitHub (veja abaixo).
3. Instalar Docker e o plugin Docker Compose uma única vez na instância.
4. Fazer push para `main`; migrations e inicialização da API são automáticas.

O workflow `.github/workflows/deploy.yml` envia uma cópia limpa do commit para a
EC2, cria o `.env`, reconstrói a imagem, executa as migrations no início do
container e valida que a API permaneceu em execução. Assim, a instância não
precisa ter uma cópia Git do repositório nem credenciais do GitHub.
O checkout e a configuração SSH usam somente ferramentas já presentes no
runner (`git` e `ssh`), sem baixar actions do Marketplace; isso evita que uma
indisponibilidade do serviço de download de actions bloqueie o deploy.

### Impacto e custo para um MVP

Esse fluxo não cria instâncias, bancos, load balancers ou containers adicionais:
ele apenas atualiza o único serviço `api` que já roda na EC2. `git archive`,
`scp`, as verificações via `docker compose ps` e o armazenamento dos secrets têm
impacto desprezível em produção. A compilação da imagem consome CPU, memória e
disco da própria EC2 somente durante cada deploy; por isso, evite muitos pushes
seguidos em uma instância muito pequena. O `concurrency` serializa os deploys e
`docker image prune` remove imagens sem uso depois de uma atualização bem-sucedida.

O workflow não aumenta, por si só, a quantidade de recursos faturados na AWS.
Ainda podem existir custos normais da infraestrutura escolhida: horas da EC2,
EBS, endereço IPv4 público, tráfego de saída, Supabase/OpenAI/Meta e, se usados,
Elastic IP, Route 53 ou outros serviços. O upload do release é pequeno e ocorre
apenas no deploy. GitHub Actions é cobrado/limitado pelo plano do GitHub, não na
fatura da AWS. Para um MVP, não é necessário adicionar Elastic IP ou domínio ao
workflow; eles servem apenas para manter um endereço estável.

Cadastre estes secrets em **Settings > Environments > production**:

- `EC2_HOST`: IP ou domínio público da instância;
- `EC2_USER`: usuário SSH (por exemplo, `ubuntu`);
- `EC2_SSH_KEY`: chave SSH privada;
- `EC2_HOST_KEY`: linha completa retornada por `ssh-keyscan -H <host>`;
- `PRODUCTION_ENV`: conteúdo completo do arquivo `.env` de produção.

### Onde obter os secrets de deploy

- **`EC2_HOST`**: no console da AWS, abra **EC2 > Instances**, selecione a
  instância e copie **Public IPv4 address** ou **Public IPv4 DNS** na aba de
  detalhes. Prefira associar um Elastic IP ou usar um domínio apontado para ele,
  pois o IP público automático pode mudar quando a instância é parada.
- **`EC2_USER`**: é o usuário definido pela AMI e usado no seu comando SSH. Nas
  imagens Ubuntu oficiais normalmente é `ubuntu`; no Amazon Linux é
  `ec2-user`. A tela **Connect > SSH client** da instância mostra um comando de
  conexão pronto e, nele, o usuário aparece antes de `@`.
- **`EC2_SSH_KEY`**: é todo o conteúdo do arquivo privado `.pem` baixado ao criar
  o key pair da instância, incluindo as linhas `BEGIN` e `END`. A AWS não permite
  baixar novamente a chave privada. Se ela foi perdida, crie uma chave nova e
  adicione sua chave pública à instância usando EC2 Instance Connect ou Session
  Manager; nunca cole a chave privada na EC2 ou no repositório.
- **`EC2_HOST_KEY`**: em uma máquina confiável, execute
  `ssh-keyscan -H <EC2_HOST>` e copie toda a saída. Para evitar confiar em uma
  chave interceptada, compare antes o fingerprint com o da instância. Pelo
  Session Manager, execute `sudo ssh-keygen -lf
  /etc/ssh/ssh_host_ed25519_key.pub`; localmente, salve a saída do `ssh-keyscan`
  e execute `ssh-keygen -lf <arquivo>`. Os fingerprints devem ser iguais.
  Use no comando o mesmo IP ou domínio salvo em `EC2_HOST`. O workflow também
  associa a chave confiável ao hostname efetivamente usado pelo `scp`, portanto
  funciona se a chave tiver sido coletada pelo IP e `EC2_HOST` usar o DNS (ou o
  inverso), desde que ambos apontem para a mesma instância.
- **`PRODUCTION_ENV`**: não é fornecido pronto pela AWS. Crie esse secret
  juntando as configurações dos serviços usados pela aplicação: conexão e
  chaves no painel do Supabase, credenciais no painel Meta for Developers,
  chave da OpenAI e os domínios/horários escolhidos para a aplicação. Use o
  modelo abaixo e substitua cada marcador `<...>`.

Depois, no GitHub, abra **Settings > Environments > production**, crie o
environment se necessário e adicione cada item em **Environment secrets**. Os
nomes precisam coincidir exatamente com os usados pelo workflow.

Exemplo dos secrets do environment `production` (substitua todos os valores
entre `<...>` pelos valores reais):

| Secret | Exemplo de valor |
| --- | --- |
| `EC2_HOST` | `api.exemplo.com` ou `203.0.113.10` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | conteúdo completo de `-----BEGIN OPENSSH PRIVATE KEY-----` até `-----END OPENSSH PRIVATE KEY-----` |
| `EC2_HOST_KEY` | saída completa de `ssh-keyscan -H api.exemplo.com` |

Para o secret multilinha `PRODUCTION_ENV`, use um valor como este:

```dotenv
ENV=production
DEBUG=false
DATABASE_URL=postgresql+psycopg2://postgres:<SENHA>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require
DATABASE_RUNTIME_ROLE=healthy_agent_api

SUPABASE_PROJECT_URL=https://<PROJECT_REF>.supabase.co
SUPABASE_ANON_KEY=<SUPABASE_ANON_KEY>
SUPABASE_JWT_SECRET=<SUPABASE_JWT_SECRET>
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_ISSUER=https://<PROJECT_REF>.supabase.co/auth/v1

CORS_ORIGINS=https://app.exemplo.com
AUTH_REDIRECT_ALLOWLIST=https://app.exemplo.com
API_PUBLIC_URL=https://api.exemplo.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax

WHATSAPP_VERIFY_TOKEN=<TOKEN_DE_VERIFICACAO>
WHATSAPP_PHONE_NUMBER_ID=<PHONE_NUMBER_ID>
WHATSAPP_ACCESS_TOKEN=<TOKEN_DE_ACESSO_PERMANENTE>
WHATSAPP_DAILY_TEMPLATE_NAME=daily_symptom_checkin
APP_SECRET=<META_APP_SECRET>

SCHEDULER_TIMEZONE=America/Sao_Paulo
SCHEDULER_MORNING_HOUR=8
SCHEDULER_MORNING_MINUTE=0

OPENAI_API_KEY=<OPENAI_API_KEY>
AI_REPORT_PREVIEW_SECRET=<SEGREDO_ALEATORIO_LONGO>
AI_REPORT_MODEL=gpt-4o-mini
AI_REPORT_MAX_INPUT_TOKENS=2000
AI_REPORT_MAX_OUTPUT_TOKENS=500
AI_REPORT_MAX_COST_USD=0.05
AI_REPORT_INPUT_COST_PER_MILLION_USD=<CUSTO_DE_ENTRADA>
AI_REPORT_OUTPUT_COST_PER_MILLION_USD=<CUSTO_DE_SAIDA>
```

O GitHub preserva as quebras de linha de `PRODUCTION_ENV`; não transforme esse
valor em JSON e não faça commit dos valores reais. `OPENAI_API_KEY` e as
variáveis `AI_REPORT_*` podem ser omitidas quando a geração de relatórios por IA
não for utilizada.

Na EC2, Docker e o plugin Docker Compose precisam estar instalados uma única
vez e o usuário SSH deve ter permissão para executar `docker`. Depois disso,
todo push na branch `main` (ou uma execução manual em **Actions**) realiza o
deploy sem comandos manuais na instância.

Para diagnóstico local na EC2, os comandos equivalentes são:

```bash
cd ~/healthy-agent-back
docker compose ps
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
8. Se o paciente informar que teve sintomas pelo botão/atalho positivo, o bot pede apenas a descrição dos sintomas em uma única mensagem para reduzir respostas não-template no WhatsApp.
9. O `BotService` localiza o usuário pelo telefone e o `DailyReportService` atualiza o relatório pendente.
10. Relatórios ficam disponíveis em `/api/daily-reports/`.

### Canais do bot

O único canal implementado e registrado atualmente é o WhatsApp. Não há lógica
ativa do Telegram nem dependência dele no backend. A abstração `BaseBotChannel`
e o registro do `BotManager` são mantidos para permitir que um canal como o
Telegram seja adicionado futuramente como uma implementação isolada, sem
acoplar essa possibilidade ao fluxo atual.

O MVP opcional de imagens clínicas é documentado em
[`docs/clinical-images-mvp.md`](docs/clinical-images-mvp.md). Ele permanece
desligado por padrão, limita o WhatsApp a uma imagem por check-in e o portal a
três imagens por envio, sem análise por IA.

### Otimização de custo do WhatsApp

O fluxo positivo foi encurtado para manter a experiência intuitiva e reduzir mensagens
enviadas pela empresa:

- Antes: template inicial, pergunta sobre sintomas, pergunta sobre causa e confirmação final.
- Agora: template inicial, uma pergunta sobre sintomas e confirmação final.

Com preços baseados em mensagem, isso reduz o caso positivo completo de 4 mensagens
enviadas pela empresa para 3 mensagens, sem deixar o paciente sem orientação sobre o que
responder.

Para evitar gasto acima desse pior cenário operacional, o bot não envia respostas
adicionais quando o check-in já foi encerrado, já foi concluído ou quando a mensagem
recebida é maior que o limite aceito. Essas entradas continuam sendo registradas pelo
webhook, mas não geram nova mensagem de texto da empresa.

### Otimização de custo dos relatórios de IA

Os prompts de insights usam instruções compactas, limite de saída e corte do relatório
de entrada para evitar consumo inesperado de tokens:

- `max_tokens=500` limita o tamanho da resposta do modelo.
- `temperature=0.1` reduz variação e respostas verbosas.
- Relatórios enviados à IA são truncados em 6.000 caracteres.
- Os templates pedem JSON compacto para reduzir tokens de entrada e saída.
- Na avaliação clínica, a IA pode listar `possiveis_doencas` apenas como hipóteses,
  sem confirmar diagnóstico.
- A geração profissional reutiliza o primeiro relatório de IA já emitido na semana
  para o paciente, evitando múltiplas chamadas pagas para o mesmo usuário.
- O resumo clínico usa a data clínica do check-in (`report_date`) e inclui adesão,
  dias/check-ins com sintomas, dias/check-ins sem sintomas e tendência do período.

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
