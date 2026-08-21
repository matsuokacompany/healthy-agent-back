# Prompt para auditoria de sessão no frontend

Copie o prompt abaixo para o agente responsável pelo repositório do frontend.

---

Investigue e corrija o logout prematuro da aplicação. O backend usa uma sessão gerenciada por cookies HttpOnly: o access token normalmente expira em cerca de uma hora, mas isso **não** deve encerrar a sessão enquanto o refresh cookie estiver válido. Não migre tokens para `localStorage`, `sessionStorage` ou JavaScript e não registre tokens/cookies em logs.

Faça as alterações diretamente no repositório do frontend; não entregue apenas
uma análise ou documentação. Antes de editar, identifique a stack, o cliente HTTP
compartilhado e o fluxo de bootstrap já existentes e preserve os padrões do
projeto.

## Contrato do backend

- `POST /api/auth/login`: autentica, define cookies e retorna o usuário; nunca retorna tokens.
- `GET /api/auth/me`: retorna o usuário quando o access cookie é válido.
- `GET /api/auth/csrf`: retorna `{ "csrf_token": "..." }` e também o header `X-CSRF-Token`.
- `POST /api/auth/refresh`: exige cookies, `X-CSRF-Token` correspondente e retorna `204`; redefine os cookies e expõe o novo `X-CSRF-Token` no header.
- `POST /api/auth/logout`: exige a mesma proteção CSRF e retorna `204`.
- Todas as chamadas devem usar `credentials: "include"` (ou `withCredentials: true` no Axios).
- O cookie não chama o endpoint sozinho: não é necessário criar um timer, mas o frontend precisa executar `/csrf` + `/refresh` no primeiro `401` e repetir a chamada original.

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
13. Se o backend acabou de receber a correção de `Path=/` do cookie `__Host-ha_refresh`, faça um novo login uma vez: sessões criadas antes da correção não possuem um refresh cookie recuperável no navegador.

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

## Exemplo de implementação com `fetch`

O ajuste precisa ser feito no cliente HTTP compartilhado do frontend, e não em
cada tela. O exemplo abaixo mostra o contrato mínimo. Adapte a obtenção da URL da
API e o tratamento de redirecionamento ao framework usado pelo frontend.

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL!;
let refreshInFlight: Promise<void> | null = null;

async function refreshSession(): Promise<void> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const csrfResponse = await fetch(`${API_URL}/api/auth/csrf`, {
        credentials: "include",
        cache: "no-store",
      });
      if (!csrfResponse.ok) throw new Error("Session refresh unavailable");

      const { csrf_token: csrfToken } = await csrfResponse.json();
      const refreshResponse = await fetch(`${API_URL}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "X-CSRF-Token": csrfToken },
      });
      if (!refreshResponse.ok) throw new Error("Session refresh failed");
    })().finally(() => {
      refreshInFlight = null;
    });
  }

  return refreshInFlight;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const request = () =>
    fetch(`${API_URL}${path}`, {
      ...init,
      credentials: "include",
      cache: "no-store",
    });

  let response = await request();
  const cannotRefresh = new Set([
    "/api/auth/login",
    "/api/auth/csrf",
    "/api/auth/refresh",
    "/api/auth/logout",
  ]).has(path);
  if (response.status !== 401 || cannotRefresh) return response;

  await refreshSession();
  response = await request();
  return response;
}
```

O bootstrap deve chamar `apiFetch("/api/auth/me")`. A aplicação só deve apagar o
usuário e navegar para a tela de login se `apiFetch` lançar erro no refresh ou se
o retry de `/me` continuar retornando `401`. Não armazene access token ou refresh
token no JavaScript.
