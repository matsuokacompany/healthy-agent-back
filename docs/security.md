# Segurança e isolamento de dados

## Matriz de acesso

- pacientes acessam somente o próprio perfil e os próprios dados clínicos;
- profissionais acessam o próprio perfil e pacientes que possuam um plano e
  um vínculo profissional ativos;
- administradores mantêm o escopo global legado até a introdução de
  organizações; não use o papel `admin` para administradores de clínicas
  independentes;
- scheduler, webhook do WhatsApp e scripts operacionais usam contexto de
  serviço, sem personificar um paciente.

As verificações FastAPI são a primeira barreira. A migration `0009` adiciona
Row Level Security como defesa contra consultas de aplicação sem escopo.

## Papel PostgreSQL de runtime

A migration cria o papel sem login `healthy_agent_api`, concede-o ao usuário
que executa a migration e habilita RLS nas tabelas sensíveis. A API executa
`SET ROLE` ao abrir cada conexão usando `DATABASE_RUNTIME_ROLE`.

O usuário de migration precisa ter permissão para criar e conceder esse papel.
Se o provedor não permitir `CREATEROLE`, o papel e os grants devem ser criados
previamente por um administrador do banco antes de executar a migration.

O usuário configurado em `DATABASE_URL` precisa conseguir assumir esse papel.
Não configure um usuário com `BYPASSRLS` como `DATABASE_RUNTIME_ROLE`.

Requisições autenticadas configuram `app.supabase_user_id` com `SET LOCAL`.
Como o valor é transacional, uma conexão devolvida ao pool não conserva a
identidade para a próxima requisição. Contextos internos usam
`app.service_context` somente em código de scheduler, webhook ou provisionamento.

## Teste operacional após a migration

Confirme em staging:

```sql
SELECT current_user, session_user;

SELECT schemaname, tablename, rowsecurity, forcerowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

Na conexão da API, `current_user` deve ser `healthy_agent_api` e `rowsecurity`
deve estar habilitado nas tabelas cobertas. Teste sempre paciente A contra
paciente B e profissional vinculado contra profissional não vinculado.

## Texto fornecido pelo usuário

Campos clínicos são **texto simples**, não HTML. O backend impõe limites e
rejeita caracteres de controle, mas preserva sinais como `<` e `>` porque podem
ser conteúdo legítimo. Todo cliente deve renderizar esses valores como texto e
nunca usar `innerHTML` ou `dangerouslySetInnerHTML`.

## Segredos

Segredos permanecem em variáveis de ambiente ou no provedor de secrets. Nunca
adicione chaves OpenAI, Meta, Supabase, banco ou SSH ao repositório. Execute
secret scanning no repositório e no histórico antes de cada release.

## Criptografia de dados clínicos

A fundação de criptografia clínica usa envelope encryption: uma data key AES-256
é gerada pelo AWS KMS para cada operação e o valor clínico é protegido com
AES-256-GCM. O banco deve persistir somente o ciphertext, nonce, data key
criptografada, identificador/versão da chave e versão do envelope. A integração
com os modelos e o backfill são realizados em etapas posteriores; adicionar as
configurações abaixo, por si só, ainda não criptografa colunas existentes.

Em produção, configure:

```dotenv
CLINICAL_ENCRYPTION_PROVIDER=aws_kms
CLINICAL_ENCRYPTION_KMS_KEY_ID=arn:aws:kms:sa-east-1:<ACCOUNT_ID>:key/<KEY_ID>
CLINICAL_ENCRYPTION_AWS_REGION=sa-east-1
CLINICAL_ENCRYPTION_ACTIVE_KEY_VERSION=v1
```

Não configure `AWS_ACCESS_KEY_ID` ou `AWS_SECRET_ACCESS_KEY` no `.env` da EC2.
Associe uma IAM Role à instância e limite-a à chave clínica, com apenas as ações
KMS exigidas pela aplicação. Desenvolvimento e testes não podem utilizar a
chave de produção. Nunca inclua plaintext clínico, data keys ou respostas do KMS
em logs.

O contexto criptográfico exige `table`, `record_id`, `patient_id` e `field`.
Esse contexto é autenticado pelo KMS e pelo AES-GCM, impedindo que um ciphertext
seja movido silenciosamente para outro paciente, registro ou campo.

A migration `0010` somente adiciona envelopes JSON anuláveis ao lado das colunas
legadas. Ela não lê, atualiza, criptografa ou remove valores existentes. O
backfill é reiniciável e processa somente valores plaintext não nulos que ainda
não possuem envelope. Primeiro confira as contagens sem acessar o KMS:

```bash
python -m app.scripts.clinical_encryption_backfill
```

Depois do preflight e de um backup verificado, execute em lotes. Cada lote é
confirmado em uma transação separada; uma nova execução ignora campos já
processados. `--max-records` permite um canário controlado:

```bash
python -m app.scripts.clinical_encryption_backfill --execute --batch-size 100 --max-records 10
python -m app.scripts.clinical_encryption_backfill --execute --batch-size 100
```

Repita o modo de contagem e confirme que todas as tabelas ficaram em zero antes
de interromper a escrita plaintext. Não execute duas instâncias do backfill ao
mesmo tempo; `SKIP LOCKED` reduz contenção no PostgreSQL, mas a operação deve ser
coordenada. Nunca registre os valores clínicos ou os envelopes.

O preflight permanente pode ser executado sem dados de pacientes:

```bash
python -m app.scripts.clinical_encryption_preflight
```

Relatórios diários novos ou editados fazem escrita dupla de descrição e causa:
o plaintext é mantido temporariamente para rollback e o envelope autenticado é
gravado na mesma transação. Em produção não existe fallback silencioso quando o
KMS falha. Limpar uma resposta também limpa os envelopes correspondentes.

Anamneses novas e atualizadas também fazem escrita dupla após o registro obter
seu ID. Leituras do paciente, profissional, dashboard e geração de prompts
preferem o envelope autenticado, mantendo fallback para anamneses legadas.
