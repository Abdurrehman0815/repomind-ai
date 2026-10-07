"""
RepoMind AI — API Router

Registers all versioned API routes.
"""
from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.projects import router as projects_router

api_router = APIRouter()

# Health endpoint — no version prefix (used by load balancers and Docker)
api_router.include_router(health_router, tags=["health"])

# Versioned API
api_router.include_router(
    projects_router,
    prefix="/api/v1/projects",
    tags=["projects"],
)
