# Supabase Auth and application authorization

## Current architecture

Authentication is delegated to Supabase Auth. Clients authenticate with Supabase and send the Supabase access token as a Bearer token to this API. The backend validates that JWT with the Supabase JWT secret for `HS256` tokens, requires `aud=authenticated`, requires `iss=https://<project-ref>.supabase.co/auth/v1` derived from `SUPABASE_PROJECT_URL`, and resolves the `sub` claim to a local `users` record through `users.supabase_user_id`.

Authorization remains local to this application. Business tables keep referencing the internal `users.id`; no business table references Supabase `auth.users` directly.

## Roles model

The project uses `roles` and `user_roles` tables instead of a single enum column. This was chosen because a single account may need multiple simultaneous permissions, for example `super_admin`, `professional`, and `patient` for end-to-end testing.

Built-in roles:

- `super_admin`
- `admin`
- `professional`
- `patient`

Every authenticated local user must have at least one of these application
roles so the client can select an access context. During login, a legacy or
pre-provisioned local record with no roles receives only the least-privileged
`patient` role. Professional, admin, and super-admin access is never inferred
from authentication and must still be explicitly provisioned.

`super_admin` is the only role allowed to change user roles. `admin` and `super_admin` can access administrative endpoints guarded by `get_current_admin`.

## Bootstrap first super admin

Create the Supabase Auth user first in Supabase. Then run:

```bash
python -m app.scripts.create_super_admin \
  --supabase-user-id "<supabase-auth-user-uuid>" \
  --email "admin@example.com" \
  --name "Initial Super Admin"
```

The script creates the local domain user if needed, links it to `users.supabase_user_id`, and grants `patient`, `professional`, `admin`, and `super_admin`.

## Create an admin

A `super_admin` can update roles through:

```http
PUT /api/users/{user_id}/roles
Authorization: Bearer <supabase-access-token>
Content-Type: application/json

{"roles": ["admin", "patient"]}
```

## Security audit notes

Fixed as part of this refactor:

- Removed hard-coded super-admin identity authorization.
- Removed backend password login and refresh-token ownership from the API; Supabase Auth owns identity/session lifecycle.
- Replaced `is_admin` authorization checks with role checks.
- Added JWT validation support for Supabase-issued tokens.
- Protected report and insight endpoints with authenticated user checks.

Still intentional:

- WhatsApp webhooks are not JWT-protected because Meta calls them directly; verification is done with the WhatsApp verify token on the GET challenge endpoint.
- `users.is_admin` remains as a deprecated compatibility flag for existing data and can be removed in a later cleanup after clients have moved to roles.

## Rollback plan

1. Revert the application commit.
2. Run Alembic downgrade from `0003` to `0002` if only the password-column removal must be reverted, or from `0002` to `0001` for the full roles/Supabase rollback.
3. Restore the previous backend auth implementation only if intentionally rolling back from Supabase Auth.

## Supabase lock-in assessment

The domain model is intentionally isolated from Supabase by storing only `users.supabase_user_id`. Business entities continue to reference `users.id`. Migrating to Auth0, Keycloak, or a custom JWT issuer would require replacing JWT validation and relinking the external identity ID field, but would not require rewriting monitoring, reports, anamneses, scheduler, or bot tables.

Estimated future migration difficulty: moderate. Authentication middleware changes are localized, but operational migration of external identity IDs and token validation configuration would still require careful planning.

## Backend-managed browser sessions

The browser must not receive, store, read, or manually forward Supabase `access_token` or `refresh_token` values. The API now exposes backend-owned auth endpoints under `/api/auth`:

- `POST /api/auth/login` authenticates with Supabase Auth server-to-server, resolves or creates the local user by Supabase `sub`, sets HttpOnly cookies, returns `UserRead`, and never returns tokens.
- `GET /api/auth/me` reads the HttpOnly access cookie, validates the Supabase JWT (`exp`, `iss`, `aud`, signature, and `sub`), resolves the local user and roles, and returns `UserRead`.
- `POST /api/auth/refresh` reads the HttpOnly refresh cookie on the server, calls Supabase refresh, rotates cookies when Supabase returns a new refresh token, and returns `204` without tokens.
- `POST /api/auth/logout` attempts Supabase logout, always expires local auth cookies, and is idempotent.
- `POST /api/auth/forgot-password`, `GET /api/auth/callback`, and `POST /api/auth/change-password` keep recovery/change-password tokens server-side and never return tokens in JSON.

