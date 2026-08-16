# Installed AI models

The authoritative list of AI model weights present on this workspace's
local machine. Update this file whenever a new model is downloaded or
removed.

## `Systran/faster-whisper-small` (int8)

| Field | Value |
|---|---|
| Purpose | Speech-to-text (Phase 8 transcription) |
| Repository | https://huggingface.co/Systran/faster-whisper-small |
| Format | CTranslate2 (int8 quantised) |
| Local cache | `~/.cache/huggingface/hub/models--Systran--faster-whisper-small` |
| Disk size | 464 MB |
| RAM at inference | ~500 MB |
| CPU speed | ~real-time on Intel i7-1185G7 |
| License | Original Whisper weights: **MIT** (© OpenAI). The Systran redistribution keeps the MIT license. |
| Commercial use | Yes |
| Hardware notes | CPU int8 is the default here. On CUDA, prefer `float16` and set `WHISPER_COMPUTE_TYPE=float16` in `.env`. |

Configuration knobs (all in `.env`):

- `WHISPER_MODEL` — `tiny` / `base` / `small` / `medium` / `large-v3`
- `WHISPER_COMPUTE_TYPE` — `int8` / `int8_float16` / `float16` / `float32`
- `WHISPER_DEVICE` — `cpu` / `cuda` / `auto`

`small` gives good Hindi results at CPU-affordable cost. `medium` is
noticeably better but ~2 GB and ~3× slower. Sanskrit is not natively
supported by Whisper and is typically classified as Hindi with degraded
per-word accuracy; downstream (scene planner) treats this correctly.

## `qwen2.5:3b-instruct` (Q4_K_M via Ollama)

| Field | Value |
|---|---|
| Purpose | Lyrics / song-structure analysis (Phase 9). Later reused for scene planning (Phase 10). |
| Repository | https://ollama.com/library/qwen2.5 (upstream: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) |
| Format | GGUF Q4_K_M quantisation, served via Ollama |
| Local cache | `~/.ollama/models/` (or `/usr/share/ollama/.ollama/models/` if run as the system user) |
| Disk size | ~1.9 GB |
| RAM at inference | ~2.5 GB |
| CPU speed | ~15 tokens/s on Intel i7-1185G7 |
| License | Apache-2.0 |
| Commercial use | Yes |
| Hardware notes | Runs anywhere Ollama runs. For CUDA machines Ollama picks up the GPU automatically. |

Enable in `.env`:

```
LLM_ENGINE=ollama
LLM_MODEL=qwen2.5:3b-instruct
LLM_BASE_URL=http://127.0.0.1:11434
```

The `stub` engine (`LLM_ENGINE=stub`) is a deterministic offline
fallback: it returns a minimal valid `LyricsAnalysis` object so the
pipeline can run end-to-end without a network call. It is used by the
fast test suite and is safe to leave as the default in `.env.example`.
