# VidhiSangh — Architecture

> Status: Phase 1 (Foundation) implemented. This document describes the target
> architecture and the parts already realised in code.

## 1. Guiding principles

| Principle | How it is applied |
|-----------|-------------------|
| **Clean Architecture** | Domain/service logic is HTTP- and DB-framework agnostic. Routers → services → repositories → models. |
| **Domain-Driven Design** | Code is organised by **bounded context** under `app/modules/*` (tenancy, identity, …), each owning its models, schemas, repository, service and router. |
| **SOLID** | Small, single-responsibility services; dependencies injected (sessions, repositories) rather than constructed inline. |
| **Repository pattern** | All persistence access goes through repositories; services never emit raw SQL. |
| **API-first** | Every capability is a versioned REST endpoint documented via OpenAPI (`/api/v1/docs`). |
| **Modular monolith, microservice-ready** | One deployable today; modules are cleanly separable into services later because they share nothing but the DB contract and event bus. |
| **Security & privacy by design** | RLS tenant isolation, Argon2id, rotating refresh tokens, column encryption, strict headers — see [SECURITY.md](SECURITY.md). |

## 2. System context

```
                     ┌───────────────────────────────────────────┐
   Browser / PWA ───▶│  NGINX edge  (TLS 1.3, CSP, rate limit)    │
   Mobile (PWA)      └───────┬───────────────────────┬───────────┘
                             │ / (static SPA)         │ /api/v1
                     ┌───────▼────────┐       ┌───────▼────────────┐
                     │ Angular 21 SPA │       │  FastAPI (ASGI)    │
                     └────────────────┘       │  modular monolith  │
                                              └───┬───────┬────┬───┘
                        ┌──────────────┬──────────┘       │    └─────────────┐
                 ┌──────▼─────┐ ┌──────▼──────┐   ┌────────▼──────┐   ┌───────▼──────┐
                 │PostgreSQL17│ │   Redis     │   │ Object store  │   │ OpenSearch   │
                 │ (RLS,      │ │ cache/queue │   │ (S3/MinIO)    │   │ search       │
                 │  pgvector) │ │ celery brkr │   │ documents     │   │              │
                 └────────────┘ └──────┬──────┘   └───────────────┘   └──────────────┘
                                ┌──────▼──────┐
                                │Celery worker│  OCR · AI drafting · notifications · indexing
                                └─────────────┘
```

## 3. Backend layering (per module)

```
router.py      HTTP boundary — request/response, status codes, dependencies (RBAC).
   │
schemas.py     Pydantic v2 DTOs — validation & serialization contracts.
   │
service.py     Use-cases / business rules — transactional, framework-agnostic.
   │
repository.py  Persistence — SQLAlchemy queries, the ONLY place with SQL.
   │
models.py      SQLAlchemy ORM aggregates (mapped to tables).
```

Cross-cutting concerns live in `app/core` (config, logging, security, crypto,
database, deps, exceptions, pagination, ratelimit) and `app/middleware`
(request-id/context, security headers).

### Request lifecycle
1. `RequestContextMiddleware` assigns a correlation id and binds structured-log context.
2. CORS / GZip / security-headers middleware run.
3. Route dependencies resolve: bearer token → `CurrentUser`; a tenant-scoped DB
   session is opened with the RLS `app.current_tenant` GUC set from the token.
4. Optional `require_permission(...)` guards enforce RBAC.
5. The service executes within the session's transaction (commit on success,
   rollback on error). Domain errors become RFC-9457 problem responses.

## 4. Multi-tenancy

**Model:** shared database, shared schema, **row-level security (RLS)** keyed on
`tenant_id`. Chosen as the default because it maximises resource efficiency
while the database itself enforces isolation.

- Every tenant-owned table extends `TenantScopedBase` (adds indexed `tenant_id`).
- A per-transaction Postgres GUC `app.current_tenant` is set from the caller's
  JWT; RLS policies compare `tenant_id` to it (`FORCE ROW LEVEL SECURITY` makes
  this apply even to the table owner).
- `app.bypass_rls` is a narrowly-scoped escape hatch used **only** by the
  authentication service and migrations/seed (operations that must run before a
  tenant context exists, e.g. login-by-email).
- **Evolution path:** schema-per-tenant and dedicated-database options are
  anticipated (the `Tenant.region` column already supports data-residency
  routing) without changing the domain code.

See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the physical model.

## 5. Identity & access

- **AuthN:** email+password (Argon2id) today; OAuth2/OIDC social logins, OTP,
  passkeys and biometric are on the roadmap. Short-lived JWT access tokens +
  opaque, **rotating** refresh tokens with **reuse detection**. TOTP MFA with
  hashed backup codes. Account lockout on repeated failures.
- **AuthZ:** RBAC — a global permission catalog (`module:action`) bundled into
  system roles (and future tenant-custom roles). ABAC hooks (e.g. "client sees
  only their own matters") layer on top per-module. The catalog is data-driven
  (`app/modules/identity/rbac.py`, installed by the seeder).

## 6. Frontend

Angular 21 standalone + signals. Structure:

```
core/     singletons: auth (signal store), token custody, HTTP interceptors
          (attach token + silent refresh, error toasts), route guards
          (auth, permission), theme, tenant, notifications, typed models.
shared/   reusable UI + design-token utilities (Tailwind + Material).
layout/   authenticated app shell (responsive sidenav + top bar).
features/ lazy-loaded feature areas (auth, dashboard, … per roadmap).
```

- **State:** Angular signals (the same reactive core NgRx Signal Store builds
  on); `AuthService` exposes `user`, `isAuthenticated`, `permissions` as signals.
- **Design system:** CSS custom-property tokens drive both Tailwind and Angular
  Material; light/dark via a `.dark` class with a `system` option. WCAG 2.2 AA
  focus handling.
- **PWA:** service worker + manifest for offline shell and installability.

## 7. Asynchronous & event-driven

- **Celery + Redis** for background jobs (OCR, AI drafting, notifications,
  digests, search indexing). Tasks live with their owning module.
- Domain events (roadmap) published on a lightweight bus for cross-module
  reactions (e.g. "MatterCreated" → index for search, notify team) — the seam
  that later enables extracting microservices.

## 8. Observability

- **Structured logs** (structlog; JSON in prod) with request-id + tenant context.
- **Metrics** exposed at `/metrics` (Prometheus).
- **Health**: `/health` (liveness) and `/ready` (readiness with dependency checks).
- **Tracing**: OpenTelemetry instrumentation hooks (roadmap: exporter wiring).

## 9. Technology summary

Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · Celery ·
Redis · PostgreSQL 17 (pgvector) · S3-compatible storage · OpenSearch ·
Angular 21 · Angular Material · Tailwind · Docker · Kubernetes · Helm · NGINX ·
GitHub Actions.
