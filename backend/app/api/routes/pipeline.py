"""Pipeline endpoints.

Contracts live here so the frontend can be built in parallel. Phase 7
implemented audio upload + FFmpeg metadata extraction; Phase 8 added
transcription via faster-whisper; Phase 9 wires lyrics upload +
LLM-driven lyrics analysis. The remaining plan-scenes / generate
endpoints stay as 501 stubs until the phases that implement them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import AssetKind, MediaAsset, Project, Scene
from backend.app.schemas import (
    AudioMetadataOut,
    AudioUploadResponse,
    GeneratedImage,
    GenerateImagesRequest,
    GenerateImagesResponse,
    LyricsAnalysisResponse,
    LyricsUploadRequest,
    LyricsUploadResponse,
    Message,
    PlanScenesRequest,
    PlanScenesResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptSegmentOut,
)
from backend.app.services.audio import save_upload
from backend.app.services.images import (
    ImageGenerationServiceError,
    generate_project_images,
)
from backend.app.services.lyrics import (
    LyricsAnalysisError,
    analyze_lyrics,
    save_lyrics,
)
from backend.app.services.scenes import (
    ScenePlanServiceError,
    plan_project_scenes,
)
from backend.app.services.transcription import transcribe_project
from models.image import get_image_engine
from models.image.base import ImageGenerationEngine
from models.llm import get_llm_engine
from models.llm.base import LLMEngine
from pipeline.audio_analysis import AudioAnalysisError, probe
from pipeline.transcription import TranscriptionError

router = APIRouter(prefix="/projects/{project_id}")
log = logging.getLogger(__name__)


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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


@router.post("/generate", response_model=Message)
def generate(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("End-to-end generation")


@router.get("/render", response_model=Message)
def render_status(project_id: str, db: Session = Depends(get_db)) -> Message:
    _require_project(db, project_id)
    raise _not_implemented("Render status")
