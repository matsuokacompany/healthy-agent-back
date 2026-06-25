# Supabase Auth and application authorization

## Current architecture

Authentication is delegated to Supabase Auth. Clients authenticate with Supabase and send the Supabase access token as a Bearer token to this API. The backend validates that JWT and resolves it to a local `users` record through `users.supabase_user_id`.

Authorization remains local to this application. Business tables keep referencing the internal `users.id`; no business table references Supabase `auth.users` directly.

## Roles model

The project uses `roles` and `user_roles` tables instead of a single enum column. This was chosen because a single account may need multiple simultaneous permissions, for example `super_admin`, `professional`, and `patient` for end-to-end testing.

Built-in roles:

- `super_admin`
- `admin`
- `professional`
- `patient`

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
