"""Router aggregation."""

from fastapi import APIRouter

from backend.app.api.routes import health, jobs, pipeline, projects, scenes

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(pipeline.router, tags=["pipeline"])
api_router.include_router(scenes.router, tags=["scenes"])
api_router.include_router(jobs.router, tags=["jobs"])
