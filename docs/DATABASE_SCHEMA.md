# VidhiSangh — Database Schema

PostgreSQL 17. Conventions applied to every table:

- **UUID** primary keys (`id`), non-enumerable.
- **Audit timestamps** `created_at` / `updated_at` (DB-managed, `timestamptz`).
- **Soft delete** `deleted_at` (nullable) — records are hidden, not destroyed.
- **Tenant scoping** `tenant_id` + a **row-level-security** policy on tenant-owned tables.
- Deterministic constraint naming (see `app/db/base_class.py`) for clean migrations.
- `pgvector` extension enabled for future embedding columns (RAG / semantic search).

## Phase 1 (implemented) — core schema

Migration: `alembic/versions/0001_initial_core_schema.py`.

### `tenants` (global)
The customer workspace. Not itself tenant-scoped.

| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| name | varchar(200) | |
| slug | varchar(80) | unique, URL-safe |
| type | varchar(32) | individual / small_firm / large_firm / enterprise / government |
| status | varchar(32) | trial / active / suspended / cancelled |
| plan | varchar(32) | free / solo / team / firm / enterprise |
| region | varchar(32) | data-residency (e.g. ap-south-1) |
| primary_contact_email | varchar(320) | |
| settings | json | feature flags / branding / limits |
| created_at, updated_at, deleted_at | timestamptz | |

### `permissions` (global catalog)
Fine-grained `module:action` capabilities. Seeded from `identity/rbac.py`.

| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| code | varchar(100) | unique, e.g. `matter:create` |
| name | varchar(150) | |
| description | varchar(400) | |
| module | varchar(60) | indexed |

### `roles`
System roles (`tenant_id IS NULL`) shipped with the platform + future tenant-custom roles.

| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| tenant_id | uuid FK→tenants | nullable (null ⇒ system role) |
| code | varchar(60) | unique per tenant (`roles_tenant_code`) |
| name | varchar(100) | |
| is_system | bool | |

### `role_permissions` (M:N)
`(role_id, permission_id)` composite PK.

### `users` (tenant-scoped, RLS)

| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| tenant_id | uuid FK→tenants | RLS key; `(tenant_id, email)` unique |
| email | varchar(320) | |
| phone | varchar(20) | |
| hashed_password | varchar(255) | Argon2id (nullable for SSO-only accounts) |
| full_name / display_name / avatar_url | | |
| is_active / is_email_verified / is_superuser | bool | |
| mfa_enabled | bool | |
| mfa_secret | varchar(255) | **encrypted at rest** (Fernet/`EncryptedString`) |
| failed_login_count | int | lockout counter |
| locked_until / last_login_at | timestamptz | |

### `user_roles` (M:N)
`(user_id, role_id)` composite PK.

### `refresh_tokens` (tenant-scoped, RLS)
Rotating, opaque tokens (stored as SHA-256 hashes).

| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| tenant_id, user_id | uuid FK | |
| token_hash | varchar(128) | indexed |
| expires_at / revoked_at | timestamptz | |
| replaced_by_id | uuid self-FK | rotation lineage → **reuse detection** |
| device_label / ip_address / user_agent | | device/session context |

### `mfa_backup_codes` (tenant-scoped, RLS)
Single-use, hashed. `used_at` marks consumption.

### `trusted_devices` (tenant-scoped, RLS)
Remembered devices: `device_fingerprint`, `label`, `last_seen_at`, `trusted_until`.

## Row-level security

Applied to `users`, `refresh_tokens`, `mfa_backup_codes`, `trusted_devices`
(and `roles`, which also permits system rows):

```sql
CREATE POLICY tenant_isolation ON <table>
  USING (
    current_setting('app.bypass_rls', true) = 'on'
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  )
  WITH CHECK ( … same … );
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
```

## Entity relationships (Phase 1)

```
tenants 1──* users 1──* refresh_tokens
   │            │  1──* mfa_backup_codes
   │            │  1──* trusted_devices
   │            *──* roles (user_roles)
   *──* roles (tenant-custom; system roles have tenant_id NULL)
roles *──* permissions (role_permissions)
```

## Roadmap tables (per functional module)

Each module introduces its own migration. Indicative core entities:

- **Profile:** `professional_profiles`, `bar_verifications`, `practice_areas`, `endorsements`, `recommendations`.
- **Network:** `posts`, `comments`, `reactions`, `connections`, `follows`, `groups`, `messages`.
- **Matters:** `matters`, `hearings`, `parties`, `tasks`, `notes`, `matter_documents`.
- **Documents:** `documents`, `document_versions`, `annotations`, `signatures`.
- **Billing:** `clients`, `invoices`, `invoice_lines`, `time_entries`, `payments`, `trust_ledger`.
- **CRM:** `leads`, `pipelines`, `consultations`.
- **Research/AI:** `judgments`, `citations`, `research_queries`, `document_embeddings (vector)`.
- **Platform:** `audit_logs` (immutable), `notifications`, `feature_flags`, `subscriptions`.

All follow the same base conventions (UUID, audit, soft-delete, `tenant_id` + RLS).
