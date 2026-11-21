# syntax=docker/dockerfile:1.7
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — Backend (FastAPI) image
#  Multi-stage:  base → dev  |  base → prod
#  Build dev :  docker build --target dev  -t vidhisangh-backend:dev  .
#  Build prod:  docker build --target prod -t vidhisangh-backend:prod .
#
#  Supply chain (A-12 / A-28):
#    - base image pinned by digest (python:3.13-slim, multi-arch index,
#      resolved 2026-09-27) — bump deliberately, with the tag comment
#    - dependencies installed from the hash-pinned lock files with
#      `--require-hashes`: a substituted or tampered wheel fails the build
#    - no build toolchain in the runtime image (wheels only)
# ════════════════════════════════════════════════════════════════════

# ─── base ───────────────────────────────────────────────────────────
# python:3.13-slim
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_REQUIRE_HASHES=1 \
    PIP_ONLY_BINARY=:all: \
    PYTHONPATH=/app

# Runtime system deps only: libpq for psycopg/asyncpg, curl for HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home --home-dir /home/app app

WORKDIR /app

# ─── dev ────────────────────────────────────────────────────────────
# Full toolchain (tests, lint, type-check) + hot-reload. Source is also
# bind-mounted by docker-compose, so the copy here is a sensible default.
FROM base AS dev

# Dependency layer first so it is cached until the lock changes.
COPY requirements-dev.lock ./
RUN pip install --require-hashes --no-deps -r requirements-dev.lock

# Application source: `app` is importable via PYTHONPATH — no package install,
# so nothing is fetched outside the hash-verified lock.
COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ─── prod ───────────────────────────────────────────────────────────
# Runtime only: production lock (storage/search/ai extras, no dev tooling),
# only the code needed to run and migrate, gunicorn + uvicorn workers.
FROM base AS prod

COPY requirements.lock ./
RUN pip install --require-hashes --no-deps -r requirements.lock

# Only what the running app + migrations need (importable via PYTHONPATH).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# gunicorn with uvicorn workers; access logs to stdout for the log pipeline.
# --forwarded-allow-ips is the loopback/pod proxy only: X-Forwarded-* from any
# other peer is ignored (A-2). Override VS_GUNICORN_WORKERS per node size.
CMD ["sh", "-c", "exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${VS_GUNICORN_WORKERS:-4} -b 0.0.0.0:8000 --timeout 60 --graceful-timeout 30 --forwarded-allow-ips ${VS_TRUSTED_PROXY_IPS:-127.0.0.1} --access-logfile -"]
