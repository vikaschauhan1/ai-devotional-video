"""Final-video compositor (Phase 16).

Takes the per-scene MP4 clips produced by the video engine and stitches
them into one final video with:

* transitions between clips (crossfade / cut / dip-to-black /
  dip-to-white / whip-pan) driven by the scene plan
* the original audio track from the project, muxed unchanged
* optional burned-in Devanagari-safe subtitles from the transcript
* target aspect ratio and resolution from the project

Uses FFmpeg exclusively. Two-pass approach:

1. Build a filter_complex that runs each clip through the requested
   transition into the next, producing a single silent video stream.
2. Feed that + the audio track through a second ffmpeg pass to mux and
   optionally burn a subtitle track.

Subprocess is always an argument list (never a shell) with a bounded
timeout, per project security rules (Phase 24).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class CompositorError(RuntimeError):
    pass


# Map planner transition names to ffmpeg xfade transition ids.
_XFADE_TRANSITIONS: dict[str, str] = {
    "crossfade":    "fade",
    "cut":          "fade",       # 0-length fade == cut when duration is tiny
    "dip-to-black": "fadeblack",
    "dip-to-white": "fadewhite",
    "whip-pan":     "slideleft",
    # Extras xfade supports; not exposed by the planner but harmless to accept.
    "wipe-left":    "wipeleft",
    "wipe-right":   "wiperight",
    "circleopen":   "circleopen",
    "circleclose":  "circleclose",
}


def _ffmpeg_binary() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise CompositorError("ffmpeg not found on PATH")
    return path


def _ffprobe_binary() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise CompositorError("ffprobe not found on PATH")
    return path


def _clip_duration(path: Path) -> float:
    ffprobe = _ffprobe_binary()
    out = subprocess.run(  # noqa: S603 - argument list
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )
    try:
        return float(out.stdout.strip())
    except ValueError as exc:
        raise CompositorError(f"ffprobe returned non-numeric duration for {path}") from exc


@dataclass(slots=True, frozen=True)
class ClipInput:
    path: Path
    transition: str = "crossfade"  # the transition INTO the NEXT clip


@dataclass(slots=True, frozen=True)
class CompositionResult:
    path: Path
    duration: float
    width: int
    height: int
    fps: int


def _build_concat_filter(
    clips: list[ClipInput],
    durations: list[float],
    *,
    xfade_seconds: float,
    width: int,
    height: int,
    fps: int,
) -> tuple[str, str]:
    """Return (filter_complex_string, final_video_label).

    ``clips[i].transition`` is the transition FROM clip i INTO clip i+1.
    The last clip's transition is ignored (there's nothing after it).
    """
    n = len(clips)
    # Normalise every input first — same fps, same size, same pixel format,
    # RGB conversion so xfade can crossfade safely.
    parts: list[str] = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p[v{i}]"
        )

    if n == 1:
        parts.append("[v0]copy[vout]")
        return ";".join(parts), "[vout]"

    # Chain xfades. offset is cumulative_duration_so_far - xfade_seconds,
    # so the next clip starts fading in xfade_seconds before the previous ends.
    prev_label = "v0"
    offset = 0.0
    for i in range(n - 1):
        offset += durations[i] - xfade_seconds
        if offset < 0:
            # Clip too short for the requested fade; clamp.
            offset = 0.0
        transition = _XFADE_TRANSITIONS.get(
            clips[i].transition.lower(), "fade"
        )
        # For 'cut' we want a very short 60 ms fade — visually indistinguishable
        # from a hard cut but doesn't need a special filter.
        dur = 0.06 if clips[i].transition.lower() == "cut" else xfade_seconds
        out_label = f"vx{i}"
        parts.append(
            f"[{prev_label}][v{i + 1}]xfade=transition={transition}:"
            f"duration={dur:.3f}:offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label

    return ";".join(parts), f"[{prev_label}]"


def _mux_audio_filter(
    audio_input_index: int,
    subtitles_path: Path | None,
    fontsize: int,
) -> tuple[list[str], list[str]]:
    """Return (extra_ffmpeg_args, filter_pieces).

    Called from ``composite()`` after we know the video-only filter graph.
    """
    args: list[str] = []
    filt: list[str] = []
    if subtitles_path is not None:
        # Escape for the subtitles filter path spec.
        subs = str(subtitles_path).replace(":", r"\:").replace("'", r"\'")
        style = (
            f"FontName=Noto Sans Devanagari,FontSize={fontsize},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=60"
        )
        filt.append(f"subtitles='{subs}':force_style='{style}'")
    _ = args
    _ = audio_input_index
    return args, filt


def _write_srt(segments: list[dict], dest: Path) -> None:
    """Write a UTF-8 SRT file that libass can render Devanagari from."""

    def _fmt(t: float) -> str:
        if t < 0:
            t = 0.0
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int(round((t - int(t)) * 1000))
        if ms >= 1000:
            s += 1
            ms -= 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    idx = 1
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 2.0))
        if end <= start:
            end = start + 2.0
        lines.append(str(idx))
        lines.append(f"{_fmt(start)} --> {_fmt(end)}")
        lines.append(text)
        lines.append("")
        idx += 1
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def composite(
    *,
    clips: list[ClipInput],
    audio_path: Path | None,
    output_path: Path,
    width: int,
    height: int,
    fps: int = 24,
    xfade_seconds: float = 0.6,
    subtitle_segments: list[dict] | None = None,
    subtitle_font_size: int = 32,
    subtitle_font_name: str = "Noto Sans Devanagari",
    subtitle_alignment: int = 2,  # ASS alignment: 2=bottom-centre, 8=top-centre
    subtitle_margin_v: int = 60,
    subtitle_outline: int = 2,
    subtitle_shadow: int = 1,
    timeout_seconds: float = 600.0,
) -> CompositionResult:
    """Concatenate ``clips`` with transitions and mux ``audio_path``.

    Returns the composition result on success, raises ``CompositorError``
    on any FFmpeg or ffprobe failure.
    """
    if not clips:
        raise CompositorError("no clips to composite")

    ffmpeg = _ffmpeg_binary()
    durations = [_clip_duration(c.path) for c in clips]

    # Optional subtitles file — written next to the output.
    subs_path: Path | None = None
    if subtitle_segments:
        subs_path = output_path.with_suffix(".srt")
        _write_srt(subtitle_segments, subs_path)

    video_filter, video_label = _build_concat_filter(
        clips,
        durations,
        xfade_seconds=xfade_seconds,
        width=width,
        height=height,
        fps=fps,
    )

    # Add subtitles as a chained filter on the concatenated video label.
    if subs_path is not None:
        subs_arg = str(subs_path).replace(":", r"\:")
        # Sanitise font name so it can't break out of the ASS style string.
        safe_font = subtitle_font_name.replace(",", " ").replace("'", "")
        style = (
            f"FontName={safe_font},FontSize={subtitle_font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
            f"Outline={subtitle_outline},Shadow={subtitle_shadow},"
            f"Alignment={subtitle_alignment},MarginV={subtitle_margin_v}"
        )
        # Wrap label with subtitles filter; xfade left us at ``video_label``
        # which is like "[vx3]". Strip brackets to reuse it as filter input.
        raw = video_label.strip("[]")
        video_filter = (
            video_filter
            + f";[{raw}]subtitles='{subs_arg}':force_style='{style}'[vout]"
        )
        video_label = "[vout]"

    # Build ffmpeg command.
    cmd: list[str] = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    for clip in clips:
        cmd += ["-i", str(clip.path)]
    audio_input_index: int | None = None
    if audio_path is not None:
        audio_input_index = len(clips)
        cmd += ["-i", str(audio_path)]

    cmd += ["-filter_complex", video_filter, "-map", video_label]
    if audio_input_index is not None:
        cmd += ["-map", f"{audio_input_index}:a:0?", "-c:a", "aac", "-b:a", "192k"]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_path),
    ]

    log.info(
        "compositing %d clips → %s (audio=%s, subs=%s)",
        len(clips),
        output_path.name,
        "yes" if audio_path else "no",
        "yes" if subs_path else "no",
    )
    try:
        subprocess.run(  # noqa: S603 - argument list, no shell
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        raise CompositorError(
            f"ffmpeg composite failed ({exc.returncode}): {exc.stderr.strip()[:800]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise CompositorError(
            f"ffmpeg composite timed out after {timeout_seconds:.0f}s"
        ) from exc

    total_duration = sum(durations) - max(0, len(clips) - 1) * xfade_seconds
    return CompositionResult(
        path=output_path,
        duration=max(total_duration, 0.0),
        width=width,
        height=height,
        fps=fps,
    )
