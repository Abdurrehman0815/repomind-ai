"""
RepoMind AI — CodeSymbol Repository
"""
from typing import Sequence
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_symbol import CodeSymbol
from app.models.code_chunk import CodeChunk

logger = structlog.get_logger(__name__)


class SymbolRepository:
    """Data access layer for CodeSymbol entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, symbol_id: str) -> CodeSymbol | None:
        result = await self.session.execute(
            select(CodeSymbol).where(CodeSymbol.id == symbol_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, symbol_ids: list[str]) -> list[CodeSymbol]:
        """Return symbols matching a collection of IDs."""
        if not symbol_ids:
            return []
        result = await self.session.execute(
            select(CodeSymbol).where(CodeSymbol.id.in_(symbol_ids))
        )
        return list(result.scalars().all())

    async def find_by_chunk_id(self, chunk_id: str) -> Sequence[CodeSymbol]:
        """Find symbols in the source file that owns a code chunk.

        Chunks currently do not store a symbol foreign key, so file-level
        symbols are the closest reliable association available in this schema.
        """
        result = await self.session.execute(
            select(CodeChunk.file_id).where(CodeChunk.id == chunk_id)
        )
        file_id = result.scalar_one_or_none()
        if not file_id:
            return []
        return await self.list_by_file(str(file_id))

    async def search_by_name(
        self, project_id: str, name_query: str
    ) -> Sequence[CodeSymbol]:
        result = await self.session.execute(
            select(CodeSymbol)
            .where(
                CodeSymbol.project_id == project_id,
                CodeSymbol.name.ilike(f"%{name_query}%"),
            )
            .order_by(CodeSymbol.name)
        )
        return result.scalars().all()

    async def list_by_file(self, file_id: str) -> Sequence[CodeSymbol]:
        result = await self.session.execute(
            select(CodeSymbol)
            .where(CodeSymbol.file_id == file_id)
            .order_by(CodeSymbol.line_start)
        )
        return result.scalars().all()

    async def create(
        self,
        project_id: str,
        file_id: str,
        name: str,
        kind: str,
        line_start: int,
        line_end: int,
        signature: str | None = None,
        docstring: str | None = None,
        parent_symbol_id: str | None = None,
    ) -> CodeSymbol:
        sym = CodeSymbol(
            project_id=project_id,
            file_id=file_id,
            name=name,
            kind=kind,
            line_start=line_start,
            line_end=line_end,
            signature=signature,
            docstring=docstring,
            parent_symbol_id=parent_symbol_id,
        )
        self.session.add(sym)
        await self.session.flush()
        return sym

    async def delete_by_file(self, file_id: str) -> int:
        result = await self.session.execute(
            delete(CodeSymbol).where(CodeSymbol.file_id == file_id)
        )
        await self.session.flush()
        return result.rowcount
