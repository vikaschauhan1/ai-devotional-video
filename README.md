# AI Devotional Video Studio

Local-first AI pipeline that turns a Hindi / Sanskrit devotional audio
recording (bhajan, mantra, aarti, stotra, chalisa, shlok, kirtan,
classical devotional song) into a cinematic short video.

Runs on a laptop. No mandatory paid APIs. Every heavy model sits behind
a swappable adapter, so this repo works from a CPU-only laptop up to a
CUDA workstation.

## Status

**Phase 2 — project skeleton.** Directory structure, docs and adapter
interfaces are in place. Backend, frontend and pipeline implementations
follow in subsequent phases (see `docs/ARCHITECTURE.md` and the phase
plan in the project brief).

## Requirements

- Linux (developed on Ubuntu 26.04)
- Python 3.12 (installed automatically through `uv`)
- Node.js 20+ (24 works)
- FFmpeg 6+ with libass (system `ffmpeg`)
- Optional: NVIDIA GPU with CUDA 12 for real video generation and MuseTalk
- Optional: Docker + Compose for the Redis job queue

## Quick start

```bash
# 1. Install python 3.12 into a project-local .venv (uv handles it)
make setup

# 2. Run backend (once Phase 5 lands)
make backend

# 3. Run frontend (once Phase 5 lands)
make frontend
```

See `docs/HARDWARE.md` for the hardware assessment of the current host
and which local models are realistically usable on it.

See `docs/ARCHITECTURE.md` for the pipeline overview.

## Layout

```
ai-devotional-video/
├── frontend/          Next.js + TypeScript UI
├── backend/           FastAPI + Pydantic + SQLAlchemy
├── agent/             Lyrics / audio / scene-planning agent code
├── workers/           Background workers (RQ / Arq)
├── pipeline/          Pipeline steps (audio, transcription, scenes, …)
├── models/            Adapter interfaces + concrete engines
├── storage/           Local file storage (uploads, audio, scenes, final)
├── scripts/           CLI entry points
├── tests/             Unit + e2e tests
├── docs/              Architecture, hardware, licensing docs
└── docker/            Dockerfiles and compose overrides
```

## Licensing

This repository is licensed under Apache-2.0. Individual AI models keep
their own licenses — see `docs/LICENSING.md` and `docs/MODELS.md` for
the list of models actually installed and their commercial-use status.
