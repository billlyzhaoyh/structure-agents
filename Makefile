.DEFAULT_GOAL := help

PRE_COMMIT := uv run pre-commit
PRE_COMMIT_HOME ?= $(CURDIR)/.pre-commit-cache
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
export PRE_COMMIT_HOME
export UV_CACHE_DIR

.PHONY: help sync lock hooks format format-check lint typecheck test test-web build contracts-export contracts-check quality-all check check-all serve-api serve-web

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install exact dependencies from uv.lock
	uv sync --all-packages --frozen

lock: ## Refresh uv.lock after an intentional dependency change
	uv lock

hooks: ## Install pre-commit and pre-push hooks
	@test -d .git || (echo "Run git init -b main first" >&2; exit 1)
	$(PRE_COMMIT) install --hook-type pre-commit --hook-type pre-push

format: ## Format Python and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

format-check: ## Check Python formatting without changing files
	uv run ruff format --check .

lint: ## Lint Python
	uv run ruff check .

typecheck: ## Run strict static type checking
	uv run mypy apps/api/src apps/api/tests scripts

test: ## Run deterministic unit tests
	uv run pytest

test-web: ## Run deterministic frontend interaction-model tests
	node --test apps/web/tests/*.test.mjs

build: ## Build the API wheel and source distribution
	uv build --package structagent-api --out-dir dist --no-build-isolation

contracts-export: ## Regenerate committed V1 JSON Schema snapshots
	uv run python scripts/export_contracts.py

contracts-check: ## Reject drift between models and committed schemas
	uv run python scripts/export_contracts.py --check

serve-api: ## Start the local FastAPI service
	uv run uvicorn structagent_api.api:create_app --factory

serve-web: ## Serve the dependency-free Decision OS demo
	python3 -m http.server 4173 --directory apps/web

quality-all: format-check lint typecheck test test-web contracts-check ## Always-run local quality gate

check: ## Run every pre-commit hook over the repository
	$(PRE_COMMIT) run --all-files --hook-stage manual

check-all: check build ## Run the complete repository gate
