"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import api_router
from backend.app.core.logging import configure_logging
from backend.app.core.settings import get_settings
from backend.app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_log_level)
    settings.ensure_dirs()
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Devotional Video Studio",
        version="0.1.0",
        description=(
            "Local-first pipeline that turns Hindi / Sanskrit devotional "
            "audio into cinematic short videos."
        ),
        lifespan=lifespan,
    )

    # Frontend runs on a separate origin in dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.next_public_api_base,
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    # Serve generated media so the browser can play/download it directly.
    # Storage root is created by settings.ensure_dirs() in the lifespan
    # hook; StaticFiles won't error out here because we haven't started
    # serving requests yet.
    settings.ensure_dirs()
    app.mount(
        "/storage",
        StaticFiles(directory=str(settings.storage_root)),
        name="storage",
    )
    return app


app = create_app()
