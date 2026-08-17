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
