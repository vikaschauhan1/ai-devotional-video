"""Wav2Lip lip-sync adapter (Phase 15).

Wav2Lip is a research model with a **non-commercial** license and a
messy install (specific PyTorch version, face-detection weights).
Rather than vendoring 340 MB of weights and pinning ancient PyTorch,
this adapter shells out to an existing Wav2Lip checkout you point at
with ``WAV2LIP_ROOT``.

Setup (once per host, only if you opt in):

    git clone https://github.com/Rudrabha/Wav2Lip.git ~/wav2lip
    cd ~/wav2lip
    # follow the repo's README to download the weights into checkpoints/
    export WAV2LIP_ROOT=~/wav2lip
    # set LIPSYNC_ENGINE=wav2lip in .env

Then any scene whose video_path is fed to this engine gets its lips
re-synced to the project's audio track. On CPU, expect ~15-30x real time
(a 6-second scene ~2-3 minutes). Use only for hero shots.

License caveat: enabling this makes any resulting distribution
non-commercial. See docs/LICENSING.md.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from models.lipsync.base import LipSyncEngine, LipSyncRequest, LipSyncResult

log = logging.getLogger(__name__)


class Wav2LipError(RuntimeError):
    pass


def _wav2lip_root() -> Path:
    override = os.environ.get("WAV2LIP_ROOT")
    if not override:
        raise Wav2LipError(
            "WAV2LIP_ROOT not set. Clone Rudrabha/Wav2Lip and point "
            "WAV2LIP_ROOT at it."
        )
    root = Path(override).expanduser()
    if not (root / "inference.py").is_file():
        raise Wav2LipError(
            f"{root}/inference.py not found — is WAV2LIP_ROOT correct?"
        )
    return root


def _python_binary() -> str:
    override = os.environ.get("WAV2LIP_PYTHON")
    if override:
        return override
    # Fall back to the interpreter that started us. This is usually wrong
    # for Wav2Lip (it needs old torch), so users typically set
    # WAV2LIP_PYTHON to a dedicated venv's python.
    return shutil.which("python") or "python"


class Wav2LipEngine(LipSyncEngine):
    name = "wav2lip"

    def __init__(self, *, storage_root: Path, timeout_seconds: float = 600.0) -> None:
        self.storage_root = Path(storage_root)
        self.timeout_seconds = timeout_seconds

    async def synchronize(self, request: LipSyncRequest) -> LipSyncResult:
        root = _wav2lip_root()
        py = _python_binary()

        checkpoint = os.environ.get(
            "WAV2LIP_CHECKPOINT", "checkpoints/wav2lip.pth"
        )
        checkpoint_path = (root / checkpoint).resolve()
        if not checkpoint_path.is_file():
            raise Wav2LipError(
                f"checkpoint {checkpoint_path} missing — download per "
                f"the Wav2Lip repo README."
            )

        # We assume request.video_path is a project id we can bucket under.
        project_id = str(request.extras.get("project_id") or "misc")
        dest_dir = (self.storage_root / "lipsync" / project_id).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"lipsync-{uuid.uuid4().hex}.mp4"

        cmd = [
            py,
            "inference.py",
            "--checkpoint_path",
            str(checkpoint_path),
            "--face",
            str(Path(request.video_path).resolve()),
            "--audio",
            str(Path(request.audio_path).resolve()),
            "--outfile",
            str(dest),
        ]
        log.info("wav2lip: %s", " ".join(cmd))
        try:
            subprocess.run(  # noqa: S603 - arg list
                cmd,
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            dest.unlink(missing_ok=True)
            raise Wav2LipError(
                f"wav2lip failed ({exc.returncode}): {exc.stderr.strip()[:800]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            dest.unlink(missing_ok=True)
            raise Wav2LipError(
                f"wav2lip timed out after {self.timeout_seconds:.0f}s"
            ) from exc

        if not dest.is_file():
            raise Wav2LipError("wav2lip produced no output file")

        return LipSyncResult(
            path=dest,
            engine=self.name,
            metadata={
                "checkpoint": str(checkpoint_path),
                "input_video": str(request.video_path),
                "input_audio": str(request.audio_path),
            },
        )
