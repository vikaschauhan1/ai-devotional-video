# Troubleshooting

## `pytest` fails with `ffmpeg not found on PATH`

Install ffmpeg: `sudo apt install ffmpeg`. The video / render / audio
tests all require the real binary.

## `POST /transcribe` hangs on the first call

faster-whisper downloads the `small` model (~464 MB) the first time.
Subsequent calls reuse the process cache. To avoid the wait, prewarm:

```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
```

## `POST /analyze` returns 500 `ollama HTTP 500: llama-server binary not found`

Ollama install is corrupted. Repair:

```bash
pkill -f 'ollama serve' 2>/dev/null; sleep 1
sudo rm -rf /usr/local/lib/ollama
bash /tmp/ollama-install.sh
nohup ollama serve > /tmp/ollama.log 2>&1 &
```

## Devanagari subtitles render as boxes

Install the font:

```bash
sudo apt install fonts-noto-sans-devanagari
```

libass looks up fonts by name at compose time. No cache flush needed.

## `POST /generate-async` completes but `Job.result.final.url` is empty

The final MP4 landed outside `STORAGE_ROOT` (misconfigured `.env`). Check:

```bash
python -c "from backend.app.core.settings import get_settings; print(get_settings().storage_root)"
```

Point `STORAGE_ROOT` at the same directory the compositor writes to,
restart uvicorn. The `_storage_url` helper deliberately returns empty
for paths outside STORAGE_ROOT — it will never leak `/etc/passwd`.

## `POST /generate` slow but never fails

Real ffmpeg time. Rough single-run budget on i7-1185G7 CPU with
6 scenes @ 4s each, 720x1280:

| Stage | Approx duration |
|---|---|
| transcribe (whisper small) | 2-8 s per 30 s audio |
| analyze (ollama qwen 3B) | 3-10 s |
| plan-scenes | 5-15 s |
| generate-images (placeholder) | ~2 s total |
| generate-videos (Ken-Burns) | ~1 s per clip |
| render | 5-15 s |

Total: 30-90 s for a typical 30-60 s song. Use `POST /generate-async`
and poll `GET /api/jobs/{id}` for live progress.

## Whisper detects Sanskrit as Hindi

Expected. Whisper doesn't support Sanskrit natively; it labels
Devanagari-script Sanskrit as `hi` with degraded per-word accuracy.
Scene planning handles this fine because it uses lyrics text directly.

## `npm run build` fails with `TS18047: possibly 'null'`

TypeScript's control-flow narrowing doesn't cross async closures.
Capture the value in a `const` at the top of the async function:

```ts
if (!selectedProject) return;
const projectId = selectedProject.id;
// use projectId inside async callbacks
```

## `ruff` complains about `Depends(...)` in default arguments (B008)

Already whitelisted in `pyproject.toml` under
`[tool.ruff.lint.flake8-bugbear] extend-immutable-calls`. If a new
FastAPI helper trips it, add it to that list — do not sprinkle `# noqa`
in routes.

## Pylance / VS Code save-action reverts my edits

Known: the editor buffer occasionally reverts `StrEnum` → `(str, Enum)`
or `timezone.utc` → `UTC`. If a `replace_string_in_file` edit refuses to
stick, patch the file directly on disk with a Python script, then use
`Ctrl+Shift+P → Revert File` in VS Code to reload.

## `/api/jobs/{id}` says COMPLETED but frontend won't stop polling

You're on the sync `POST /generate` codepath, which never creates a Job.
Switch to `POST /generate-async` — the frontend already does this in
`onGenerate`.

## Preview `<video>` shows the URL but doesn't play

CORS: hitting the backend from a non-3000 origin. Add your dev origin to
the `CORSMiddleware` allow-list in `backend/app/main.py`.
