<div align="center">

# ⚖️ VidhiSangh

**The integrated professional ecosystem for the legal profession.**

Networking · Legal Research · Practice Management · AI Productivity — in one secure, multi-tenant, cloud-native platform.

</div>

---

VidhiSangh brings together the capabilities of LinkedIn, Clio, PracticePanther, Harvey AI, LexisNexis, Westlaw, Microsoft Teams and Google Workspace into a single, purpose-built platform for advocates, law firms, corporate legal teams, researchers, and allied professionals.

> **Status (2026-09-27):** Core practice workflows and cross-feature integrations are implemented. Migrations run through **0047**; the frontend production build and backend import/route checks pass.
>
> **Resuming work / new machine? Read these (they are the portable project memory):**
> [`CLAUDE.md`](CLAUDE.md) (onboarding, run/test, conventions) · [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) (what's built) · [`docs/FUTURE_DELIVERABLES.md`](docs/FUTURE_DELIVERABLES.md) (what's left) · [`docs/ROADMAP.md`](docs/ROADMAP.md) (phase plan).

## Architecture at a glance

| Layer        | Technology |
|--------------|------------|
| Frontend     | Angular 21 (standalone, signals) · Angular Material · Tailwind CSS · NgRx Signal Store · PWA |
| Backend      | Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Async / Jobs | Celery · Redis |
| Database     | PostgreSQL 17 (row-level-security multi-tenancy, `pgvector` for embeddings) |
| Storage      | S3-compatible object storage (versioned documents) |
| Search       | Elasticsearch / OpenSearch |
| AI           | Pluggable LLM providers (Anthropic / OpenAI / Azure / local) · RAG · vector DB |
| Auth         | OAuth2 / OIDC · JWT (short-lived access + rotating refresh) · MFA · Passkeys |
| Delivery     | Docker · Kubernetes · Helm · NGINX · GitHub Actions |

Design principles: **Clean Architecture · Domain-Driven Design · SOLID · Repository pattern · CQRS where beneficial · Event-driven · API-first · Modular monolith (microservice-ready) · Security & Privacy by design.**

Read the full design in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), the data model in [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md), and the security posture in [`docs/SECURITY.md`](docs/SECURITY.md).

## Repository layout

```
VidhiSangh/
├── backend/          FastAPI application (clean architecture, DDD modules)
│   └── app/
│       ├── core/     config, logging, database, security primitives
│       ├── db/       declarative base + mixins
│       ├── middleware/  request-id, tenant context, security headers
│       ├── modules/  bounded contexts (tenancy, identity, audit, health, …)
│       └── api/v1/   versioned router aggregation
├── frontend/         Angular 21 workspace (core / shared / features / layout)
├── infra/            nginx, Kubernetes manifests, Helm chart
├── docs/             architecture, schema, security, roadmap
├── .github/workflows CI/CD pipelines (lint, test, SAST, SCA, build)
└── docker-compose.yml  full local stack (postgres, redis, minio, backend, frontend)
```

## Quick start (local development)

Prerequisites: Docker + Docker Compose (recommended), **or** Python 3.13 + Node 20+ + PostgreSQL 17 + Redis for a native run.

```bash
cp .env.example .env          # then edit secrets

# Option A — full stack via Docker
docker compose up --build

# Option B — native
#   backend
cd backend && python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
#   frontend (new terminal)
cd frontend && npm install && npm start
```

- API + interactive docs: http://localhost:8000/api/v1/docs
- Frontend: http://localhost:4200
- Health: http://localhost:8000/health

See [`backend/README.md`](backend/README.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md) for details.

## License

Proprietary — © VidhiSangh. All rights reserved.

## Product help

Open **Help & feature tour** in the app, or read the [user guide](docs/help/user-guide.md). The top-bar **Help** and light-bulb controls explain the current page. See [help maintenance and testing](docs/help/README.md) and [rollout validation](docs/ROLLOUT_VALIDATION.md).
