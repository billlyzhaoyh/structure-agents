.DEFAULT_GOAL := help

PRE_COMMIT := uvx --from pre-commit==4.3.0 pre-commit
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
UV_TOOL_DIR ?= $(CURDIR)/.uv-tools
export UV_CACHE_DIR
export UV_TOOL_DIR

.PHONY: help sync lock hooks format format-check lint typecheck test build quality-all check check-all serve-api

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
	uv run mypy apps/api/src apps/api/tests

test: ## Run deterministic unit tests
	uv run pytest

build: ## Build the API wheel and source distribution
	uv build --package structagent-api --out-dir dist --no-build-isolation

serve-api: ## Start the local FastAPI service
	uv run uvicorn structagent_api.api:create_app --factory

quality-all: format-check lint typecheck test ## Always-run local quality gate

check: ## Run every pre-commit hook over the repository
	$(PRE_COMMIT) run --all-files --hook-stage manual

check-all: check build ## Run the complete repository gate
