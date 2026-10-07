"""
RepoMind AI — Health Check Endpoints

Provides health information for load balancers, Docker health checks,
and startup diagnostics.
"""
import time
from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import check_database_connection, check_pgvector_extension

logger = structlog.get_logger(__name__)
router = APIRouter()

_start_time = time.time()


class ComponentStatus(BaseModel):
    """Status of a single system component."""
    status: str  # "ok" | "degraded" | "unavailable"
    message: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    environment: str
    uptime_seconds: float
    components: dict[str, ComponentStatus]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check — fast response for load balancer use.
    Does not check database; use /health/full for deep checks.
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(time.time() - _start_time, 2),
        components={
            "api": ComponentStatus(status="ok"),
        },
    )


@router.get("/health/full", response_model=HealthResponse)
async def health_check_full() -> HealthResponse:
    """
    Full health check — tests all external dependencies.
    May be slow; do not use for load balancer probes.
    """
    settings = get_settings()
    components: dict[str, ComponentStatus] = {}
    overall = "healthy"

    # ── Database ──────────────────────────────────────────────
    t0 = time.monotonic()
    db_ok = await check_database_connection()
    db_latency = round((time.monotonic() - t0) * 1000, 1)

    if db_ok:
        components["database"] = ComponentStatus(
            status="ok",
            latency_ms=db_latency,
        )
    else:
        components["database"] = ComponentStatus(
            status="unavailable",
            message="Cannot connect to PostgreSQL",
            latency_ms=db_latency,
        )
        overall = "unhealthy"

    # ── pgvector ──────────────────────────────────────────────
    if db_ok:
        t0 = time.monotonic()
        vec_ok = await check_pgvector_extension()
        vec_latency = round((time.monotonic() - t0) * 1000, 1)

        if vec_ok:
            components["pgvector"] = ComponentStatus(
                status="ok",
                latency_ms=vec_latency,
            )
        else:
            components["pgvector"] = ComponentStatus(
                status="unavailable",
                message="pgvector extension not installed",
                latency_ms=vec_latency,
            )
            if overall == "healthy":
                overall = "degraded"
    else:
        components["pgvector"] = ComponentStatus(
            status="unknown",
            message="Skipped — database unavailable",
        )

    # ── Ollama (non-blocking check) ───────────────────────────
    ollama_status = await _check_ollama()
    components["ollama"] = ollama_status
    if ollama_status.status == "unavailable" and overall == "healthy":
        overall = "degraded"

    logger.info("health_check_full", overall=overall, components=list(components.keys()))

    return HealthResponse(
        status=overall,
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(time.time() - _start_time, 2),
        components=components,
    )


async def _check_ollama() -> ComponentStatus:
    """Check if Ollama is reachable."""
    import httpx
    settings = get_settings()

    if settings.llm_provider != "ollama":
        return ComponentStatus(
            status="ok",
            message=f"Provider is '{settings.llm_provider}', Ollama not used",
        )

    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/version")
        latency = round((time.monotonic() - t0) * 1000, 1)

        if resp.status_code == 200:
            data = resp.json()
            return ComponentStatus(
                status="ok",
                message=f"Ollama {data.get('version', 'unknown')}",
                latency_ms=latency,
            )
        else:
            return ComponentStatus(
                status="degraded",
                message=f"Ollama responded with HTTP {resp.status_code}",
                latency_ms=latency,
            )
    except Exception as exc:
        return ComponentStatus(
            status="unavailable",
            message=f"Ollama not reachable: {exc}",
        )
