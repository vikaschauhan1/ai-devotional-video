# Installation

Tested on Ubuntu 26.04 with Python 3.12 and Node 24. Should work on any
recent Linux distro.

## System packages

```bash
sudo apt install -y ffmpeg fonts-noto-sans-devanagari
# Optional: NVIDIA driver + CUDA if you have a discrete GPU
```

## Python toolchain via `uv`

`uv` bootstraps its own Python — no `sudo` needed.

```bash
# Install uv (skip if already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# In the project root
make setup
```

This installs Python 3.12 into `~/.local/share/uv/` and creates
`.venv/` with all Python deps.

## Node.js

```bash
# Recommended: nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
```

Then:

```bash
make frontend-install
```

## Environment

```bash
cp .env.example .env
# edit STORAGE_ROOT, WHISPER_MODEL etc. if needed
```

The defaults (`.env.example`) run the pipeline with:

- `LLM_ENGINE=stub` (offline, deterministic placeholder)
- `IMAGE_ENGINE=placeholder` (Pillow gradient card)
- `VIDEO_ENGINE=procedural` (FFmpeg Ken-Burns)
- `LIPSYNC_ENGINE=noop`
- `TTS_ENGINE=stub`

Everything works out of the box with those. Upgrade one engine at a time.

## Optional: real LLM via Ollama

Only needed for real lyrics analysis / scene planning.

```bash
curl -fsSL https://ollama.com/install.sh | sh          # ~200 MB
ollama pull qwen2.5:3b-instruct                        # ~1.9 GB
```

Start it (systemd unit is created by the installer; if not, run
`ollama serve &` manually).

Then in `.env`:

```
LLM_ENGINE=ollama
LLM_MODEL=qwen2.5:3b-instruct
LLM_BASE_URL=http://127.0.0.1:11434
```

## Optional: faster-whisper transcription

Already installed as part of `make setup`. On first `POST /transcribe`
it downloads the `small` model (~464 MB) into
`~/.cache/huggingface/hub/`. To use `medium` or `large-v3` set
`WHISPER_MODEL` in `.env`.

## Verify

```bash
make test          # pytest
python -m app health
```

If `make test` shows `63 passed, 3 skipped` and `python -m app health`
prints the engine table, you're good.

## Troubleshooting

- **`ffmpeg not found on PATH`** — install ffmpeg via apt.
- **`ollama /api/chat returns 500 "llama-server binary not found"`** —
  incomplete install; run
  `sudo rm -rf /usr/local/lib/ollama && bash /tmp/ollama-install.sh`.
- **Python 3.14 wheels break** — the project uses Python 3.12; make sure
  `.venv/bin/python --version` says 3.12.
- **Devanagari subs render as boxes** — install
  `fonts-noto-sans-devanagari` (`sudo apt install fonts-noto-sans-devanagari`).
