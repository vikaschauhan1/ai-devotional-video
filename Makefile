.PHONY: help setup venv backend frontend frontend-install test lint format clean

help:
	@echo "Common targets:"
	@echo "  setup            Install Python 3.12 via uv and create .venv"
	@echo "  frontend-install Install Node dependencies (npm ci)"
	@echo "  backend          Run the FastAPI backend"
	@echo "  frontend         Run the Next.js dev server"
	@echo "  test             Run pytest"
	@echo "  lint             Run ruff + mypy"
	@echo "  format           Auto-format with ruff"
	@echo "  clean            Remove caches and build artefacts"

setup:
	uv python install 3.12
	uv sync --python 3.12

frontend-install:
	cd frontend && npm ci

backend:
	uv run uvicorn backend.app.main:app --host $${APP_HOST:-127.0.0.1} --port $${APP_PORT:-8000} --reload

frontend:
	cd frontend && npm run dev

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run mypy backend agent workers pipeline models || true
	cd frontend && npm run lint

format:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .venv .uv-cache .pytest_cache .mypy_cache .ruff_cache
	rm -rf frontend/.next frontend/node_modules
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
