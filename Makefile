# Every target the lanes and the hub use. Frozen: change it only after a brain block.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv

help: ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## once per clone or worktree: git hooks, Python env, web deps when present
	git config core.hooksPath scripts/githooks
	$(UV) sync --frozen
	@if [ -f web/package.json ]; then pnpm install --frozen-lockfile; fi

check: check-py check-web ## everything the hub runs before a merge

check-py: ## ruff, pytest and the openapi.json drift check
	$(UV) sync --frozen --quiet
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run pytest
	@if [ -f openapi.json ] && [ -f alinka/api/openapi.py ]; then \
	  $(UV) run python -m alinka.api.openapi | diff -q - openapi.json >/dev/null \
	  || { echo "openapi.json is stale: run make openapi"; exit 1; }; fi

check-web: ## typecheck, unit tests and build of web/ once it exists
	@if [ -f web/package.json ]; then \
	  pnpm install --frozen-lockfile --silent \
	  && pnpm --filter ./web run typecheck \
	  && pnpm --filter ./web run test \
	  && pnpm --filter ./web run build; \
	else echo "web/ not scaffolded yet: skipped"; fi

fmt: ## format and autofix Python
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

test: ## Python tests only
	$(UV) run pytest

db-up: ## start local Postgres (compose.yaml)
	docker compose up -d --wait db

db-down: ## stop local Postgres
	docker compose down

openapi: ## Lane D: write openapi.json from the FastAPI app
	$(UV) run python -m alinka.api.openapi > openapi.json

eval: ## Lane A: evaluation in replay mode, writes evals/report.json and EVAL_REPORT.md
	$(UV) run python -m evals.run_eval

api: ## Lane D: the API on :8000 in replay mode
	$(UV) run uvicorn alinka.api.app:app --reload --port 8000

web: ## Lane E: the web dev server, proxying /api to :8000
	pnpm --filter ./web run dev

.PHONY: help setup check check-py check-web fmt test db-up db-down openapi eval api web
