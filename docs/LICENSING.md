# Licensing

Two layers.

## Repository code

Apache-2.0 for everything in this repository.

## Third-party AI models

Each model keeps its upstream license. The list below covers only models
the code paths actually use. Models mentioned in `.env.example` under
"future" adapters are not included until they are wired up.

| Model | Installed? | License | Commercial use | Notes |
|---|---|---|---|---|
| `Systran/faster-whisper-small` (int8) | Yes | MIT (© OpenAI, redistributed by Systran) | Yes | Auto-downloaded to `~/.cache/huggingface/` on first `/transcribe`. |
| `qwen2.5:3b-instruct` (Ollama Q4_K_M) | Optional | Apache-2.0 (© Alibaba) | Yes | Pulled with `ollama pull`. |
| Placeholder image engine | Built-in | Apache-2.0 | Yes | Pillow-based, no third-party weights. |
| Procedural video engine | Built-in | Apache-2.0 | Yes | FFmpeg only. |

## Models referenced in adapters but NOT installed

These names appear in `.env.example` or docs as future adapter
implementations. Check the license before enabling them.

| Model | Upstream license | Commercial use |
|---|---|---|
| SDXL-Turbo | Stability Community License (non-commercial default; commercial license available) | Restricted |
| Stable Diffusion 1.5 | CreativeML-OpenRAIL-M | Case-by-case |
| Wan 2.x | Apache-2.0 | Yes when installed |
| SVD (Stable Video Diffusion) | Stability Community License | Restricted |
| AnimateDiff | Apache-2.0 | Yes |
| MuseTalk | Non-commercial research license | **No** |
| Wav2Lip weights | Non-commercial research license | **No** |
| Piper voices | Varies per voice; most are permissive | Per voice |
| IndicF5 | Check per release | Case-by-case |

## Fonts

- `Noto Sans Devanagari` — SIL Open Font License 1.1 — commercial-OK.
  Used by libass for burned-in subtitles.

## Frontend third-party

The `frontend/` directory is a standard `create-next-app` scaffold.
Direct dependencies: Next.js 16, React 19, Tailwind CSS 4, TypeScript.
All MIT / Apache-2.0.

## What this means in practice

- Fully commercial-OK setup: `LLM_ENGINE=ollama` (qwen2.5), placeholder
  image engine, procedural video engine, `LIPSYNC_ENGINE=noop`,
  `TTS_ENGINE=stub`. This is what the MVP ships with.
- Enabling MuseTalk or the default Wav2Lip weights makes the output
  non-commercial. Do not ship those in a paid product.
- Enabling SDXL / SVD requires a Stability commercial license for
  paid distribution.
