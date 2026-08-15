# Architecture

## High-level flow

```
              USER (Web UI / CLI)
                       │
                       ▼
              FastAPI backend  ── SQLite (metadata)
                       │
                       ▼
              Job queue (Redis + RQ / Arq)
                       │
        ┌──────────────┼─────────────────┐
        ▼              ▼                 ▼
   Audio worker   Image worker      Video worker
        │              │                 │
        ▼              ▼                 ▼
  faster-whisper   Image engine      Video engine
   (transcript)    (adapter)         (adapter)
        │              │                 │
        └──────────────┼─────────────────┘
                       ▼
              Lip-sync worker (adapter, optional)
                       │
                       ▼
              FFmpeg compositor  ──►  final MP4
```

Storage lives on local disk under `storage/`. Metadata (projects, jobs,
scenes, file paths) lives in SQLite through SQLAlchemy — schema is
PostgreSQL-compatible so migration later is straightforward.

## Adapter model

Every heavy ML component sits behind an abstract base class in `models/`.
Concrete implementations are swappable through configuration:

```
models/
├── llm/       base.py  ollama.py  openai_compat.py
├── image/     base.py  placeholder.py  openvino_sdxl.py  diffusers_cpu.py
├── video/     base.py  procedural.py  wan.py (stub)  svd.py (stub)
├── lipsync/   base.py  noop.py  wav2lip.py  musetalk.py (stub)
└── tts/       base.py  piper.py  indicf5.py
```

The engine used at runtime is chosen through env-file config
(`.env` / `settings.yaml`) — never hard-coded in workers.

## Why a procedural video engine in the MVP?

This laptop has no CUDA GPU. Wan / SVD / AnimateDiff would either not
run at all or take hours per clip. The `ProceduralVideoEngine` uses
`FFmpeg` `zoompan` + `xfade` to animate generated still images with
cinematic camera moves and crossfades. It is a real, honest technique
(this is how a lot of devotional YouTube content is actually cut) — not
a fake or a mock. Real neural video generation slots in behind the
same `VideoGenerationEngine` interface the moment a GPU appears.

## Directory layout

See the top-level `README.md` and the source tree.
