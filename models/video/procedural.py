"""Procedural video-generation engine.

Turns a still image into a short MP4 clip using FFmpeg's ``zoompan``
Ken-Burns filter. This is the CPU-only workhorse the MVP ships with;
neural T2V / I2V engines (Wan, SVD, AnimateDiff) drop in behind the
same ``VideoGenerationEngine`` interface as soon as a CUDA GPU is
available.

The chosen camera move is driven by the ``camera_hint`` field on the
request. Common devotional-video language maps to concrete zoompan /
xfade expressions:

* "slow push-in"        → z increases from 1.0 to 1.10, center held
* "slow pull-out"       → z from 1.15 to 1.0
* "pan-left"/"pan-right"→ x drifts across the crop window
* "orbit"/"dolly"       → mild diagonal drift with slight zoom
* fallback              → gentle push-in

Every subprocess call uses an argument list (no shell), a bounded
timeout, and rejects failed invocations with a domain-specific error.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from models.video.base import (
    VideoGenerationEngine,
    VideoGenerationRequest,
    VideoGenerationResult,
)

log = logging.getLogger(__name__)


class ProceduralVideoError(RuntimeError):
    pass


def _ffmpeg_binary() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise ProceduralVideoError(
            "ffmpeg not found on PATH; install ffmpeg to use the procedural engine."
        )
    return path


def _camera_expression(
    camera_hint: str,
    total_frames: int,
    width: int,
    height: int,
) -> tuple[str, str, str]:
    """Return (zoom_expr, x_expr, y_expr) for the given camera language.

    zoompan operates on an oversampled internal canvas. Standard pattern:
    z ramps between 1.0 and ~1.15 over ``total_frames`` frames. x/y move
    the crop centre. Expressions use ``on`` (current output frame index)
    so timing is stable regardless of source resolution.
    """
    hint = (camera_hint or "").lower()
    n = max(total_frames - 1, 1)  # 0-indexed frame counter

    # Sensible defaults: slow push-in.
    if not hint or "push" in hint and "out" not in hint:
        zoom = f"1.0 + 0.10*on/{n}"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
        return zoom, x, y

    if "pull" in hint or "out" in hint:
        zoom = f"1.15 - 0.15*on/{n}"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
        return zoom, x, y

    if "left" in hint:
        # Slight zoom + horizontal drift to the left.
        zoom = "1.10"
        x = f"(iw-iw/zoom) * (1 - on/{n})"
        y = "ih/2-(ih/zoom/2)"
        return zoom, x, y

    if "right" in hint:
        zoom = "1.10"
        x = f"(iw-iw/zoom) * on/{n}"
        y = "ih/2-(ih/zoom/2)"
        return zoom, x, y

    if "up" in hint or "tilt-up" in hint:
        zoom = "1.10"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom) * (1 - on/{n})"
        return zoom, x, y

    if "down" in hint or "tilt-down" in hint:
        zoom = "1.10"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom) * on/{n}"
        return zoom, x, y

    if "orbit" in hint or "dolly" in hint or "spin" in hint:
        # Mild diagonal drift + subtle zoom.
        zoom = f"1.0 + 0.08*on/{n}"
        x = f"(iw-iw/zoom) * (0.4 + 0.2*on/{n})"
        y = f"(ih-ih/zoom) * (0.4 + 0.2*on/{n})"
        return zoom, x, y

    # Fallback: default push-in.
    zoom = f"1.0 + 0.10*on/{n}"
    x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    return zoom, x, y


class ProceduralVideoEngine(VideoGenerationEngine):
    """FFmpeg-based Ken-Burns video engine — the MVP fallback.

    Requires ``image_path`` on the request (this engine cannot invent
    imagery from a text prompt alone). Duration and fps come from the
    request; camera language from ``camera_hint``.
    """

    name = "procedural"

    def __init__(self, *, storage_root: Path, timeout_seconds: float = 120.0) -> None:
        self.storage_root = Path(storage_root)
        self.timeout_seconds = timeout_seconds

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        if request.image_path is None:
            raise ProceduralVideoError(
                "procedural engine requires image_path; text-only generation is "
                "reserved for the neural adapter"
            )
        src = Path(request.image_path)
        if not src.is_file():
            raise ProceduralVideoError(f"image not found: {src}")

        duration = max(0.5, float(request.duration))
        fps = int(request.fps or 24)
        width = int(request.width or 720)
        height = int(request.height or 1280)
        total_frames = int(round(duration * fps))

        zoom_expr, x_expr, y_expr = _camera_expression(
            request.camera_hint or "",
            total_frames,
            width,
            height,
        )
        # zoompan needs an integer number of output frames via ``d=``.
        # It also produces frames at its own fps; we tell it explicitly.
        vf = (
            # Oversample to hide zoompan's chunky integer stepping.
            f"scale=iw*4:ih*4,"
            f"zoompan="
            f"z='{zoom_expr}':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d={total_frames}:"
            f"s={width}x{height}:"
            f"fps={fps},"
            # Ensure yuv420p for broad compatibility.
            "format=yuv420p"
        )

        # Output alongside the source image, under scenes/<project_id>/videos.
        project_id = str(request.extras.get("project_id") or "misc")
        scene_id = str(request.extras.get("scene_id") or src.stem)
        dest_dir = (
            self.storage_root / "generated_videos" / project_id
        ).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{scene_id}-{int(duration * 1000):06d}ms.mp4"

        ffmpeg = _ffmpeg_binary()
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(src),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-r",
            str(fps),
            str(dest),
        ]
        log.info(
            "procedural video: scene=%s duration=%.2fs fps=%d camera=%r size=%dx%d",
            scene_id,
            duration,
            fps,
            request.camera_hint,
            width,
            height,
        )
        try:
            subprocess.run(  # noqa: S603 - argument list, no shell
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            dest.unlink(missing_ok=True)
            raise ProceduralVideoError(
                f"ffmpeg failed ({exc.returncode}): {exc.stderr.strip()[:500]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            dest.unlink(missing_ok=True)
            raise ProceduralVideoError(
                f"ffmpeg timed out after {self.timeout_seconds:.0f}s"
            ) from exc

        return VideoGenerationResult(
            path=dest,
            duration=duration,
            fps=fps,
            engine=self.name,
            metadata={
                "width": width,
                "height": height,
                "camera_hint": request.camera_hint,
                "source_image": str(src),
            },
        )
