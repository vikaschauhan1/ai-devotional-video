"""Command-line interface (Phase 18).

Wraps the existing service functions so the pipeline can be driven
without the HTTP layer. Uses the same DB, storage, and adapters as the
FastAPI app.

Examples
--------
    python -m app health
    python -m app new-project --name "Shiva bhajan" --deity Shiva --style shiva-himalayan
    python -m app upload-audio <project-id> bhajan.mp3
    python -m app set-lyrics <project-id> - < lyrics.txt
    python -m app generate <project-id> --burn-subtitles --scenes 6
    python -m app render-status <project-id>
    python -m app list-projects
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from backend.app.core.settings import get_settings
from backend.app.db.models import AssetKind, MediaAsset, Project
from backend.app.db.session import SessionLocal, init_db
from backend.app.services.audio import save_upload
from backend.app.services.generate import GenerationError, generate_project_end_to_end
from backend.app.services.lyrics import save_lyrics
from models.image import get_image_engine
from models.llm import get_llm_engine
from models.video import get_video_engine
from pipeline.audio_analysis import probe

console = Console()
app = typer.Typer(
    add_completion=False,
    help="AI Devotional Video Studio — command-line pipeline runner.",
)


def _session():
    init_db()
    return SessionLocal()


def _fail(msg: str, code: int = 1) -> None:
    console.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code)


class _FakeUpload:
    """Minimal UploadFile shim: save_upload only needs filename, content_type, read/close."""

    def __init__(self, path: Path, content_type: str) -> None:
        self.filename = path.name
        self.content_type = content_type
        self._fh = path.open("rb")

    async def read(self, n: int) -> bytes:
        return self._fh.read(n)

    async def close(self) -> None:
        self._fh.close()


def _guess_content_type(ext: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
    }.get(ext.lower(), "application/octet-stream")


@app.command()
def health() -> None:
    """Print backend health / engine names / storage root."""
    s = get_settings()
    console.print(
        f"[bold]storage_root[/bold]  {s.storage_root}\n"
        f"[bold]database_url[/bold]  {s.database_url}\n"
        f"[bold]llm[/bold]           {s.llm_engine} ({s.llm_model})\n"
        f"[bold]image[/bold]         {s.image_engine}\n"
        f"[bold]video[/bold]         {s.video_engine}\n"
        f"[bold]lipsync[/bold]       {s.lipsync_engine}\n"
        f"[bold]asr[/bold]           faster-whisper:{s.whisper_model} "
        f"({s.whisper_compute_type}/{s.whisper_device})"
    )


@app.command("list-projects")
def list_projects() -> None:
    with _session() as db:
        rows = db.query(Project).order_by(Project.created_at.desc()).all()
    if not rows:
        console.print("[dim]no projects yet[/dim]")
        return
    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("id", overflow="fold")
    tbl.add_column("name")
    tbl.add_column("deity")
    tbl.add_column("aspect")
    tbl.add_column("style")
    for p in rows:
        tbl.add_row(p.id, p.name, p.deity or "", p.aspect_ratio, p.style or "")
    console.print(tbl)


@app.command("new-project")
def new_project(
    name: str = typer.Option(..., "--name", "-n"),
    deity: str | None = typer.Option(None, "--deity", "-d"),
    style: str | None = typer.Option(None, "--style", "-s"),
    aspect_ratio: str = typer.Option("9:16", "--aspect-ratio", "-a"),
    resolution: str = typer.Option("auto", "--resolution", "-r"),
) -> None:
    with _session() as db:
        p = Project(
            name=name,
            deity=deity,
            style=style,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        console.print(p.id)


@app.command("upload-audio")
def upload_audio(project_id: str, audio_path: Path) -> None:
    """Upload an audio file (MP3/WAV/M4A/FLAC) into a project."""
    if not audio_path.is_file():
        _fail(f"file not found: {audio_path}")

    async def run() -> None:
        settings = get_settings()
        with _session() as db:
            project = db.get(Project, project_id)
            if project is None:
                _fail(f"project not found: {project_id}")
                return
            upload = _FakeUpload(
                audio_path, _guess_content_type(audio_path.suffix)
            )
            stored = await save_upload(
                settings=settings, project_id=project.id, upload=upload
            )
            meta = probe(stored.path)
            asset = MediaAsset(
                project_id=project.id,
                kind=AssetKind.AUDIO,
                path=str(stored.path),
                original_filename=stored.original_filename,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                meta=meta.to_dict(),
            )
            db.add(asset)
            db.commit()
            console.print(
                f"[green]OK[/green] uploaded {audio_path.name} "
                f"({meta.duration:.1f}s {meta.codec})"
            )

    asyncio.run(run())


@app.command("set-lyrics")
def set_lyrics(
    project_id: str,
    text: str = typer.Argument(
        ...,
        help="Lyrics text, or '-' to read from stdin.",
    ),
) -> None:
    if text == "-":
        text = sys.stdin.read()
    with _session() as db:
        project = db.get(Project, project_id)
        if project is None:
            _fail(f"project not found: {project_id}")
            return
        save_lyrics(db=db, project=project, text=text)
        console.print(f"[green]OK[/green] {len(text.strip())} chars saved")


@app.command()
def generate(
    project_id: str,
    scenes: int = typer.Option(6, "--scenes", "-n"),
    style_preset: str | None = typer.Option(None, "--style"),
    burn_subtitles: bool = typer.Option(False, "--burn-subtitles"),
    run_transcription: bool = typer.Option(True, "--transcribe/--no-transcribe"),
    fps: int = typer.Option(24, "--fps"),
    xfade: float = typer.Option(0.6, "--xfade"),
) -> None:
    """Run the full pipeline end-to-end. Blocking."""

    async def run() -> None:
        settings = get_settings()
        with _session() as db:
            project = db.get(Project, project_id)
            if project is None:
                _fail(f"project not found: {project_id}")
                return

            async def _on_step(step) -> None:  # noqa: ANN001 - imported dataclass
                icon = {
                    "ok": "[green]✓[/green]",
                    "skipped": "[dim]—[/dim]",
                    "failed": "[red]✗[/red]",
                }.get(step.status, "•")
                detail = f" [dim]{step.detail}[/dim]" if step.detail else ""
                console.print(f"  {icon} {step.stage}{detail}")

            try:
                outcome = await generate_project_end_to_end(
                    db=db,
                    settings=settings,
                    project=project,
                    llm_engine=get_llm_engine(),
                    image_engine=get_image_engine(),
                    video_engine=get_video_engine(),
                    run_transcription=run_transcription,
                    target_scene_count=scenes,
                    style_preset_override=style_preset,
                    burn_subtitles=burn_subtitles,
                    fps=fps,
                    xfade_seconds=xfade,
                    progress_callback=_on_step,
                )
            except GenerationError as exc:
                _fail(f"{exc.stage}: {exc.reason}")
                return
            console.print(
                f"\n[bold green]DONE[/bold green] "
                f"{outcome.duration:.1f}s @ {outcome.width}x{outcome.height}\n"
                f"  {outcome.final_path}"
            )

    asyncio.run(run())


@app.command("render-status")
def render_status(project_id: str) -> None:
    with _session() as db:
        latest = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.project_id == project_id,
                MediaAsset.kind == AssetKind.FINAL,
            )
            .order_by(MediaAsset.created_at.desc())
            .first()
        )
    if latest is None:
        _fail("no final render yet", code=2)
        return
    meta = latest.meta or {}
    console.print(
        json.dumps(
            {
                "path": latest.path,
                "size_bytes": latest.size_bytes,
                "duration": meta.get("duration"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "fps": meta.get("fps"),
                "subtitles_burned": meta.get("subtitles_burned"),
                "scene_count": meta.get("scene_count"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
