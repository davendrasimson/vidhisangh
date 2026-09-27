# syntax=docker/dockerfile:1.7
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — Backend (FastAPI) image
#  Multi-stage:  base → dev  |  base → prod
#  Build dev :  docker build --target dev  -t vidhisangh-backend:dev  .
#  Build prod:  docker build --target prod -t vidhisangh-backend:prod .
# ════════════════════════════════════════════════════════════════════

# ─── base ───────────────────────────────────────────────────────────
# Shared foundation: Python runtime, system build/runtime deps, an
# unprivileged user, and a workdir. Both dev and prod derive from this.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# System dependencies:
#   build-essential + libpq-dev  → compile asyncpg/psycopg/argon2 wheels
#   curl                         → container HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (fixed uid/gid for predictable K8s securityContext).
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home --home-dir /home/app app

WORKDIR /app
RUN pip install --upgrade pip

# ─── dev ────────────────────────────────────────────────────────────
# Full toolchain (tests, lint, type-check) + hot-reload. Source is also
# bind-mounted by docker-compose, so the copy here is a sensible default.
FROM base AS dev

# Dependency layer: copy only metadata first so `pip install` is cached
# and re-run only when dependencies change (not on every source edit).
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install -e ".[dev,storage,search,ai]"

# Application source (editable install already points at /app/app).
COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ─── prod ───────────────────────────────────────────────────────────
# Lean-ish runtime: production extras only (no dev/test tooling), only
# the code needed to run and migrate, gunicorn + uvicorn workers.
FROM base AS prod

# Cached dependency layer (production extras only — no dev).
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install -e ".[storage,search,ai]"

# Copy only what the running app + migrations need.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 4 uvicorn workers behind gunicorn; access logs to stdout for the log pipeline.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-"]
