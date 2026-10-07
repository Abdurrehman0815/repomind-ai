"""
RepoMind AI — CodeChunk Repository
"""
from typing import Sequence, Any
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_chunk import CodeChunk

logger = structlog.get_logger(__name__)


class ChunkRepository:
    """Data access layer for CodeChunk entities with vector support."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, chunk_id: str) -> CodeChunk | None:
        result = await self.session.execute(
            select(CodeChunk).where(CodeChunk.id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def list_by_file(self, file_id: str) -> Sequence[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(CodeChunk.file_id == file_id)
            .order_by(CodeChunk.chunk_index)
        )
        return result.scalars().all()

    async def list_by_project(self, project_id: str) -> Sequence[CodeChunk]:
        result = await self.session.execute(
            select(CodeChunk)
            .where(CodeChunk.project_id == project_id)
            .order_by(CodeChunk.created_at)
        )
        return result.scalars().all()

    async def create(
        self,
        project_id: str,
        file_id: str,
        chunk_index: int,
        content: str,
        start_line: int,
        end_line: int,
        token_count: int = 0,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CodeChunk:
        chunk = CodeChunk(
            project_id=project_id,
            file_id=file_id,
            chunk_index=chunk_index,
            content=content,
            start_line=start_line,
            end_line=end_line,
            token_count=token_count,
            embedding=embedding,
            metadata_=metadata or {},
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def delete_by_file(self, file_id: str) -> int:
        result = await self.session.execute(
            delete(CodeChunk).where(CodeChunk.file_id == file_id)
        )
        await self.session.flush()
        return result.rowcount
