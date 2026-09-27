# VidhiSangh — Claude onboarding & project instructions

> **New machine / new session? START HERE.** This file is auto-loaded by Claude Code.
> The per-machine `.claude` memory does **not** travel with this folder, so the full
> project state now lives in-repo. Read these three, in order, before doing anything:
> 1. [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — everything that is **built** (the source of truth).
> 2. [docs/FUTURE_DELIVERABLES.md](docs/FUTURE_DELIVERABLES.md) — everything **to do** (deferred/parked work + why).
> 3. [docs/ROADMAP.md](docs/ROADMAP.md) — phase-by-phase plan with ✅/🚧/⬜ status.

## What this is
VidhiSangh is a **multi-tenant legal-profession SaaS** for advocates & law firms in India
(think LinkedIn + Clio + Harvey AI + LexisNexis). Phases 1–5 are complete; Phase 6
(platform/integrations/hardening) has all of its **buildable-without-external-infra** parts done.

## Stack
- **Backend**: Python 3.13, FastAPI, async SQLAlchemy 2, Alembic, PostgreSQL with **row-level security** (RLS) for tenant isolation. Modular monolith, DDD bounded contexts.
- **Frontend**: Angular 21 (standalone components, signals), Angular Material, Tailwind CSS.
- Location: `c:\GIT\VidhiSangh` (this folder). **Not currently a git repo** — see PROJECT_STATUS “Preserving work”.

## Run & test (Makefile targets exist — `make help`)
```
# Backend  (cwd: backend/)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload      # API → http://localhost:8000/api/v1/docs
.venv/Scripts/python.exe -m pytest -q                          # tests (SQLite, hermetic) — 112 passing
# Frontend (cwd: frontend/)
npm start                                                      # → http://localhost:4200
npx ng build                                                   # production build (use `> log 2>&1`, NOT `| tail`, when backgrounding — it hangs)
```
**On a fresh machine, recreate the environments** (`.venv/` and `node_modules/` are gitignored and may not be portable):
```
cd backend  && python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"
cd frontend && npm install
```
Tests run on **SQLite** and need no Postgres/Redis. Running the real app needs Postgres (see `.env.example`; copy to `backend/.env`).

## Conventions you MUST follow (match the existing code)
- **Module shape** (one bounded context per folder under `backend/app/modules/<name>/`): `models.py → schemas.py → repository.py → service.py → router.py`. Register the model in `app/db/base.py` (import + `__all__`) and the router in `app/api/v1/router.py`.
- **Every schema change = a new Alembic migration** in `backend/alembic/versions/` (sequential id `00NN_...`, `down_revision` chained). Latest is **0052**.
- **Tenant-scoped tables** extend `TenantScopedBase` and get an RLS policy in their migration (copy the `tenant_isolation` USING/WITH CHECK block from any recent migration, e.g. `0029_api_keys.py`). **Global/cross-tenant tables** (network, marketplace, notifications, oauth_states, webauthn_challenges) extend `AuditedBase` — no RLS. Repos still filter by `tenant_id` explicitly so isolation holds under the SQLite tests (no RLS there).
- **RBAC**: `require_permission("code")`; codes are catalogued in `app/modules/identity/rbac.py`. `has_permission` needs the EXACT code (no hierarchy). `org_admin` (the default signup role) holds every code via `ALL_PERMISSION_CODES`.
- **Pluggable seams** (real impl + mock/log fallback + `set_*` test hook, chosen by env): `app/core/storage.py`, `payments.py`, `channels.py` (notifications), `webhook_transport.py`, `oauth.py`, `webauthn.py`. Follow this pattern for any new external integration; tests inject the mock via `conftest.py`.
- **Async gotchas** (already hit): build a relationship collection BEFORE the first flush (appending to a flushed relationship → `MissingGreenlet`); `await session.refresh(obj)` before reading a server-side `updated_at` after a 2nd flush.
- **Dates are dd/mm/yyyy everywhere.** Never use `<input type="date">` / `datetime-local` (the browser renders them in its own locale — the user saw mm/dd/yyyy); use `<vs-date-input [(ngModel)]>` (`withTime` for date-times; model stays the ISO string the API expects). Display with `| date` (default is `dd/MM/yyyy` via `DATE_PIPE_DEFAULT_OPTIONS`; date-times `'dd/MM/yyyy, h:mm a'`), never a raw ISO string. `LOCALE_ID` is `en-IN`.
- **Frontend**: standalone signal components, `firstValueFrom`, `vs-*` CSS utility classes, design-token colours `brand`/`success`/`warning`/`danger`/`content`/`surface`/`line` (NOT `primary`/`emerald`/`red`). Admin screens live under `frontend/src/app/features/admin/`, nav is `layout/shell/shell.component.ts`, routes in `app.routes.ts`.

## Working style the user expects
- One coherent module/deliverable at a time; **write the tests**, then verify with the full `pytest` suite + a clean `ng build` before reporting.
- Build what's testable now; **defer anything that needs external infra** and record it in FUTURE_DELIVERABLES.md (the user explicitly wants deferred items revisited, not silently dropped).
- Keep PROJECT_STATUS.md, FUTURE_DELIVERABLES.md, and ROADMAP.md up to date as you go — they are now the persistent memory.
