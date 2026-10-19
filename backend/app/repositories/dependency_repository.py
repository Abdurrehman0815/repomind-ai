"""
RepoMind AI — Dependency Repository
"""
from typing import Sequence
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dependency import Dependency

logger = structlog.get_logger(__name__)


class DependencyRepository:
    """Data access layer for Dependency entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, dependency_id: str) -> Dependency | None:
        result = await self.session.execute(
            select(Dependency).where(Dependency.id == dependency_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> Sequence[Dependency]:
        result = await self.session.execute(
            select(Dependency)
            .where(Dependency.project_id == project_id)
            .order_by(Dependency.created_at)
        )
        return result.scalars().all()

    async def list_by_file(self, file_id: str) -> Sequence[Dependency]:
        result = await self.session.execute(
            select(Dependency)
            .where(Dependency.source_file_id == file_id)
            .order_by(Dependency.line_number)
        )
        return result.scalars().all()

    async def find_by_file_ids(self, file_ids: list[str]) -> list[Dependency]:
        """Find dependency edges originating from any supplied file."""
        if not file_ids:
            return []
        result = await self.session.execute(
            select(Dependency)
            .where(Dependency.source_file_id.in_(file_ids))
            .order_by(Dependency.line_number)
        )
        return list(result.scalars().all())

    async def find_by_dependent_file_id(self, file_id: str) -> list[Dependency]:
        """Find edges whose target is the given file (incoming dependencies)."""
        result = await self.session.execute(
            select(Dependency)
            .where(Dependency.target_file_id == file_id)
            .order_by(Dependency.line_number)
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: str,
        source_file_id: str,
        target_module: str,
        import_statement: str,
        target_file_id: str | None = None,
        symbol_name: str | None = None,
        line_number: int | None = None,
    ) -> Dependency:
        dep = Dependency(
            project_id=project_id,
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            target_module=target_module,
            import_statement=import_statement,
            symbol_name=symbol_name,
            line_number=line_number,
        )
        self.session.add(dep)
        await self.session.flush()
        return dep

    async def delete_by_file(self, file_id: str) -> int:
        """Delete all dependencies for a given file."""
        result = await self.session.execute(
            delete(Dependency).where(Dependency.source_file_id == file_id)
        )
        await self.session.flush()
        return result.rowcount

    async def delete_by_project(self, project_id: str) -> int:
        """Delete all dependencies for a given project."""
        result = await self.session.execute(
            delete(Dependency).where(Dependency.project_id == project_id)
        )
        await self.session.flush()
        return result.rowcount