### Cookie strategy decision

The implemented MVP uses Supabase tokens in HttpOnly cookies instead of an opaque server-side session. This is the smallest compatible change because the current protected-route dependencies already validate Supabase JWTs locally. Cookies are configured without `Domain`, with `Path=/` for the access token, `Path=/api/auth` for the refresh token, `HttpOnly=true`, `Secure=true` by default, and `SameSite=Lax` for access plus `SameSite=Strict` for refresh. The access cookie `Max-Age` follows Supabase `expires_in`; the refresh cookie uses a 30-day max age and is rotated whenever Supabase returns a replacement refresh token.

Preferred future hardening is an opaque `session_id` cookie backed by Redis or the database. In that model, access and refresh tokens stay server-side, refresh operations are locked per session, sessions can be revoked centrally, token material should be encrypted at rest, and a scheduled cleanup job should remove expired/revoked sessions.

### CORS and CSRF

Because cookies are sent automatically by browsers, CORS uses `allow_credentials=True` and explicit `CORS_ORIGINS`; wildcard origins must not be used with credentials. Configure local, staging, preview, and production frontend origins in `CORS_ORIGINS` as a comma-separated list.

Unsafe `/api` methods (`POST`, `PUT`, `PATCH`, `DELETE`) validate `Origin` against `CORS_ORIGINS`. Cookie-authenticated mutations also require double-submit CSRF protection with a `ha_csrf` cookie and matching `X-CSRF-Token` header. The frontend can obtain the current token from `GET /api/auth/csrf`; login and refresh also expose the newly rotated token in the `X-CSRF-Token` response header. Requests authenticated exclusively with `Authorization: Bearer` do not require CSRF because browsers do not attach that credential automatically. Login and forgot-password validate `Origin`; session-bound mutations such as refresh, logout, and change-password require CSRF. Auth responses include `Cache-Control: no-store`.

### Environment variables

- `SUPABASE_PROJECT_URL`: project URL used for Auth API calls and issuer derivation.
- `SUPABASE_ANON_KEY`: backend-only Supabase anon key used for Auth server-to-server password, refresh, recovery, and PKCE exchange calls.
- `SUPABASE_JWT_SECRET` or `SUPABASE_JWKS_URL`: JWT verification keys.
- `SUPABASE_JWT_AUDIENCE`: expected JWT audience, default `authenticated`.
- `SUPABASE_JWT_ISSUER`: optional explicit issuer.
- `AUTH_COOKIE_SECURE`: keep `true` in production; set `false` only for local HTTP development.
- `AUTH_COOKIE_SAMESITE`: access-cookie SameSite policy, default `lax`.
- `AUTH_REDIRECT_ALLOWLIST`: comma-separated allowed frontend redirect origins.
- `CORS_ORIGINS`: comma-separated allowed frontend origins.

### Supabase configuration

Set the Supabase Auth Site URL to the canonical frontend URL. Add explicit Redirect URLs for local, staging, preview, and production callback destinations that land on the backend-controlled callback flow, including `/api/auth/callback` where applicable. Password recovery email links should use the backend callback URL so the API can exchange the code and set HttpOnly cookies before redirecting to an allowlisted frontend destination. Keep recovery link expiration short enough for product requirements and rotate sessions after password changes according to incident-response policy.

### Rollout plan

1. Deploy backend with cookie endpoints while temporarily preserving Bearer-token compatibility for existing clients.
2. Configure `CORS_ORIGINS`, `AUTH_REDIRECT_ALLOWLIST`, `SUPABASE_ANON_KEY`, cookie security settings, and Supabase redirect URLs in each environment.
3. Update the Next.js frontend to call backend auth endpoints with `credentials: "include"`, stop using Supabase browser login, stop storing Supabase session in `localStorage`, and stop manually setting `Authorization`.
4. Verify login, refresh, logout, password recovery, CSRF, and authorization in staging.
5. Remove legacy Bearer-token compatibility after all clients use backend-managed sessions.

### Rollback plan

If rollout fails, revert the frontend to the previous Supabase browser login flow and keep the backend Bearer-token path enabled. Revert this backend change only after confirming no active clients depend on the cookie endpoints. Expire auth cookies for affected users during rollback to avoid ambiguous client state.
