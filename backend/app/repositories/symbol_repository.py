"""
RepoMind AI — CodeSymbol Repository
"""
from typing import Sequence
import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_symbol import CodeSymbol

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
