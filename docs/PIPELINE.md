# Pipeline

End-to-end flow when `POST /projects/{id}/generate` (or `-async`) is
called on a project with audio + lyrics uploaded.

```
Upload audio  ─→  ffprobe metadata (services/audio.py)
Upload lyrics ─→  Project.lyrics
                    │
Optional            │  ── 1 ──▶ pipeline/transcription.py
Transcribe          ▼           faster-whisper small int8
                                        │
                                        ▼
                    │  ── 2 ──▶ services/lyrics.py + agent/prompts.py
Analyze lyrics      │           LLMEngine.generate_json → LyricsAnalysis
                    │                   │
                    │                   ▼
                    │  ── 3 ──▶ services/scenes.py + agent/scenes.py
Plan scenes         │           LLM ScenePlan → Scene DB rows
                    │                   │
                    │                   ▼
                    │  ── 4 ──▶ services/images.py
Generate images     │           ImageGenerationEngine (placeholder / …)
                    │                   │
                    │                   ▼
                    │  ── 5 ──▶ services/videos.py
Generate clips      │           VideoGenerationEngine (procedural / …)
                    │                   │
                    │                   ▼
                    │  ── 6 ──▶ services/render.py + pipeline/compositor.py
Compose final       │           FFmpeg xfade + audio mux + optional subs
                    │                   │
                    ▼                   ▼
                 Job.status         MediaAsset kind=FINAL
                COMPLETED           storage/final/<pid>/final-<uuid>.mp4
```

## Adapter model

Every heavy stage sits behind a Python `ABC` in `models/<kind>/base.py`.
Concrete implementations are selected at runtime by the corresponding
`.env` variable:

| Adapter | Env var | Implementations available today |
|---|---|---|
| LLM | `LLM_ENGINE` | `ollama` (real), `stub` (offline placeholder) |
| Image | `IMAGE_ENGINE` | `placeholder` (real Pillow, produces PNGs) |
| Video | `VIDEO_ENGINE` | `procedural` (real FFmpeg zoompan) |
| Lipsync | `LIPSYNC_ENGINE` | (interface only, not yet implemented) |
| TTS | `TTS_ENGINE` | (interface only) |

The placeholder image engine and procedural video engine are **real**,
not mocks. They produce actual media files that flow through the rest
of the pipeline so the whole system works on any laptop.

Neural engines (SDXL, Wan, MuseTalk, Wav2Lip) drop in behind the same
interfaces when GPU + weights become available.

## Job states

`Job.status` is persisted in SQLite as one of:

```
QUEUED → ANALYZING → PLANNING → GENERATING_IMAGES
       → GENERATING_VIDEO → COMPOSITING → COMPLETED
                                        └→ FAILED / CANCELLED
```

`GET /api/jobs/{job_id}` returns the row so a client can poll or an
LSP/WebSocket adapter can be layered on later.

## Storage layout

```
storage/
├── uploads/                 (raw uploads; unused post-validation)
├── audio/<pid>/             validated audio, safe UUID filename
├── transcripts/<pid>/       whisper JSON output
├── references/<pid>/        user-uploaded reference images
├── scenes/<pid>/            lyrics-analysis-*.json, scene-plan-*.json
├── generated_images/<pid>/  per-scene PNGs
├── generated_videos/<pid>/  per-scene MP4 clips
├── lipsync/<pid>/           (reserved for Phase 15)
└── final/<pid>/             final composite MP4 + SRT
```

All files under `storage/` are served at `/storage/...` by the FastAPI
static mount for direct browser playback.

## Determinism

- Placeholder image engine seeds from `SHA-256(prompt)[:4]` — same
  prompt → same PNG (unless explicit `seed=` overrides).
- FFmpeg Ken-Burns is deterministic per (image, camera, duration).
- LLM calls are non-deterministic; the stub engine is fully deterministic.

## Failure semantics

- Precheck failures (`no audio`, `no lyrics`) surface as HTTP 409 with
  `detail = {"stage": "precheck", "message": "..."}`.
- Any downstream stage failure short-circuits the pipeline and surfaces
  as HTTP 500 with `detail = {"stage": "<name>", "message": "..."}`.
- Whisper transcription is best-effort: a failure is downgraded to
  `skipped` in the progress log and the flow continues.
