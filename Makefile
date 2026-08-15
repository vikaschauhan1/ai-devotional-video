.PHONY: help setup venv backend frontend test lint format clean

help:
	@echo "Common targets:"
	@echo "  setup       Install Python 3.12 via uv and create .venv"
	@echo "  backend     Run the FastAPI backend (added in Phase 5)"
	@echo "  frontend    Run the Next.js frontend (added in Phase 5)"
	@echo "  test        Run pytest"
	@echo "  lint        Run ruff + mypy"
	@echo "  format      Auto-format with ruff"
	@echo "  clean       Remove caches and build artefacts"

setup:
	uv python install 3.12
	uv sync --python 3.12

backend:
	uv run uvicorn backend.app.main:app --host $${APP_HOST:-127.0.0.1} --port $${APP_PORT:-8000} --reload

frontend:
	cd frontend && npm run dev

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run mypy backend agent workers pipeline models || true

format:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	rm -rf .venv .uv-cache .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
