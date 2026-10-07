"""
RepoMind AI — Database Session and Engine

Async SQLAlchemy engine and session factory.
"""
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from settings."""
    settings = get_settings()

    kwargs: dict = {
        "echo": settings.db_echo,
        "future": True,
    }

    # For test environments use NullPool to avoid connection leaks
    if settings.environment == "test":
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_pre_ping"] = True

    return create_async_engine(settings.database_url, **kwargs)


engine: AsyncEngine = _create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an async database session.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Check if the database is reachable.
    Returns True if successful, False otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("database_connection_failed", error=str(exc))
        return False


async def check_pgvector_extension() -> bool:
    """
    Check if the pgvector extension is installed.
    Returns True if available, False otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            row = result.fetchone()
            return row is not None
    except Exception as exc:
        logger.warning("pgvector_check_failed", error=str(exc))
        return False
