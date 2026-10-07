"""
RepoMind AI — FileDocument Repository
"""
from typing import Sequence
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_document import FileDocument

logger = structlog.get_logger(__name__)


class FileRepository:
    """Data access layer for FileDocument entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, file_id: str) -> FileDocument | None:
        result = await self.session.execute(
            select(FileDocument).where(FileDocument.id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_by_relative_path(
        self, project_id: str, relative_path: str
    ) -> FileDocument | None:
        result = await self.session.execute(
            select(FileDocument).where(
                FileDocument.project_id == project_id,
                FileDocument.relative_path == relative_path,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> Sequence[FileDocument]:
        result = await self.session.execute(
            select(FileDocument)
            .where(FileDocument.project_id == project_id)
            .order_by(FileDocument.relative_path)
        )
        return result.scalars().all()

    async def create(
        self,
        project_id: str,
        path: str,
        relative_path: str,
        file_hash: str,
        language: str,
        size_bytes: int = 0,
        line_count: int = 0,
        ast_status: str = "pending",
    ) -> FileDocument:
        doc = FileDocument(
            project_id=project_id,
            path=path,
            relative_path=relative_path,
            file_hash=file_hash,
            language=language,
            size_bytes=size_bytes,
            line_count=line_count,
            ast_status=ast_status,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def delete_by_project(self, project_id: str) -> int:
        result = await self.session.execute(
            delete(FileDocument).where(FileDocument.project_id == project_id)
        )
        await self.session.flush()
        return result.rowcount
