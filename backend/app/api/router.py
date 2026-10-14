"""
RepoMind AI — API Router

Registers all versioned API routes.
"""
from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.projects import router as projects_router
from app.api.v1.symbols import router as symbols_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.chat import router as chat_router

api_router = APIRouter()

# Health endpoint — no version prefix (used by load balancers and Docker)
api_router.include_router(health_router, tags=["health"])

# Versioned API
api_router.include_router(
    projects_router,
    prefix="/api/v1/projects",
    tags=["projects"],
)
api_router.include_router(
    symbols_router,
    prefix="/api/v1/projects",
    tags=["symbols"],
)
api_router.include_router(
    retrieval_router,
    prefix="/api/v1/projects",
    tags=["retrieval"],
)
api_router.include_router(
    chat_router,
    prefix="/api/v1/projects",
    tags=["chat"],
)
