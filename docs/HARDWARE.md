# Hardware Inspection Report

Captured: 2026-08-16 on host `RSILINUX-13934`.

## Summary

| Item | Value |
|---|---|
| OS | Ubuntu 26.04 LTS "Resolute Raccoon" (kernel 7.0.0-29) |
| CPU | Intel Core i7-1185G7 (Tiger Lake, 4 cores / 8 threads, AVX-512 + VNNI) |
| RAM | 29 GiB total (7.4 GiB available at inspection; 7.5 / 8 GiB swap already used) |
| GPU | Intel Iris Xe integrated (`Corporation TigerLake-LP GT2`) |
| VRAM | Shared with system RAM (no dedicated VRAM) |
| CUDA | **Not available** — no NVIDIA GPU, `nvidia-smi` and `nvcc` absent |
| NVIDIA driver | Not installed |
| Python | 3.14.4 at `/usr/bin/python3` (see caveat below) |
| Node.js | v24.14.0 at `~/.nvm/versions/node/v24.14.0/bin/node`, npm 11.9.0 |
| Docker | 29.1.3, Compose v2.40.3 |
| FFmpeg | 8.0.1 (full build with libx264/x265/svtav1/aom/ass/vpl/OpenCL/Vulkan) |
| Disk (root) | 468 GB total, 227 GB free (48 % used) |

## Caveats

1. **No CUDA GPU.** All CUDA-only models are out of scope for local execution
   on this machine. This includes MuseTalk, Wan 2.x video-generation, and any
   diffusion model that requires ≥ 8 GB VRAM at practical speed.
2. **Memory pressure.** At inspection ~22 GiB of the 29 GiB RAM was already
   in use and swap was 94 % full. Heavy local inference will thrash. Free memory
   before running the pipeline, or accept swap-backed inference.
3. **Python 3.14 is too new** for the current ML wheel ecosystem
   (PyTorch, faster-whisper/CTranslate2, diffusers). The project pins
   **Python 3.12** via `uv` in a project-local `.venv` — no root or apt
   changes needed.
4. **Ubuntu 26.04 is very new** — a few apt packages (Intel OpenVINO runtime,
   CUDA toolchains) are not yet packaged. We install those through language
   package managers instead of apt.

## Realistic local-model plan for this host

| Pipeline stage | Chosen local model | Runs here? | Notes |
|---|---|---|---|
| Lyrics ASR | `faster-whisper` (`small` or `medium`, int8 CPU) | Yes, fast | `large-v3` works but ~5× slower |
| LLM (scene planning) | Ollama running `qwen2.5:3b-instruct` (Q4_K_M) | Yes | ~15 tok/s CPU; 7B is usable but slow |
| Image generation | Placeholder adapter first, then SDXL-Turbo via OpenVINO on Iris Xe (or SD 1.5 diffusers CPU) | Yes, slow | ~10-20 s/image on OpenVINO, ~60 s on CPU |
| Video generation (true T2V) | **Not viable locally** on this host | No | MVP uses `ProceduralVideoEngine` (stills + FFmpeg Ken-Burns/zoompan + crossfade). Real Wan/SVD adapter is left as a stub for future GPU. |
| Lip sync | Wav2Lip CPU (adapter present, off by default) | Slow but works | MuseTalk adapter left as CUDA stub |
| TTS | Piper (CPU, fast) later, IndicF5 later | Yes | Not required for MVP |
| Composition | System FFmpeg 8.0.1 with libass | Yes | Devanagari subtitles via Noto Sans Devanagari |

All choices are open source and run locally with no paid APIs.

## Model licenses (recorded per Phase 23)

| Model | License | Commercial use |
|---|---|---|
| Whisper / faster-whisper | MIT | Yes |
| Qwen 2.5 | Apache-2.0 | Yes |
| SDXL-Turbo | Stability Community License | Restricted |
| SD 1.5 | CreativeML-OpenRAIL-M | Case-by-case |
| Wan 2.x | Apache-2.0 | Yes (when we can run it) |
| MuseTalk | Non-commercial research | No |
| Wav2Lip weights | Non-commercial research | No |
| Piper voices | Various (per voice) | Per voice |
| IndicF5 | Check per release | Case-by-case |

Refer to `docs/LICENSING.md` for the authoritative list of models actually
installed in this workspace.
