# VidhiSangh — Backend

FastAPI backend for VidhiSangh — the integrated legal ecosystem platform.
Clean-architecture, domain-driven, multi-tenant, async throughout.

- **Stack:** Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · Celery · Redis · PostgreSQL 17 (`pgvector`)
- **API:** served under `/api/v1` · interactive docs at `/api/v1/docs`
- **Ops endpoints:** `GET /health` (liveness) · `GET /ready` (readiness) · `GET /metrics` (Prometheus)

---

## Prerequisites

- Python **3.13+**
- PostgreSQL **17** (with the `pgvector` extension) and Redis **7** — either natively or via the repo's `docker compose up` (recommended for local dev).
- Optional: MinIO/S3 (object storage) and OpenSearch 2 for the storage/search features.

## Install

All dependencies are declared in `pyproject.toml` (PEP 621). From this `backend/` directory:

```bash
python -m venv .venv
. .venv/Scripts/activate            # Windows (PowerShell/Git Bash)
# source .venv/bin/activate         # macOS / Linux

# Full local toolchain (tests, lint, storage, search, AI providers):
pip install -e ".[dev,storage,search,ai]"

# Minimal (app + tests only):
# pip install -e ".[dev]"
```

Optional extras: `storage` (boto3/S3), `search` (opensearch-py), `ai` (anthropic/openai), `dev` (pytest, ruff, mypy, faker).

## Configuration

Configuration is read from environment variables prefixed **`VS_`** (see the
repo-root [`.env.example`](../.env.example) for the full, documented list).
Copy it and fill in values:

```bash
cp ../.env.example ../.env          # never commit .env
```

Key variables: `VS_SECRET_KEY`, `VS_POSTGRES_HOST/PORT/USER/PASSWORD/DB`,
`VS_REDIS_URL`, `VS_CELERY_BROKER_URL`, `VS_S3_*`, `VS_OPENSEARCH_URL`,
`VS_ANTHROPIC_API_KEY`. In production, source these from a secrets manager —
never a file.

## Database migrations (Alembic)

```bash
alembic upgrade head                # apply all migrations
alembic revision --autogenerate -m "describe change"   # create a new migration
alembic downgrade -1                # roll back one revision
```

## Run

```bash
# Dev server with hot reload
uvicorn app.main:app --reload

# Production (gunicorn + uvicorn workers)
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000 --timeout 60 --access-logfile -
```

- API + docs: http://localhost:8000/api/v1/docs
- Health: http://localhost:8000/health · Readiness: http://localhost:8000/ready

### Background worker (Celery)

```bash
celery -A app.worker.celery_app worker --loglevel=info
```

## Seed data

Idempotent seeder for the RBAC catalog (permissions + system roles):

```bash
python -m app.scripts.seed
```

## Tests

```bash
pytest                              # full suite (asyncio auto-mode)
pytest --cov=app --cov-report=term-missing   # with coverage (fails under 85%)
pytest tests/path/to/test_x.py -k name       # focused run
```

## Lint & type-check

```bash
ruff check .                        # lint
ruff format .                       # auto-format  (use --check in CI)
mypy app                            # strict static typing
```

## Project layout

```
backend/
├── app/
│   ├── main.py         # FastAPI app factory: middleware, exception handlers,
│   │                   #   /metrics mount, health router, /api/v1 router
│   ├── worker.py       # Celery application (app.worker.celery_app)
│   ├── core/           # settings, logging, database engine, security primitives
│   ├── db/             # declarative base + mixins
│   ├── middleware/     # request-id, tenant context, security headers
│   ├── modules/        # bounded contexts: tenancy, identity, audit, health, …
│   ├── shared/         # cross-cutting helpers
│   ├── api/v1/         # versioned router aggregation
│   └── scripts/        # operational scripts (e.g. seed.py)
├── alembic/            # migration environment + versions
├── alembic.ini
├── tests/
└── pyproject.toml      # dependencies, ruff, mypy, pytest, coverage config
```

## Docker

Built via the multi-stage [`Dockerfile`](./Dockerfile) (`dev` and `prod`
targets). For the full local stack (Postgres, Redis, MinIO, OpenSearch,
backend, worker, frontend) use the repo-root `docker compose up --build`.
