# AI Devotional Video Studio

Local-first AI pipeline that turns a Hindi / Sanskrit devotional audio
recording (bhajan, mantra, aarti, stotra, chalisa, kirtan, classical
devotional song) into a cinematic short video.

Runs entirely on a laptop. No mandatory cloud APIs. Every heavy model
sits behind a swappable adapter, so this repo works from a CPU-only
laptop up to a CUDA workstation.

## Status

**MVP loop closed.** All spec phases 1-19 are implemented end-to-end:
audio + lyrics + LLM analysis + LLM scene planning + still generation
+ Ken-Burns clips + FFmpeg composition with Devanagari subtitles.
See [docs/PIPELINE.md](docs/PIPELINE.md) for the flow.

Optional phases still pending: neural image / video engines (Phase 11/13
real), lip sync (Phase 15), TTS singing (Phase 22), WebSocket progress,
Docker packaging. Everything else works today.

## Requirements

- Linux (developed on Ubuntu 26.04)
- Python 3.12 (auto-installed by `uv`)
- Node.js 20+
- FFmpeg 6+ with libass
- Optional: NVIDIA GPU + CUDA for future neural adapters
- Optional: Ollama for the real LLM engine
- Optional: `Noto Sans Devanagari` font for burned subtitles

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for step-by-step setup.

## Quick start

```bash
# Install everything (Python 3.12 via uv, Python deps, frontend deps)
make setup
make frontend-install

# Terminal 1 — backend on http://127.0.0.1:8000
make backend

# Terminal 2 — frontend on http://127.0.0.1:3000
make frontend

# Optional Terminal 3 — Ollama for the real LLM
ollama serve &
ollama pull qwen2.5:3b-instruct
# Then flip LLM_ENGINE=ollama in .env
```

Open http://127.0.0.1:3000 and drive the whole flow from the browser:
create a project, upload MP3, paste lyrics, click **GENERATE VIDEO**,
watch the six-stage progress timeline light up live.

## CLI

```bash
python -m app health
python -m app new-project --name "Shiva bhajan" --deity Shiva --style shiva-himalayan
python -m app upload-audio <project-id> bhajan.mp3
python -m app set-lyrics <project-id> - < lyrics.txt
python -m app generate <project-id> --burn-subtitles --scenes 6
python -m app render-status <project-id>
```

## API surface

19 operations across 15 paths. Swagger UI at http://127.0.0.1:8000/docs.

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | status + engine names |
| `POST /api/projects` | create project |
| `GET  /api/projects/{id}` | fetch |
| `PATCH /api/projects/{id}` | update |
| `DELETE /api/projects/{id}` | delete |
| `POST /api/projects/{id}/audio` | upload MP3/WAV/M4A/FLAC |
| `POST /api/projects/{id}/lyrics` | save lyrics text |
| `POST /api/projects/{id}/references` | upload reference PNG/JPG |
| `GET /api/projects/{id}/references` | list |
| `DELETE /api/projects/{id}/references/{ref_id}` | delete |
| `POST /api/projects/{id}/transcribe` | faster-whisper |
| `POST /api/projects/{id}/analyze` | LLM lyrics analysis |
| `POST /api/projects/{id}/plan-scenes` | LLM scene plan |
| `POST /api/projects/{id}/generate-images` | placeholder stills |
| `POST /api/projects/{id}/generate-videos` | Ken-Burns clips |
| `POST /api/projects/{id}/render` | composite final MP4 |
| `GET  /api/projects/{id}/render` | latest final |
| `POST /api/projects/{id}/generate` | full pipeline (blocking) |
| `POST /api/projects/{id}/generate-async` | full pipeline (background job) |
| `GET  /api/projects/{id}/scenes` | list scenes |
| `GET  /api/jobs/{job_id}` | poll job progress |
| `POST /api/jobs/{job_id}/cancel` | mark cancelled |

Storage is served at `/storage/...` for direct browser playback.

## Layout

```
ai-devotional-video/
├── frontend/    Next.js 16 + TypeScript + Tailwind 4
├── backend/     FastAPI + Pydantic + SQLAlchemy 2 (SQLite)
├── agent/       LLM prompts + orchestration
├── pipeline/    audio_analysis, transcription, compositor
├── models/      adapter interfaces + concrete engines
│   ├── llm/     ollama.py, stub.py
│   ├── image/   placeholder.py
│   ├── video/   procedural.py
│   ├── lipsync/ (interface only)
│   └── tts/     (interface only)
├── app/         typer CLI (python -m app)
├── storage/     local file storage
├── tests/       pytest + real FFmpeg
├── docs/        HARDWARE, ARCHITECTURE, PIPELINE, MODELS, INSTALLATION
└── docker/      (empty; future work)
```

## Docs

- [docs/INSTALLATION.md](docs/INSTALLATION.md) — dependency install
- [docs/HARDWARE.md](docs/HARDWARE.md) — hardware assessment on this host
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module layout + adapter model
- [docs/PIPELINE.md](docs/PIPELINE.md) — end-to-end flow
- [docs/MODELS.md](docs/MODELS.md) — installed models, licenses, sizes

## License

Apache-2.0 for this repository. Individual AI models keep their own
licenses — see [docs/MODELS.md](docs/MODELS.md).
