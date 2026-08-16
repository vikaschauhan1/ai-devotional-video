# Development

## Setup

```bash
make setup             # Python 3.12 venv via uv
make frontend-install  # npm deps
```

## Run

```bash
make backend    # uvicorn on :8000, reload on
make frontend   # next dev on :3000
```

## Test

```bash
make test                                        # fast suite (~15 s)
RUN_WHISPER_INTEGRATION=1 pytest tests/test_transcription.py::test_transcribe_real_whisper_integration -v
RUN_OLLAMA_INTEGRATION=1  pytest tests/test_lyrics.py::test_analyze_real_ollama_integration -v
```

Integration tests are gated so they don't pull heavy models in CI.

## Lint & format

```bash
make lint       # ruff + mypy + npm lint
make format     # ruff check --fix + ruff format
```

Ruff config lives in `pyproject.toml`. Per-file `E501` ignore for
`agent/prompts.py` because prompts are natural-language content, not
code.

## Adding a new adapter

1. Subclass the interface in `models/<kind>/base.py`.
2. Implement `generate(...)`.
3. Register it in `models/<kind>/__init__.py::get_<kind>_engine()`.
4. Update `.env.example` with the new engine name.
5. Add tests in `tests/test_<kind>.py`.

Example: [`models/llm/ollama.py`](../models/llm/ollama.py) added the
`ollama` engine behind the `LLMEngine` interface with no changes to
callers.

## Adding a new pipeline stage

Follow the pattern used by every existing stage:

- Pure logic in `pipeline/<stage>.py` (no DB, no FastAPI)
- Persistence + DB session in `backend/app/services/<stage>.py`
- Pydantic contract in `backend/app/schemas/<stage>.py`
- Endpoint in `backend/app/api/routes/pipeline.py`
- Test in `tests/test_<stage>.py`

Failure convention: raise a stage-specific domain exception
(`XxxServiceError`), let the route translate it into 404 / 409 / 500.

## Testing patterns

- FastAPI TestClient session lives at `tests/conftest.py`, isolates
  SQLite + STORAGE_ROOT under `/tmp`.
- Override LLM engines with `app.dependency_overrides[get_llm_engine]
  = lambda: FakeLLM(...)`. See `tests/test_scenes.py` for a queued
  FakeLLM that hands out canned payloads in order.
- Real FFmpeg is invoked with tiny inputs (~1 s WAVs, 320x320 clips)
  so tests stay fast.

## Database

SQLite via SQLAlchemy 2 sync ORM. Schema is PG-compatible (`String`,
`Integer`, `JSON`, `Enum`, timezone-aware `DateTime`). Point
`DATABASE_URL` at Postgres to switch — no code change required.

Alembic isn't wired yet; `Base.metadata.create_all` runs on startup.
Add migrations once the schema evolves.

## Job runner

`asyncio.create_task` on the FastAPI loop (`backend/app/services/jobs.py`).
No Redis, no worker process. Enough for single-user local dev.

To upgrade: replace `kick_off_generate_job` with an RQ / Arq enqueue,
run a worker outside uvicorn. The progress callback shape doesn't
change.

## Git

Working branch is `feature/phase-01-02-scaffold`. Commits are authored
as `Vikas Chauhan <vikkygp4all@gmail.com>` (personal). Never use the
work email on this repo.

Push only on explicit request. Origin: SSH via `git@github.com`, key at
`~/.ssh/id_ed25519.pub`.

## Common terminal commands used during development

```bash
# Rebuild everything cleanly
make clean && make setup && make frontend-install

# Run backend + frontend + open browser
make backend & sleep 3 && make frontend & sleep 8 && xdg-open http://127.0.0.1:3000

# Trigger a full pipeline from the CLI (project must exist with audio + lyrics)
python -m app generate <project-id> --burn-subtitles --scenes 6

# Preview a stored final MP4
mpv "$(python -m app render-status <project-id> | jq -r .path)"
```
