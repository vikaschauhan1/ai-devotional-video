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
