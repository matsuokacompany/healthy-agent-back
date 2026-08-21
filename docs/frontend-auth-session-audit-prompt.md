# Prompt para auditoria de sessão no frontend

Copie o prompt abaixo para o agente responsável pelo repositório do frontend.

---

Investigue e corrija o logout prematuro da aplicação. O backend usa uma sessão gerenciada por cookies HttpOnly: o access token normalmente expira em cerca de uma hora, mas isso **não** deve encerrar a sessão enquanto o refresh cookie estiver válido. Não migre tokens para `localStorage`, `sessionStorage` ou JavaScript e não registre tokens/cookies em logs.

## Contrato do backend

- `POST /api/auth/login`: autentica, define cookies e retorna o usuário; nunca retorna tokens.
- `GET /api/auth/me`: retorna o usuário quando o access cookie é válido.
- `GET /api/auth/csrf`: retorna `{ "csrf_token": "..." }` e também o header `X-CSRF-Token`.
- `POST /api/auth/refresh`: exige cookies, `X-CSRF-Token` correspondente e retorna `204`; redefine os cookies e expõe o novo `X-CSRF-Token` no header.
- `POST /api/auth/logout`: exige a mesma proteção CSRF e retorna `204`.
- Todas as chamadas devem usar `credentials: "include"` (ou `withCredentials: true` no Axios).

## Verificações obrigatórias

1. Localize todos os clientes HTTP, interceptors, hooks, providers, middleware, server actions e guards de rota relacionados à autenticação.
2. Confirme que a URL da API é a correta por ambiente e que **todas** as requisições para o backend incluem credenciais, inclusive `/login`, `/me`, `/csrf`, `/refresh`, `/logout` e o retry.
3. Remova qualquer lógica que redirecione imediatamente ao login no primeiro `401`.
4. Implemente um refresh **single-flight**: no primeiro `401`, todos os pedidos concorrentes devem aguardar a mesma Promise de refresh, sem disparar vários refreshes.
5. Antes do refresh, chame `GET /api/auth/csrf`; envie o valor recebido em `X-CSRF-Token` no `POST /api/auth/refresh`.
6. Após refresh bem-sucedido, atualize em memória o CSRF retornado no header e repita a requisição original **uma única vez**.
7. Só limpe o estado do usuário e redirecione ao login quando o refresh realmente falhar. Não tente refresh para falhas `403`, erros de rede ou para os próprios endpoints `/login`, `/csrf`, `/refresh` e `/logout`.
8. Execute o mesmo fluxo de recuperação no bootstrap: se `/me` responder `401`, tente refresh e repita `/me` antes de considerar a sessão encerrada.
9. Evite loops infinitos marcando a requisição já repetida e trate logout concorrente: depois que o usuário iniciar logout, uma resposta atrasada não pode restaurar a sessão.
10. Verifique se service workers, cache de fetch, React Query/SWR e middleware SSR não armazenam respostas de autenticação nem transformam um erro transitório em logout. Chamadas de auth devem usar `cache: "no-store"` quando aplicável.
11. No DevTools, valide que o login recebe os cookies `__Host-ha_access`, `__Host-ha_refresh` e `ha_csrf`; o refresh cookie deve ter `Secure`, `HttpOnly`, ausência de `Domain`, `SameSite=Strict`, `Path=/` e expiração aproximada de 30 dias.
12. Confira CORS e topologia dos domínios. O origin exato do frontend precisa estar permitido pelo backend. Se frontend e API forem cross-site (não apenas subdomínios do mesmo site), documente o conflito com `SameSite=Strict` em vez de enfraquecer a política silenciosamente.

## Testes a criar

- Login mantém usuário autenticado.
- Um endpoint que retorna `401` uma vez provoca `/csrf` + `/refresh` + um único retry e então tem sucesso.
- Várias requisições simultâneas com access expirado fazem exatamente um refresh.
- Falha do refresh limpa a sessão e redireciona uma única vez.
- O bootstrap recupera `/me` após access token expirado.
- O retry não entra em loop se continuar recebendo `401`.
- Logout impede refresh posterior e limpa o estado local.
- Todas as chamadas relevantes enviam credenciais e o refresh envia CSRF.

Entregue: (a) diagnóstico com a causa raiz e evidências, (b) alterações mínimas de código, (c) testes automatizados, (d) comandos executados e resultados, e (e) checklist manual do Network/Application do navegador sem expor valores sensíveis.

---
