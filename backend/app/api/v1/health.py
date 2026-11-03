"""
RepoMind AI — Health Check Endpoints

Provides health information for load balancers, Docker health checks,
and startup diagnostics.
"""
import time
from typing import Awaitable, Callable

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

    # ── Active AI providers (Azure Foundry or Ollama) ─────────
    for name, check in (("llm", _check_llm), ("embeddings", _check_embeddings)):
        component = await _cached(name, check)
        components[name] = component
        if component.status != "ok" and overall == "healthy":
            overall = "degraded"

    logger.info("health_check_full", overall=overall, components=list(components.keys()))

    return HealthResponse(
        status=overall,
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(time.time() - _start_time, 2),
        components=components,
    )


# Provider checks make a real (tiny) model call, and the UI polls every 30s,
# so results are cached rather than paying for a request on every poll.
_PROVIDER_CHECK_TTL_S = 300
_provider_cache: dict[str, tuple[float, ComponentStatus]] = {}


async def _cached(name: str, check: Callable[[], Awaitable[ComponentStatus]]) -> ComponentStatus:
    cached = _provider_cache.get(name)
    if cached and time.monotonic() - cached[0] < _PROVIDER_CHECK_TTL_S:
        return cached[1]
    status = await check()
    # Cache failures briefly so a fixed key/endpoint shows green again quickly.
    ttl_start = time.monotonic() if status.status == "ok" else time.monotonic() - _PROVIDER_CHECK_TTL_S + 30
    _provider_cache[name] = (ttl_start, status)
    return status


async def _check_llm() -> ComponentStatus:
    """Check the configured LLM provider with a minimal request."""
    from app.ai.providers.registry import get_llm_provider
    try:
        provider = get_llm_provider()
        t0 = time.monotonic()
        ok = await provider.health_check()
        latency = round((time.monotonic() - t0) * 1000, 1)
        label = f"{provider.provider_name}: {provider.model_name}"
        if ok:
            return ComponentStatus(status="ok", message=label, latency_ms=latency)
        return ComponentStatus(status="unavailable", message=f"{label} not reachable (check endpoint, key, deployment)", latency_ms=latency)
    except Exception as exc:
        return ComponentStatus(status="unavailable", message=f"LLM provider error: {exc}")


async def _check_embeddings() -> ComponentStatus:
    """Check the configured embedding provider with a one-item request."""
    from app.ai.providers.embedding_registry import get_embedding_provider
    try:
        provider = get_embedding_provider()
        t0 = time.monotonic()
        ok = await provider.health_check()
        latency = round((time.monotonic() - t0) * 1000, 1)
        label = f"{provider.provider_name}: {provider.model_name}"
        if ok:
            return ComponentStatus(status="ok", message=label, latency_ms=latency)
        return ComponentStatus(status="unavailable", message=f"{label} not reachable (check endpoint, key, deployment)", latency_ms=latency)
    except Exception as exc:
        return ComponentStatus(status="unavailable", message=f"Embedding provider error: {exc}")
