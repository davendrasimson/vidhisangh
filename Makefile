# VidhiSangh — developer convenience targets
# (Windows: use `make` via Git Bash / WSL, or run the underlying commands.)

.DEFAULT_GOAL := help
.PHONY: help up down logs be-install be-run be-test be-lint be-migrate be-revision fe-install fe-run fe-build seed fmt

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Start full local stack (docker compose)
	docker compose up --build

down: ## Stop stack and remove containers
	docker compose down

logs: ## Tail backend logs
	docker compose logs -f backend

# ─── Backend ────────────────────────────────────────────────────────
be-install: ## Install backend deps (editable + dev extras)
	cd backend && pip install -e ".[dev]"

be-run: ## Run API with reload
	cd backend && uvicorn app.main:app --reload

be-test: ## Run backend tests with coverage
	cd backend && pytest -q --cov=app --cov-report=term-missing

be-lint: ## Ruff + mypy
	cd backend && ruff check app tests && mypy app

be-migrate: ## Apply migrations
	cd backend && alembic upgrade head

be-revision: ## Autogenerate a migration: make be-revision m="message"
	cd backend && alembic revision --autogenerate -m "$(m)"

seed: ## Seed baseline roles/permissions + demo tenant
	cd backend && python -m app.scripts.seed

# ─── Frontend ───────────────────────────────────────────────────────
fe-install: ## Install frontend deps
	cd frontend && npm install

fe-run: ## Run Angular dev server
	cd frontend && npm start

fe-build: ## Production build
	cd frontend && npm run build

fmt: ## Format everything
	cd backend && ruff format app tests
	cd frontend && npx prettier --write "src/**/*.{ts,html,scss}"
