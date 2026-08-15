"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    return app


app = create_app()
