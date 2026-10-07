"""
RepoMind AI — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine, check_database_connection

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager — startup and shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    logger.info(
        "repomind_startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        version="0.1.0",
    )

    # Check database connectivity on startup
    db_ok = await check_database_connection()
    if not db_ok:
        logger.warning(
            "database_unavailable",
            message="Database connection failed — some features will not work.",
        )
    else:
        logger.info("database_connected")

    yield

    logger.info("repomind_shutdown")


def create_application() -> FastAPI:
    """Factory function — creates and configures the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="RepoMind AI",
        description=(
            "Agentic codebase intelligence copilot — answers questions about your "
            "repository with source citations, architecture analysis, and safe tools."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    # ── Middleware ──────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ─────────────────────────────────────────────────
    app.include_router(api_router)

    return app


app = create_application()
