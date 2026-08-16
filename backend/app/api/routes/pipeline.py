"""Pipeline endpoints.

Contracts live here so the frontend can be built in parallel. Phase 7
implemented audio upload + FFmpeg metadata extraction; Phase 8 added
transcription via faster-whisper; Phase 9 wires lyrics upload +
LLM-driven lyrics analysis. The remaining plan-scenes / generate
endpoints stay as 501 stubs until the phases that implement them.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from backend.app.schemas import (
    AsyncGenerateResponse,
    AudioMetadataOut,
    AudioUploadResponse,
    GeneratedImage,
    GeneratedVideo,
    GenerateImagesRequest,
    GenerateImagesResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateVideosRequest,
    GenerateVideosResponse,
    GenerationStepOut,
    LyricsAnalysisResponse,
    LyricsUploadRequest,
    LyricsUploadResponse,
    PlanScenesRequest,
    PlanScenesResponse,
    ReferenceOut,
    RenderFinalRequest,
    RenderFinalResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptSegmentOut,
)
from backend.app.services.audio import save_upload
from backend.app.services.generate import (
    GenerationError,
    _has_audio,
    generate_project_end_to_end,
)
from backend.app.services.images import (
    ImageGenerationServiceError,
    generate_project_images,
)
from backend.app.services.jobs import kick_off_generate_job
from backend.app.services.lyrics import (
    LyricsAnalysisError,
    analyze_lyrics,
    save_lyrics,
)
from backend.app.services.render import (
    CompositeServiceError,
    render_project_final,
)
from backend.app.services.scenes import (
    ScenePlanServiceError,
    plan_project_scenes,
)
from backend.app.services.transcription import transcribe_project
from backend.app.services.videos import (
    VideoGenerationServiceError,
    generate_project_videos,
)
from models.image import get_image_engine
from models.image.base import ImageGenerationEngine
from models.llm import get_llm_engine
from models.llm.base import LLMEngine
from models.video import get_video_engine
from models.video.base import VideoGenerationEngine
from pipeline.audio_analysis import AudioAnalysisError, probe
from pipeline.transcription import TranscriptionError

router = APIRouter(prefix="/projects/{project_id}")
log = logging.getLogger(__name__)


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _storage_url(settings: Settings, absolute_path: str) -> str:
    """Turn an absolute storage path into a browser-relative URL.

    The FastAPI app mounts settings.storage_root at ``/storage``, so any
    file under STORAGE_ROOT can be served as ``/storage/<relative>``.
    Returns an empty string for paths that are NOT under STORAGE_ROOT
    (defence in depth — the frontend must never receive a link to a
    file the user isn't entitled to see).
    """
    if not absolute_path:
        return ""
    try:
        root = settings.storage_root.resolve()
        p = type(root)(absolute_path).resolve()
    except (OSError, ValueError):
        return ""
    if not p.is_relative_to(root):
        return ""
    return "/storage/" + str(p.relative_to(root)).replace("\\", "/")


def _not_implemented(feature: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{feature} is not implemented yet (see project phase plan).",
    )


@router.post(
    "/audio",
    response_model=AudioUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_audio(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AudioUploadResponse:
    project = _require_project(db, project_id)

    stored = await save_upload(
        settings=settings, project_id=project.id, upload=file
    )

    try:
        meta = probe(stored.path)
    except AudioAnalysisError as exc:
        # File was invalid audio - clean up and 400 back.
        stored.path.unlink(missing_ok=True)
        log.warning("rejecting upload for project=%s: %s", project.id, exc)
        raise HTTPException(status_code=400, detail=f"audio invalid: {exc}") from exc

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
    db.refresh(asset)

    return AudioUploadResponse(
        asset_id=asset.id,
        project_id=project.id,
        path=str(stored.path),
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        metadata=AudioMetadataOut(**meta.to_dict()),
    )


@router.post("/lyrics", response_model=LyricsUploadResponse)
def upload_lyrics(
    project_id: str,
    payload: LyricsUploadRequest,
    db: Session = Depends(get_db),
) -> LyricsUploadResponse:
    project = _require_project(db, project_id)
    save_lyrics(db=db, project=project, text=payload.text)
    return LyricsUploadResponse(
        project_id=project.id,
        lyrics_length=len(project.lyrics or ""),
    )


@router.post(
    "/references",
    response_model=ReferenceOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference(
    project_id: str,
    file: UploadFile = File(...),
    label: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReferenceOut:
    from backend.app.services.references import save_reference

    project = _require_project(db, project_id)
    stored = await save_reference(
        settings=settings, project_id=project.id, upload=file, label=label
    )
    asset = MediaAsset(
        project_id=project.id,
        kind=AssetKind.REFERENCE,
        path=str(stored.path),
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        meta={"label": label} if label else None,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return ReferenceOut(
        id=asset.id,
        project_id=project.id,
        path=asset.path,
        url=_storage_url(settings, asset.path),
        label=label,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        created_at=asset.created_at,
    )


@router.get("/references", response_model=list[ReferenceOut])
def list_references(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[ReferenceOut]:
    _require_project(db, project_id)
    rows = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == AssetKind.REFERENCE,
        )
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    return [
        ReferenceOut(
            id=a.id,
            project_id=project_id,
            path=a.path,
            url=_storage_url(settings, a.path),
            label=(a.meta or {}).get("label"),
            original_filename=a.original_filename,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes,
            created_at=a.created_at,
        )
        for a in rows
    ]


@router.delete(
    "/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_reference(
    project_id: str,
    reference_id: str,
    db: Session = Depends(get_db),
) -> None:
    _require_project(db, project_id)
    asset = db.get(MediaAsset, reference_id)
    if asset is None or asset.project_id != project_id or asset.kind != AssetKind.REFERENCE:
        raise HTTPException(status_code=404, detail="reference not found")
    p = Path(asset.path)
    p.unlink(missing_ok=True)
    db.delete(asset)
    db.commit()


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def transcribe_endpoint(
    project_id: str,
    payload: TranscriptionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse:
    project = _require_project(db, project_id)
    req = payload or TranscriptionRequest()
    try:
        audio_asset, transcript_asset, result = transcribe_project(
            db=db,
            settings=settings,
            project=project,
            language=req.language,
            beam_size=req.beam_size,
            vad_filter=req.vad_filter,
        )
    except TranscriptionError as exc:
        log.warning("transcription failed for project=%s: %s", project.id, exc)
        # 409 when preconditions aren't met (no audio), 500 for engine faults.
        code = 409 if "no audio" in str(exc).lower() else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    return TranscriptionResponse(
        project_id=project.id,
        audio_asset_id=audio_asset.id,
        transcript_asset_id=transcript_asset.id,
        language=result.language,
        language_probability=result.language_probability,
        duration=result.duration,
        model=result.model,
        segments=[
            TranscriptSegmentOut(start=s.start, end=s.end, text=s.text)
            for s in result.segments
        ],
        text=result.text,
        transcript_path=transcript_asset.path,
    )


@router.post(
    "/analyze",
    response_model=LyricsAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    engine: LLMEngine = Depends(get_llm_engine),
) -> LyricsAnalysisResponse:
    project = _require_project(db, project_id)
    try:
        analysis, asset = await analyze_lyrics(
            db=db, settings=settings, project=project, engine=engine
        )
    except LyricsAnalysisError as exc:
        log.warning("lyrics analysis failed project=%s: %s", project.id, exc)
        code = 409 if "no lyrics" in str(exc).lower() else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    return LyricsAnalysisResponse(
        project_id=project.id,
        engine=engine.name,
        model=settings.llm_model,
        analysis=analysis,
        analysis_asset_id=asset.id,
        analysis_path=asset.path,
    )


@router.post("/plan-scenes", response_model=PlanScenesResponse, status_code=status.HTTP_201_CREATED)
async def plan_scenes(
    project_id: str,
    payload: PlanScenesRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    engine: LLMEngine = Depends(get_llm_engine),
) -> PlanScenesResponse:
    project = _require_project(db, project_id)
    req = payload or PlanScenesRequest()
    try:
        plan, asset, _replaced = await plan_project_scenes(
            db=db,
            settings=settings,
            project=project,
            engine=engine,
            style_preset_override=req.style_preset,
            target_scene_count=req.target_scene_count,
            reference_hints=req.reference_hints,
        )
    except ScenePlanServiceError as exc:
        log.warning("scene planning failed project=%s: %s", project.id, exc)
        code = 409 if "no lyrics analysis" in str(exc).lower() else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    return PlanScenesResponse(
        project_id=project.id,
        engine=engine.name,
        model=settings.llm_model,
        plan=plan,
        plan_asset_id=asset.id,
        plan_path=asset.path,
        scene_count=len(plan.scenes),
    )


@router.post(
    "/generate-images",
    response_model=GenerateImagesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_images(
    project_id: str,
    payload: GenerateImagesRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    image_engine: ImageGenerationEngine = Depends(get_image_engine),
) -> GenerateImagesResponse:
    project = _require_project(db, project_id)
    req = payload or GenerateImagesRequest()
    try:
        pairs = await generate_project_images(
            db=db,
            settings=settings,
            project=project,
            engine=image_engine,
            force=req.force,
        )
    except ImageGenerationServiceError as exc:
        log.warning("image generation failed project=%s: %s", project.id, exc)
        code = 409 if "no scenes" in str(exc).lower() else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    total_scenes = (
        db.query(Scene).filter(Scene.project_id == project.id).count()
    )
    return GenerateImagesResponse(
        project_id=project.id,
        engine=image_engine.name,
        scenes_total=total_scenes,
        scenes_generated=len(pairs),
        images=[
            GeneratedImage(
                scene_index=scene.index,
                image_path=asset.path,
                size_bytes=asset.size_bytes or 0,
                seed=int((asset.meta or {}).get("seed", 0)),
            )
            for scene, asset in pairs
        ],
    )


@router.post(
    "/generate-videos",
    response_model=GenerateVideosResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_videos(
    project_id: str,
    payload: GenerateVideosRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    video_engine: VideoGenerationEngine = Depends(get_video_engine),
) -> GenerateVideosResponse:
    project = _require_project(db, project_id)
    req = payload or GenerateVideosRequest()
    try:
        pairs = await generate_project_videos(
            db=db,
            settings=settings,
            project=project,
            engine=video_engine,
            force=req.force,
            fps=req.fps,
        )
    except VideoGenerationServiceError as exc:
        log.warning("video generation failed project=%s: %s", project.id, exc)
        detail = str(exc).lower()
        code = 409 if ("no scenes" in detail or "no image" in detail) else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    total_scenes = (
        db.query(Scene).filter(Scene.project_id == project.id).count()
    )
    return GenerateVideosResponse(
        project_id=project.id,
        engine=video_engine.name,
        scenes_total=total_scenes,
        scenes_generated=len(pairs),
        videos=[
            GeneratedVideo(
                scene_index=scene.index,
                video_path=asset.path,
                duration=float((asset.meta or {}).get("duration", 0.0)),
                fps=int((asset.meta or {}).get("fps", 0)),
                size_bytes=asset.size_bytes or 0,
            )
            for scene, asset in pairs
        ],
    )


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    project_id: str,
    payload: GenerateRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm_engine: LLMEngine = Depends(get_llm_engine),
    image_engine: ImageGenerationEngine = Depends(get_image_engine),
    video_engine: VideoGenerationEngine = Depends(get_video_engine),
) -> GenerateResponse:
    """One-button MVP endpoint. Chains every real pipeline stage."""
    project = _require_project(db, project_id)
    req = payload or GenerateRequest()
    try:
        outcome = await generate_project_end_to_end(
            db=db,
            settings=settings,
            project=project,
            llm_engine=llm_engine,
            image_engine=image_engine,
            video_engine=video_engine,
            run_transcription=req.run_transcription,
            target_scene_count=req.target_scene_count,
            style_preset_override=req.style_preset,
            burn_subtitles=req.burn_subtitles,
            fps=req.fps,
            xfade_seconds=req.xfade_seconds,
        )
    except GenerationError as exc:
        log.warning(
            "end-to-end generation failed project=%s stage=%s: %s",
            project.id,
            exc.stage,
            exc.reason,
        )
        code = 409 if exc.stage == "precheck" else 500
        raise HTTPException(
            status_code=code,
            detail={"stage": exc.stage, "message": exc.reason},
        ) from exc

    return GenerateResponse(
        project_id=outcome.project_id,
        final_asset_id=outcome.final_asset_id,
        path=outcome.final_path,
        url=_storage_url(settings, outcome.final_path),
        duration=outcome.duration,
        width=outcome.width,
        height=outcome.height,
        fps=outcome.fps,
        size_bytes=outcome.size_bytes,
        subtitles_burned=outcome.subtitles_burned,
        scene_count=outcome.scene_count,
        progress=[
            GenerationStepOut(stage=p.stage, status=p.status, detail=p.detail)
            for p in outcome.progress
        ],
    )


@router.post(
    "/generate-async",
    response_model=AsyncGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_async(
    project_id: str,
    payload: GenerateRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm_engine: LLMEngine = Depends(get_llm_engine),
    image_engine: ImageGenerationEngine = Depends(get_image_engine),
    video_engine: VideoGenerationEngine = Depends(get_video_engine),
) -> AsyncGenerateResponse:
    """Queue the whole pipeline as a background job.

    Returns 202 with a ``job_id`` immediately. Poll
    ``GET /api/jobs/{job_id}`` for progress and the final URL.
    """
    project = _require_project(db, project_id)

    # Precheck synchronously so the client learns about missing audio /
    # lyrics right away rather than paying the async round-trip first.
    if not _has_audio(db, project.id):
        raise HTTPException(
            status_code=409,
            detail={
                "stage": "precheck",
                "message": "no audio uploaded — POST /audio first",
            },
        )
    if not (project.lyrics and project.lyrics.strip()):
        raise HTTPException(
            status_code=409,
            detail={
                "stage": "precheck",
                "message": "no lyrics uploaded — POST /lyrics first",
            },
        )

    req = payload or GenerateRequest()
    job = kick_off_generate_job(
        db=db,
        settings=settings,
        project=project,
        params=req.model_dump(),
        llm_engine=llm_engine,
        image_engine=image_engine,
        video_engine=video_engine,
    )
    return AsyncGenerateResponse(
        project_id=project.id,
        job_id=job.id,
        status=job.status.value,
    )


@router.post(
    "/render",
    response_model=RenderFinalResponse,
    status_code=status.HTTP_201_CREATED,
)
def render_final(
    project_id: str,
    payload: RenderFinalRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RenderFinalResponse:
    project = _require_project(db, project_id)
    req = payload or RenderFinalRequest()
    try:
        asset, result = render_project_final(
            db=db,
            settings=settings,
            project=project,
            burn_subtitles=req.burn_subtitles,
            fps=req.fps,
            xfade_seconds=req.xfade_seconds,
        )
    except CompositeServiceError as exc:
        log.warning("render failed project=%s: %s", project.id, exc)
        detail = str(exc).lower()
        code = 409 if ("no scenes" in detail or "no video" in detail) else 500
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    meta = asset.meta or {}
    return RenderFinalResponse(
        project_id=project.id,
        final_asset_id=asset.id,
        path=asset.path,
        url=_storage_url(settings, asset.path),
        duration=float(result.duration),
        width=int(result.width),
        height=int(result.height),
        fps=int(result.fps),
        size_bytes=asset.size_bytes or 0,
        subtitles_burned=bool(meta.get("subtitles_burned")),
        scene_count=int(meta.get("scene_count", 0)),
    )


@router.get("/render", response_model=RenderFinalResponse)
def render_status(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RenderFinalResponse:
    project = _require_project(db, project_id)
    latest = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.project_id == project.id,
            MediaAsset.kind == AssetKind.FINAL,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="no final render yet — POST /render to create one",
        )
    meta = latest.meta or {}
    return RenderFinalResponse(
        project_id=project.id,
        final_asset_id=latest.id,
        path=latest.path,
        url=_storage_url(settings, latest.path),
        duration=float(meta.get("duration", 0.0)),
        width=int(meta.get("width", 0)),
        height=int(meta.get("height", 0)),
        fps=int(meta.get("fps", 0)),
        size_bytes=latest.size_bytes or 0,
        subtitles_burned=bool(meta.get("subtitles_burned")),
        scene_count=int(meta.get("scene_count", 0)),
    )
