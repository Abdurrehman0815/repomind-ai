"""
RepoMind AI — Project Repository
"""
from typing import Sequence
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project

logger = structlog.get_logger(__name__)


class ProjectRepository:
    """Data access layer for Project entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, project_id: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get(self, project_id: str) -> Project | None:
        """Backward-compatible alias used by agents and services."""
        return await self.get_by_id(project_id)

    async def get_by_path(self, path: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.path == path)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Project]:
        result = await self.session.execute(
            select(Project).order_by(Project.created_at.desc())
        )
        return result.scalars().all()

    async def create(
        self,
        name: str,
        path: str,
        settings: dict | None = None,
        metadata: dict | None = None,
    ) -> Project:
        project = Project(
            name=name,
            path=path,
            settings=settings or {},
            metadata_=metadata or {},
            status="unindexed",
        )
        self.session.add(project)
        await self.session.flush()
        return project

    async def update_status(self, project_id: str, status: str) -> Project | None:
        project = await self.get_by_id(project_id)
        if project:
            project.status = status
            await self.session.flush()
        return project

    async def update_commit_hash(self, project_id: str, commit_hash: str) -> Project | None:
        """Update the repository commit hash for a project."""
        project = await self.get_by_id(project_id)
        if project:
            project.repository_commit = commit_hash
            await self.session.flush()
        return project

    async def delete(self, project_id: str) -> bool:
        project = await self.get_by_id(project_id)
        if project:
            await self.session.delete(project)
            await self.session.flush()
            return True
        return False