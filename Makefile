.DEFAULT_GOAL := help

PRE_COMMIT := uv run pre-commit
PRE_COMMIT_HOME ?= $(CURDIR)/.pre-commit-cache
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
SPIKE_ENV_ARGS := $(if $(wildcard .env),--env-file .env,)
export PRE_COMMIT_HOME
export UV_CACHE_DIR

.PHONY: help sync lock hooks format format-check lint typecheck test build contracts-export contracts-check quality-all check check-all serve-api daytona-spike-sync daytona-spike-check daytona-spike-run smoke-openai-api smoke-codex-sdk smoke-providers

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

build: ## Build the API wheel and source distribution
	uv build --package structagent-api --out-dir dist --no-build-isolation

contracts-export: ## Regenerate committed V1 JSON Schema snapshots
	uv run python scripts/export_contracts.py

contracts-check: ## Reject drift between models and committed schemas
	uv run python scripts/export_contracts.py --check

serve-api: ## Start the local FastAPI service
	uv run uvicorn structagent_api.api:create_app --factory

daytona-spike-sync: ## Install the separately locked provider spike dependencies
	uv sync --all-packages --group daytona-spike --group codex-spike --frozen

daytona-spike-check: ## Run deterministic checks for all provider spikes
	uv run --frozen --group daytona-spike --group codex-spike mypy spikes/daytona_agents_sdk
	uv run --frozen --group daytona-spike --group codex-spike python -m pytest spikes/daytona_agents_sdk/tests

daytona-spike-run: ## Run the live keyless Agents SDK to Daytona CPU canary
	uv run $(SPIKE_ENV_ARGS) --frozen --group daytona-spike python -m spikes.daytona_agents_sdk.smoke

smoke-openai-api: ## Run the live OpenAI Agents SDK to Daytona smoke
	uv run $(SPIKE_ENV_ARGS) --frozen --group daytona-spike python -m spikes.daytona_agents_sdk.live openai-api

smoke-codex-sdk: ## Run the live local Codex SDK to Daytona smoke
	uv run $(SPIKE_ENV_ARGS) --frozen --group daytona-spike --group codex-spike python -m spikes.daytona_agents_sdk.live codex-sdk

smoke-providers: ## Run both live model-provider to Daytona smokes
	uv run $(SPIKE_ENV_ARGS) --frozen --group daytona-spike --group codex-spike python -m spikes.daytona_agents_sdk.live all

quality-all: format-check lint typecheck test contracts-check ## Always-run local quality gate

check: ## Run every pre-commit hook over the repository
	$(PRE_COMMIT) run --all-files --hook-stage manual

check-all: check build ## Run the complete repository gate
